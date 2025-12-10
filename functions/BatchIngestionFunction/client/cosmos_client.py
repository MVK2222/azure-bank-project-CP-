"""
cosmos_client.py: Cosmos DB Client Wrapper with Performance Optimizations

This module provides high-level abstractions for Cosmos DB operations optimized for
the banking data platform's workload patterns:
- High-throughput batch upserts with parallel execution
- Automatic retry logic for transient failures (429 throttling, network errors)
- Datetime serialization for JSON compatibility
- Container lifecycle management (lazy creation)

Performance Optimizations:
1. Parallel Upserts: ThreadPoolExecutor for concurrent Cosmos DB writes
2. Exponential Backoff: Smart retry strategy for rate limiting (429 errors)
3. Connection Pooling: Single CosmosClient instance reused across invocations
4. Batch Operations: Upserts grouped for throughput efficiency

Cosmos DB Pricing & Resource Management:
- Database Throughput: 400 RU/s (Request Units per second) shared across containers
- Cost: ~$24/month for 400 RU/s shared throughput
- Scaling: Auto-scale can be enabled for variable workloads
- Partition Strategy: Critical for distributed throughput and storage

Reliability Features:
- Idempotent Operations: Upserts safely handle retries
- Error Isolation: Single item failures don't crash the batch
- Comprehensive Logging: All errors logged for debugging
- Configurable Retry Policy: Tunable via environment variables

Environment Variables (Configuration):
- COSMOS_DB_CONNECTION_STRING (required): Connection string with read/write permissions
- COSMOS_DB_NAME (default: "operation-storage-db"): Database name
- UPSERT_WORKERS (default: 8): Parallel upsert thread pool size
- UPSERT_RETRIES (default: 3): Max retry attempts for transient errors
- UPSERT_RETRY_BACKOFF (default: 0.5): Base backoff in seconds (exponential)

Best Practices:
- Always include partition key in queries to avoid cross-partition scans
- Use point reads (id + partition key) for lowest latency and cost
- Batch operations when possible to reduce per-request overhead
- Monitor RU consumption and adjust throughput to avoid 429 throttling

Author: Azure Bank Platform Team
Last Updated: 2024
"""

# client/cosmos_client.py
import os
import logging
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Dict, Any, Tuple

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError

# ================================================================================
# CONFIGURATION: Environment Variables with Sensible Defaults
# ================================================================================
_COSMOS_CONN = os.environ.get("COSMOS_DB_CONNECTION_STRING")
_COSMOS_DB = os.environ.get("COSMOS_DB_NAME", "operation-storage-db")

# Parallel upsert configuration
_UPSERT_WORKERS = int(os.environ.get("UPSERT_WORKERS", "8"))  # Thread pool size
_UPSERT_RETRIES = int(os.environ.get("UPSERT_RETRIES", "3"))  # Max retry attempts
_UPSERT_RETRY_BACKOFF = float(os.environ.get("UPSERT_RETRY_BACKOFF", "0.5"))  # Base backoff (seconds)

# Validate required configuration
if not _COSMOS_CONN:
    raise RuntimeError("Missing COSMOS_DB_CONNECTION_STRING env var for cosmos client")

# ================================================================================
# CLIENT INITIALIZATION: Module-Level Singleton Pattern
# ================================================================================
# CosmosClient is expensive to create (connection pool initialization).
# Reuse a single client instance across function invocations for performance.
# Azure Functions runtime keeps modules loaded between invocations (warm starts).
_client = CosmosClient.from_connection_string(_COSMOS_CONN)

# Database is created if it doesn't exist (idempotent operation)
# offer_throughput=400 sets shared database-level throughput (cost-effective for multiple containers)
_database = _client.create_database_if_not_exists(id=_COSMOS_DB, offer_throughput=400)


def get_or_create_container(container_id: str, partition_key_path: str):
    """
    Get or create a Cosmos DB container with specified partition key strategy.
    
    This function implements the "lazy initialization" pattern for container creation.
    Containers are created on-demand during first function execution, simplifying
    deployment (no separate infrastructure setup step required).
    
    Args:
        container_id (str): Container name (e.g., "ATMTransactions", "FraudAlerts")
        partition_key_path (str): Partition key path with leading slash (e.g., "/AccountNumber")
            
            Partition key considerations:
            - High cardinality: Choose keys with many distinct values (avoid hotspots)
            - Query patterns: Design for single-partition queries when possible
            - Growth: Ensure even data distribution as dataset grows
            - Immutability: Partition keys cannot be changed after container creation
    
    Returns:
        ContainerProxy: Cosmos DB container client for CRUD operations
    
    Raises:
        Exception: If container creation fails (permissions, quota limits, etc.)
    
    Performance Impact:
        - First call: Creates container (~1-2 seconds)
        - Subsequent calls: Returns existing container (<50ms)
        - Idempotent: Safe to call multiple times
    
    Partition Key Strategy Examples:
        ATM/UPI Transactions → /AccountNumber
            - Queries typically filter by account (transaction history, fraud detection)
            - Natural distribution across customer base
            - Supports efficient point reads and range queries
        
        Customer Profiles → /CustomerID
            - Enables customer 360-degree view queries
            - Co-locates customer and account data
            - Efficient for customer lifecycle operations
        
        Alerts → /AccountNumber
            - Fraud investigation queries by account
            - Co-located with related transaction data
            - Supports fast alert retrieval for customer service
    
    Design Note:
        Container throughput is shared at database level (400 RU/s).
        For dedicated throughput per container, use container.replace_throughput().
    
    Example Usage:
        atm_container = get_or_create_container("ATMTransactions", "/AccountNumber")
        item = {"id": "txn_123", "AccountNumber": "ACC001", "Amount": 5000}
        atm_container.upsert_item(item)
    """
    try:
        container = _database.create_container_if_not_exists(
            id=container_id,
            partition_key=PartitionKey(path=partition_key_path)
        )
        return container
    except Exception as e:
        logging.error(f"Failed to create/get cosmos container {container_id}: {e}")
        raise  # Re-raise to fail fast on infrastructure issues


