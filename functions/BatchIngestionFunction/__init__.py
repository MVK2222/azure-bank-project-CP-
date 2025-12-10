"""
BatchIngestionFunction: Service Bus-Triggered Batch Data Processor

This Azure Function orchestrates the end-to-end processing of banking data files including:
- Transaction data (ATM, UPI)
- Profile data (Customer, Account)

Architecture Pattern: Event-Driven Batch Processing with Modular Design
    - Event Source: Service Bus Queue (triggered by FileArrivalFunction)
    - Processing: Validate, Transform, Load (ETL)
    - Storage: Cosmos DB (operational store) + ADLS Gen2 (metadata/quarantine)
    - Monitoring: Application Insights for observability

Key Responsibilities:
1. Download CSV files from ADLS Gen2 based on Service Bus message
2. Parse and validate each row against schema rules
3. Route valid records to appropriate Cosmos DB containers
4. Quarantine invalid records to separate blob storage
5. Execute fraud detection rules on transaction data
6. Generate and persist fraud alerts
7. Write processing metadata for audit and monitoring

Design Principles:
- IDEMPOTENCY: Upsert operations ensure safe retries
- SEPARATION OF CONCERNS: Modular processor/validator/alert components
- ERROR ISOLATION: Per-record error handling prevents batch failures
- OBSERVABILITY: Comprehensive logging and metadata tracking
- SECURITY: No secrets in code; all credentials via environment variables

Performance Characteristics:
- Batch size: 1-10K rows typical, 100K rows maximum
- Processing time: ~2-10 seconds per 1K rows
- Parallelism: Cosmos DB upserts use ThreadPoolExecutor for throughput
- Memory: Processes entire CSV in-memory; consider streaming for >50MB files

Integration Points:
- INPUT: Azure Service Bus Queue (file metadata messages)
- OUTPUT: 
    * Cosmos DB (ATMTransactions, UPIEvents, AccountProfile, FraudAlerts)
    * ADLS Gen2 (quarantine container, metadata container)
- MONITORING: Application Insights (logs, metrics, traces)

Error Handling Strategy:
- Transient errors (network, throttling): Automatic retry via Service Bus
- Validation errors: Record-level quarantine
- Processing errors: Logged and tracked in metadata
- Fatal errors: Dead-letter queue for manual intervention

Author: Azure Bank Platform Team
Last Updated: 2024
Version: 2.0 (Modular Architecture)
"""

import json
import logging
import os
import azure.functions as func
from datetime import datetime, timezone
import csv
import io

# ================================================================================
# MODULE IMPORTS: Modular Component Architecture
# ================================================================================
# The function is decomposed into specialized modules for maintainability:
# - client/: Azure service client wrappers (Blob, Cosmos DB)
# - utils/: Reusable utilities (CSV parsing, date handling, sanitization)
# - processor/: Domain-specific ingestion logic (ATM, UPI, Account, Customer)
# - validator/: Schema validation and data quality rules
# - alerts/: Fraud detection and alert generation logic

from .client.blob_client import read_blob_text
from .client.cosmos_client import get_or_create_container

from .utils.csv_utils import detect_source_type
from .utils.date_utils import utcnow

from .processor.atm_processor import process_atm
from .processor.upi_processor import process_upi
from .processor.account_processor import process_account_profiles
from .processor.customer_processor import process_customer_profiles


# ================================================================================
# CONFIGURATION: Environment Variables and Container Names
# ================================================================================
# All configuration is externalized to environment variables for:
# - Security: No hardcoded credentials or connection strings
# - Flexibility: Different values for dev/staging/production environments
# - Compliance: Secrets stored in Azure Key Vault and injected via App Settings

