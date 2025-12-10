"""
Cosmos DB client helpers used by processors.

Responsibilities:
- Provide container creation helper and robust upsert helpers with retries and parallelism.
- Sanitize Python objects (datetimes) before sending to Cosmos.

Notes:
- Relies on environment variables for connection strings and config values.
"""

import os
import logging
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Dict, Any, Tuple

from azure.cosmos import CosmosClient, PartitionKey

# Env & defaults
_COSMOS_CONN = os.environ.get("COSMOS_DB_CONNECTION_STRING")
_COSMOS_DB = os.environ.get("COSMOS_DB_NAME", "operation-storage-db")
_UPSERT_WORKERS = int(os.environ.get("UPSERT_WORKERS", "8"))
_UPSERT_RETRIES = int(os.environ.get("UPSERT_RETRIES", "3"))
_UPSERT_RETRY_BACKOFF = float(os.environ.get("UPSERT_RETRY_BACKOFF", "0.5"))

if not _COSMOS_CONN:
    raise RuntimeError("Missing COSMOS_DB_CONNECTION_STRING env var for cosmos client")

_client = CosmosClient.from_connection_string(_COSMOS_CONN)
_database = _client.create_database_if_not_exists(id=_COSMOS_DB, offer_throughput=400)


# -------------------------
# container creation (Option A)
# -------------------------
def get_or_create_container(container_id: str, partition_key_path: str):
    """
    Create container if not exists and return container client.

    Args:
        container_id: The id/name of the container to create or fetch.
        partition_key_path: The partition key path for the container (e.g. "/AccountNumber").

    Returns:
        The Cosmos container client instance.

    Raises:
        Exception: Re-raises underlying exceptions after logging.
    """
    try:
        container = _database.create_container_if_not_exists(
            id=container_id,
            partition_key=PartitionKey(path=partition_key_path),
        )
        return container
    except Exception as e:
        logging.error(f"Failed to create/get cosmos container {container_id}: {e}")
        raise


# -------------------------
# Basic sanitizer: datetime -> ISO recursively
# -------------------------
def _sanitize_for_cosmos(obj: Any) -> Any:
    """
    Replace datetime objects (recursively) with ISO strings.

    This function traverses dicts and lists and converts datetime instances
    to ISO-formatted strings because Cosmos DB expects JSON-serializable values.

    Args:
        obj: The object to sanitize (can be dict, list, datetime, or primitive).

    Returns:
        A sanitized copy (or the original primitive) where datetimes are
        replaced with ISO strings.
    """
    from datetime import datetime as _dt

    if isinstance(obj, _dt):
        # Convert datetime to ISO string representation
        return obj.isoformat()
    if isinstance(obj, dict):
        # Recursively sanitize dictionary values
        return {k: _sanitize_for_cosmos(v) for k, v in obj.items()}
    if isinstance(obj, list):
        # Recursively sanitize list elements
        return [_sanitize_for_cosmos(x) for x in obj]
    # Primitives are returned unchanged
    return obj


# -------------------------
# Upsert helpers with retries & parallelism (v4 SDK friendly)
# -------------------------
def _retry_op(fn, *args, **kwargs):
    """
    Retry a callable using exponential backoff.

    Args:
        fn: Callable to execute.
        *args, **kwargs: Arguments forwarded to callable.

    Returns:
        The return value of `fn` on success.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(1, _UPSERT_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            sleep = _UPSERT_RETRY_BACKOFF * (2 ** (attempt - 1))
            logging.warning(f"Retry {attempt}/{_UPSERT_RETRIES} for {fn.__name__}: {e} (sleep {sleep}s)")
            time.sleep(sleep)
    logging.error(f"Operation {fn.__name__} failed after {_UPSERT_RETRIES} attempts: {last_exc}")
    # Re-raise the last exception so callers can handle it
    raise last_exc


def upsert_item(container, item: Dict[str, Any]) -> None:
    """
    Upsert single item with sanitization and basic retry.

    Args:
        container: Cosmos container client.
        item: Mapping to upsert. Will be sanitized (datetimes -> ISO) before upsert.

    Returns:
        None

    Raises:
        Exception if upsert ultimately fails after retries.
    """
    sanitized = _sanitize_for_cosmos(item)
    _retry_op(container.upsert_item, sanitized)


def upsert_items_parallel(
    container, items: Iterable[Dict[str, Any]], workers: int = None
) -> Tuple[int, int]:
    """
    Upsert many items in parallel using ThreadPoolExecutor.

    Behavior:
    - Ensures each item has an 'id' field (generates one based on timestamp if absent).
    - Sanitizes items before upsert.
    - Retries individual upserts using _retry_op.

    Args:
        container: Cosmos container client.
        items: Iterable of item dicts to upsert.
        workers: Optional number of parallel workers (defaults to env-configured).

    Returns:
        A tuple (success_count, fail_count).
    """
    workers = workers or _UPSERT_WORKERS
    successes = 0
    failures = 0
    futures = []

    def _worker(itm: Dict[str, Any]):
        # Local worker sanitizes and upserts a single item
        sanitized = _sanitize_for_cosmos(itm)
        _retry_op(container.upsert_item, sanitized)

    with ThreadPoolExecutor(max_workers=workers) as exe:
        for itm in items:
            # ensure an 'id' exists (Cosmos requirement)
            if not itm.get("id"):
                # Use timezone-aware UTC timestamp for id generation (collisions unlikely in this context)
                itm["id"] = str(datetime.now(timezone.utc).timestamp())
            futures.append(exe.submit(_worker, itm))

        # Collect results, count failures and successes
        for f in as_completed(futures):
            ex = f.exception()
            if ex:
                logging.error(f"Item upsert failed: {ex}")
                failures += 1
            else:
                successes += 1

    return successes, failures