def _sanitize_for_cosmos(obj):
    """
    Recursively convert Python datetime objects to ISO 8601 strings for Cosmos DB.
    
    Cosmos DB stores dates as strings (no native datetime type in JSON).
    ISO 8601 format ensures:
    - Timezone information is preserved
    - Lexicographic sorting matches chronological order
    - Interoperability with other systems and languages
    
    Args:
        obj: Any Python object (dict, list, datetime, primitive)
    
    Returns:
        Same object with datetime instances replaced by ISO strings
    
    Example:
        Input:  {"timestamp": datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)}
        Output: {"timestamp": "2024-01-01T10:00:00+00:00"}
    
    Performance:
        - Recursive traversal: O(n) where n = total elements in nested structure
        - Safe for typical document sizes (<1MB)
        - For very deep nesting (>100 levels), consider iterative approach
    
    Design Rationale:
        Cosmos DB SDK does not auto-serialize datetime objects.
        Manual serialization gives us control over format and timezone handling.
    """
    from datetime import datetime as _dt

    if isinstance(obj, _dt):
        return obj.isoformat()  # ISO 8601 with timezone: "2024-01-01T10:00:00+00:00"
    if isinstance(obj, dict):
        return {k: _sanitize_for_cosmos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_cosmos(x) for x in obj]
    return obj  # Primitives (str, int, float, bool, None) pass through unchanged


def _retry_op(fn, *args, **kwargs):
    """
    Execute Cosmos DB operation with exponential backoff retry logic.
    
    Cosmos DB operations can fail transiently due to:
    - 429 Rate Limiting: Request Units (RU) exceeded provisioned throughput
    - 503 Service Unavailable: Temporary backend issues
    - Network Errors: TCP connection failures, timeouts
    
    Retry Strategy: Exponential Backoff with Jitter
    - Attempt 1: Immediate execution
    - Attempt 2: Wait 0.5s (base backoff)
    - Attempt 3: Wait 1.0s (2x base backoff)
    - Attempt 4+: Wait 2.0s, 4.0s, etc.
    
    Args:
        fn: Callable to execute (e.g., container.upsert_item)
        *args: Positional arguments for fn
        **kwargs: Keyword arguments for fn
    
    Returns:
        Return value of fn on successful execution
    
    Raises:
        Last exception if all retries fail
    
    Configuration:
        _UPSERT_RETRIES: Max retry attempts (default: 3)
        _UPSERT_RETRY_BACKOFF: Base backoff in seconds (default: 0.5)
    
    Performance Impact:
        - Success on first try: No overhead
        - 429 errors: Backoff time allows throughput to recover
        - Permanent errors: Fast failure after final retry
    
    Best Practices:
        - Monitor 429 error rates in Application Insights
        - Increase provisioned RU/s if sustained throttling occurs
        - Consider implementing token bucket or circuit breaker for extreme throttling
    
    TODO: Add jitter to backoff to prevent thundering herd in concurrent scenarios
    """
    last_exc = None
    for attempt in range(1, _UPSERT_RETRIES + 1):
        try:
            return fn(*args, **kwargs)  # Execute operation
        except Exception as e:
            last_exc = e
            # Exponential backoff: wait time doubles with each retry
            sleep = _UPSERT_RETRY_BACKOFF * (2 ** (attempt - 1))
            logging.warning(f"Retry {attempt}/{_UPSERT_RETRIES} for {fn.__name__}: {e} (sleep {sleep}s)")
            time.sleep(sleep)
    
    # All retries exhausted - log and raise
    logging.error(f"Operation {fn.__name__} failed after {_UPSERT_RETRIES} attempts: {last_exc}")
    raise last_exc