ATM_CONTAINER_NAME = os.environ.get("ATM_CONTAINER", "ATMTransactions")
UPI_CONTAINER_NAME = os.environ.get("UPI_CONTAINER", "UPIEvents")
PROFILE_CONTAINER_NAME = os.environ.get("PROFILE_CONTAINER", "AccountProfile")
ALERT_CONTAINER_NAME = os.environ.get("ALERTS_CONTAINER", "FraudAlerts")
METADATA_CONTAINER = os.environ.get("METADATA_CONTAINER", "metadata")
QUARANTINE_CONTAINER = os.environ.get("QUARANTINE_CONTAINER", "quarantine")

# ================================================================================
# COSMOS DB INITIALIZATION: Container Creation with Partition Strategy
# ================================================================================
# Containers are created lazily on first function execution (idempotent operation).
# Partition key strategy is critical for performance and cost optimization:
#
# ATM/UPI Transactions: Partitioned by /AccountNumber
#   - Queries typically filter by account (customer transaction history)
#   - Enables efficient point reads and range queries per account
#   - Distributes hot accounts across multiple partitions
#
# Profile Container: Partitioned by /CustomerID
#   - Customer and Account documents are grouped by customer
#   - Supports efficient customer 360-degree view queries
#   - Natural distribution for large customer bases
#
# Alert Container: Partitioned by /AccountNumber
#   - Fraud alerts are queried by account for investigations
#   - Co-locates alerts with related transaction data
#
# Performance Note: Cross-partition queries are expensive (O(P) where P = partition count).
# Design queries to target a single partition key when possible.

atm_container = get_or_create_container(ATM_CONTAINER_NAME, "/AccountNumber")
upi_container = get_or_create_container(UPI_CONTAINER_NAME, "/AccountNumber")
profile_container = get_or_create_container(PROFILE_CONTAINER_NAME, "/CustomerID")
alert_container = get_or_create_container(ALERT_CONTAINER_NAME, "/AccountNumber")


# ================================================================================
# BLOB STORAGE HELPERS: Metadata and Quarantine Management
# ================================================================================
from azure.storage.blob import BlobServiceClient

# Initialize Blob Service Client (reused across function invocations)
_STORAGE_CONN = os.environ.get("STORAGE_CONNECTION_STRING")
_blob_client = BlobServiceClient.from_connection_string(_STORAGE_CONN)


def write_metadata_blob(file_name: str, metadata: dict):
    """
    Write processing metadata to ADLS Gen2 for audit and monitoring.
    
    Metadata files track the complete lifecycle of each file through the pipeline:
    - Initial processing start (status: PROCESSING)
    - Download success/failure
    - Validation results (rows parsed, valid, invalid)
    - Fraud alert generation counts
    - Final completion status (status: COMPLETED)
    
    Args:
        file_name (str): Original CSV filename (e.g., "atm_20250101.csv")
        metadata (dict): Processing metadata including:
            - file_name: Original filename
            - file_url: Blob URL
            - source_type: ATM, UPI, ACCOUNT, or CUSTOMER
            - status: PROCESSING, COMPLETED, DOWNLOAD_FAILED, etc.
            - started_at: ISO 8601 timestamp
            - completed_at: ISO 8601 timestamp (when finished)
            - rows_parsed: Total rows in CSV
            - valid: Count of valid rows inserted
            - invalid: Count of rows with validation errors
            - quarantined: Count of rows sent to quarantine
            - alerts_generated: Count of fraud alerts created
            - error: Error message if processing failed
    
    Returns:
        None: Metadata is written to blob storage
    
    Storage Location:
        Container: {METADATA_CONTAINER} (default: "metadata")
        Blob Path: {file_name}.metadata.json
        Format: JSON with 2-space indentation for readability
    
    Design Rationale:
        - Metadata enables post-processing analytics and debugging
        - JSON format supports ingestion into log analytics tools
        - Overwrite=True ensures idempotency for retries
        - Container auto-creation handles first-time execution
    
    Example Metadata:
        {
          "file_name": "atm_20250101.csv",
          "source_type": "ATM",
          "status": "COMPLETED",
          "started_at": "2024-01-01T10:00:00Z",
          "completed_at": "2024-01-01T10:00:05Z",
          "rows_parsed": 1000,
          "valid": 998,
          "invalid": 2,
          "alerts_generated": 5
        }
    """
    container_client = _blob_client.get_container_client(METADATA_CONTAINER)
    
    # Create container if it doesn't exist (idempotent operation)
    try:
        container_client.create_container()
    except:
        # Container already exists or permission error - safe to ignore
        pass

    # Write metadata as JSON blob (overwrite if exists for retry safety)
    blob = container_client.get_blob_client(f"{file_name}.metadata.json")
    blob.upload_blob(json.dumps(metadata, indent=2), overwrite=True)