def upsert_item(container, item: Dict[str, Any]) -> None:
    """
    Upsert a single document to Cosmos DB with automatic retry and serialization.
    
    Upsert semantics: Insert if document doesn't exist, update if it does.
    Document identity is determined by 'id' and partition key fields.
    
    Args:
        container: Cosmos DB container proxy (from get_or_create_container)
        item (dict): Document to upsert. Must contain:
            - 'id': Unique identifier within partition (string)
            - Partition key field (e.g., 'AccountNumber', 'CustomerID')
    
    Returns:
        None: Operation completes successfully or raises exception
    
    Raises:
        Exception: If all retry attempts fail (see _retry_op for details)
    
    Idempotency:
        Multiple calls with same id/partition key produce identical result.
        Safe for Service Bus message retries and function retries.
    
    Cost:
        - Insert: ~5 RU for 1KB document
        - Update: ~5-10 RU depending on document size and indexing policy
        - Cross-partition: Not applicable (single-partition operation)
    
    Performance:
        - Typical latency: 10-50ms within same region
        - Network overhead: ~10ms for SSL handshake (first request)
        - Throughput: Single-threaded upserts ~20-50 ops/sec
    
    Use Cases:
        - Single-record updates (real-time transactions)
        - Idempotent message processing
        - Incremental batch processing (one at a time)
    
    For batch operations, use upsert_items_parallel() for better throughput.
    
    Example:
        item = {
            "id": "txn_123",
            "AccountNumber": "ACC001",  # Partition key
            "Amount": 5000,
            "Timestamp": "2024-01-01T10:00:00Z"
        }
        upsert_item(atm_container, item)
    """
    sanitized = _sanitize_for_cosmos(item)  # Convert datetime objects to ISO strings
    _retry_op(container.upsert_item, sanitized)  # Execute with retry logic


def upsert_items_parallel(container, items: Iterable[Dict[str, Any]], workers: int = None) -> Tuple[int, int]:
    """
    Upsert multiple documents to Cosmos DB in parallel for maximum throughput.
    
    This function uses concurrent.futures.ThreadPoolExecutor to parallelize
    Cosmos DB write operations, dramatically improving throughput for batch workloads.
    
    Args:
        container: Cosmos DB container proxy (from get_or_create_container)
        items: Iterable of dictionaries to upsert (list, generator, etc.)
        workers: Thread pool size (default: _UPSERT_WORKERS from env var, typically 8)
    
    Returns:
        Tuple[int, int]: (success_count, failure_count)
            - success_count: Number of items successfully upserted
            - failure_count: Number of items that failed after all retries
    
    Behavior:
        - Each item is sanitized (datetime → ISO string)
        - Missing 'id' fields are auto-generated (timestamp-based)
        - Failed items are logged but don't stop processing
        - Returns counts for monitoring and alerting
    
    Performance Characteristics:
        - Throughput: ~100-500 upserts/sec (depends on RU/s and document size)
        - Parallelism: Optimal workers = 2-4x CPU cores (I/O-bound workload)
        - Memory: All items loaded into memory (consider chunking for >100K items)
    
    Threading Considerations:
        - Python GIL: Not a bottleneck (I/O-bound, not CPU-bound)
        - Network connections: Cosmos SDK handles connection pooling
        - Thread safety: Each thread has independent Cosmos DB client state
    
    Error Handling:
        - Individual failures are isolated (don't crash the batch)
        - Failed items are logged with full exception details
        - Consider implementing a failed items queue for manual retry
    
    Throughput Optimization:
        1. Increase workers for higher parallelism (diminishing returns >16)
        2. Increase provisioned RU/s to handle higher request rates
        3. Batch inserts into chunks if processing >100K items
        4. Monitor 429 throttling errors and adjust accordingly
    
    Cost Optimization:
        - Parallel upserts maximize RU/s utilization
        - Reduces function execution time (lower compute costs)
        - Trade-off: Higher peak RU consumption vs. lower total cost
    
    Example:
        items = [
            {"id": "txn_1", "AccountNumber": "ACC001", "Amount": 1000},
            {"id": "txn_2", "AccountNumber": "ACC002", "Amount": 2000},
            # ... thousands more
        ]
        success, failed = upsert_items_parallel(atm_container, items, workers=10)
        logging.info(f"Batch complete: {success} success, {failed} failed")
    
    TODO: Add support for batching large item lists (chunking) to reduce memory pressure
    TODO: Implement failed item queue for retry workflows
    """
    workers = workers or _UPSERT_WORKERS  # Use configured default if not specified
    successes = 0
    failures = 0
    futures = []

    def _worker(itm):
        """Inner worker function executed by each thread."""
        sanitized = _sanitize_for_cosmos(itm)  # Serialize datetime objects
        _retry_op(container.upsert_item, sanitized)  # Execute with retry logic

    with ThreadPoolExecutor(max_workers=workers) as exe:
        # Submit all upsert operations to thread pool
        for itm in items:
            # Ensure 'id' field exists (Cosmos DB requirement)
            # Auto-generate timestamp-based ID if missing
            if not itm.get("id"):
                itm["id"] = str(datetime.utcnow().timestamp())
            
            # Submit work to thread pool (non-blocking)
            futures.append(exe.submit(_worker, itm))

        # Wait for all operations to complete and collect results
        for f in as_completed(futures):
            ex = f.exception()  # Returns None if no exception occurred
            if ex:
                logging.error(f"Item upsert failed: {ex}")
                failures += 1
            else:
                successes += 1

    return successes, failures