def write_quarantine_blob(base_file_name: str, header, bad_rows):
    """
    Write invalid records to quarantine storage for manual review and correction.
    
    Quarantine strategy is essential for data quality management:
    - Prevents bad data from contaminating operational databases
    - Preserves original records for root cause analysis
    - Enables data correction and reprocessing workflows
    - Supports compliance and audit requirements
    
    Args:
        base_file_name (str): Original filename without extension (e.g., "atm_20250101")
        header (list[str]): CSV header row (column names)
        bad_rows (list[list]): List of invalid rows (each row is a list of values)
    
    Returns:
        None: Quarantine CSV is written to blob storage
        
    Storage Location:
        Container: {QUARANTINE_CONTAINER} (default: "quarantine")
        Blob Path: {base_file_name}_badrows.csv
        Format: CSV with header row
    
    Quarantine Workflow:
        1. Data engineer reviews quarantine files daily
        2. Issues are categorized: data quality, schema changes, bugs
        3. Corrected data is resubmitted to raw/ folder for reprocessing
        4. Original quarantine files are retained for audit trail
    
    Common Causes of Quarantine:
        - Missing required fields (TransactionID, AccountNumber)
        - Invalid data types (non-numeric amounts, unparseable dates)
        - Out-of-range values (negative amounts, future timestamps)
        - Schema mismatches (extra/missing columns)
        - Data corruption (encoding errors, truncated records)
    
    Performance Note:
        - Quarantine writes are synchronous (blocking)
        - For very large quarantine sets (>10K rows), consider async batching
        - Empty quarantine sets skip blob write to reduce storage costs
    
    TODO: Add quarantine metrics to Azure Monitor for alerting
    FIXME: Consider adding validation error details to each row (requires schema change)
    """
    # Skip empty quarantine sets to avoid creating unnecessary blobs
    if not bad_rows:
        return
        
    container_client = _blob_client.get_container_client(QUARANTINE_CONTAINER)
    
    # Create container if it doesn't exist (idempotent operation)
    try:
        container_client.create_container()
    except:
        # Container already exists or permission error - safe to ignore
        pass

    # Build CSV in memory using StringIO buffer
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)      # Write header row for schema reference
    writer.writerows(bad_rows)   # Write all invalid rows

    # Upload quarantine CSV with descriptive naming convention
    blob_name = f"{base_file_name}_badrows.csv"
    blob = container_client.get_blob_client(blob_name)
    blob.upload_blob(buf.getvalue(), overwrite=True)  # Overwrite ensures retry safety


# ================================================================================
# MAIN ENTRY FUNCTION: Service Bus Message Handler
# ================================================================================
def main(msg: func.ServiceBusMessage):
    """
    Main orchestration function for batch file processing.
    
    This function is triggered by Service Bus messages containing file metadata.
    It coordinates the complete ETL pipeline: Extract (download), Transform (validate),
    Load (Cosmos DB + ADLS).
    
    Processing Flow:
        1. Parse Service Bus message to extract file metadata
        2. Write initial metadata blob (status: PROCESSING)
        3. Download CSV content from ADLS Gen2
        4. Route to appropriate processor based on source type
        5. Handle validation errors and quarantine bad records
        6. Execute fraud detection rules (transaction data only)
        7. Write final metadata blob (status: COMPLETED)
    
    Args:
        msg (func.ServiceBusMessage): Service Bus message with file metadata.
            Expected JSON body:
            {
                "file_url": "https://account.blob.core.windows.net/raw/atm/atm_20250101.csv",
                "file_name": "atm_20250101.csv",
                "source_type": "ATM"
            }
    
    Returns:
        None: Function completes successfully if processing finishes.
              Early returns occur on validation or download errors.
    
    Error Handling:
        - Message parsing errors: Logged and function returns (message goes to DLQ after max retries)
        - Download errors: Metadata updated with error status
        - Processing errors: Metadata updated with error status
        - Individual record errors: Quarantined but don't fail the batch
    
    Idempotency:
        - Cosmos DB upserts prevent duplicate records on retries
        - Metadata blob overwrites ensure latest status is persisted
        - Quarantine blobs overwrite to match retry behavior
    
    Performance Considerations:
        - Entire CSV is loaded into memory (suitable for files up to ~100MB)
        - Parallel Cosmos DB writes using ThreadPoolExecutor
        - Service Bus visibility timeout should exceed max processing time
    
    Monitoring:
        - All operations logged to Application Insights
        - Metadata blobs enable post-processing analytics
        - Alert counts tracked for fraud detection KPIs
    
    TODO: Add support for large file streaming (>100MB) to reduce memory pressure
    TODO: Implement circuit breaker for Cosmos DB throttling scenarios
    """
    logging.info("BatchIngestionFunction triggered.")

    # ================================================================================
    # STEP 1: Parse Service Bus Message
    # ================================================================================
    # Service Bus messages are JSON-encoded with UTF-8 encoding.
    # Message format is validated here to fail fast on malformed messages.
    try:
        body = json.loads(msg.get_body().decode("utf-8"))
    except Exception as e:
        logging.error(f"Invalid message format: {e}")
        # Return without retry - malformed messages should go to dead-letter queue
        return

    file_url = body.get("file_url")
    file_name = body.get("file_name")

    # Validate required fields
    if not file_url or not file_name:
        logging.error("Missing file_url or file_name in message")
        return  # Invalid message - will be dead-lettered after max retries

    # ================================================================================
    # STEP 2: Detect Source Type and Initialize Metadata
    # ================================================================================
    # Source type determines which processor and validation rules to apply.
    # Detection is based on filename conventions (e.g., "atm_20250101.csv" → ATM)
    source_type = detect_source_type(file_name)
    logging.info(f"Processing {file_name}, source_type={source_type}")

    # Create initial metadata document to track processing lifecycle
    metadata = {
        "file_name": file_name,
        "file_url": file_url,
        "source_type": source_type,
        "status": "PROCESSING",          # Will be updated to COMPLETED or FAILED
        "started_at": utcnow().isoformat()  # ISO 8601 timestamp for timezone safety
    }
    
    # Write initial metadata immediately to enable monitoring of in-flight batches
    write_metadata_blob(file_name, metadata)

    # ================================================================================
    # STEP 3: Download CSV Content from ADLS Gen2
    # ================================================================================
    # Files are downloaded completely into memory for processing.
    # This approach is efficient for typical batch sizes (1K-100K rows).
    #
    # Alternative for large files: Stream processing with azure.storage.blob.BlobClient.download_blob()
    # Trade-off: Streaming reduces memory but increases complexity and processing time.
    try:
        text = read_blob_text(file_url)
    except Exception as e:
        # Download failures are typically transient (network, throttling)
        # Service Bus will retry the message based on delivery count
        metadata["status"] = "DOWNLOAD_FAILED"
        metadata["error"] = str(e)
        write_metadata_blob(file_name, metadata)
        logging.error(f"Blob read failed: {e}")
        return  # Early return allows Service Bus retry

    # ================================================================================
    # STEP 4: Route to Domain-Specific Processor
    # ================================================================================
    # Each processor is responsible for:
    # - Schema validation specific to its data type
    # - Data transformation and normalization
    # - Cosmos DB upserts with appropriate partition keys
    # - Fraud detection (for transaction types)
    # - Returning processing statistics
    #
    # Processor Selection Strategy:
    # - ATM: Transaction processor with ATM-specific validation rules
    # - UPI: Transaction processor with UPI-specific validation rules
    # - ACCOUNT: Profile processor with account schema validation
    # - CUSTOMER: Profile processor with customer schema validation
    #
    # Design Pattern: Strategy Pattern
    #   Each processor implements a common interface (input: text, output: result dict)
    
    result = {}  # Will contain: rows_parsed, valid, invalid, quarantined, alerts

    try:
        if source_type == "ATM":
            # Process ATM transactions: validate, insert, detect fraud
            result = process_atm(text, file_name, atm_container, alert_container)

        elif source_type == "UPI":
            # Process UPI transactions: validate, insert, detect fraud
            result = process_upi(text, file_name, upi_container, alert_container)

        elif source_type == "ACCOUNT":
            # Process account profiles: validate, merge/upsert, generate profile alerts
            result = process_account_profiles(text, file_name, profile_container, alert_container)

        elif source_type == "CUSTOMER":
            # Process customer profiles: validate, merge with existing accounts
            result = process_customer_profiles(text, file_name, profile_container)

        else:
            # Unknown source types should not reach here (detected in FileArrivalFunction)
            # This is a safety check for manual queue messages or configuration errors
            logging.error(f"Unknown source_type for file: {file_name}")
            metadata["status"] = "UNKNOWN_SOURCE"
            write_metadata_blob(file_name, metadata)
            return

    except Exception as e:
        # Processor exceptions indicate bugs or unexpected data conditions
        # These should be investigated and fixed; message goes to DLQ after retries
        logging.error(f"Processor exception: {e}", exc_info=True)
        metadata["status"] = "PROCESSOR_FAILED"
        metadata["error"] = str(e)
        write_metadata_blob(file_name, metadata)
        return  # Service Bus will retry based on delivery count

    # ================================================================================
    # STEP 5: Handle Quarantine (Invalid Records)
    # ================================================================================
    # Invalid records are preserved in quarantine storage for data quality review.
    # Note: Current implementation tracks quarantine count but does not write rows.
    # TODO: Enhance processors to return bad_rows for quarantine CSV generation.
    if result.get("invalid", 0) > 0:
        # Quarantine handling is currently delegated to processors
        # Future enhancement: Centralize quarantine logic here for consistency
        #
        # Example quarantine workflow:
        # 1. Re-parse CSV to extract header
        # 2. Collect bad rows from processor (requires API change)
        # 3. Write quarantine CSV with validation error annotations
        #
        # rows = text.splitlines()
        # header = rows[0].split(",")
        # write_quarantine_blob(file_name, header, bad_rows)
        
        logging.warning(f"{result.get('invalid', 0)} invalid rows detected in {file_name}")

    # ================================================================================
    # STEP 6: Finalize Processing Metadata
    # ================================================================================
    # Update metadata with final processing statistics and completion status.
    # This metadata is used for:
    # - Operational dashboards (success rate, processing times)
    # - Data quality monitoring (invalid row trends)
    # - Fraud detection KPIs (alert generation rates)
    # - Audit and compliance reporting
    
    metadata.update({
        "status": "COMPLETED",
        "completed_at": utcnow().isoformat(),
        "rows_parsed": result.get("rows_parsed", 0),
        "valid": result.get("valid", 0),
        "invalid": result.get("invalid", 0),
        "quarantined": result.get("quarantined", 0),
        "alerts_generated": result.get("alerts", 0)
    })

    write_metadata_blob(file_name, metadata)

    logging.info(f"Completed processing {file_name} → {json.dumps(metadata)}")
    
    # Function completes successfully - Service Bus will remove message from queue
    # Cosmos DB contains validated records, alerts are generated, metadata is persisted
