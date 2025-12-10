"""
Azure Function handler for batch ingestion pipeline.

This module wires blob read, source detection and dispatch to specialized
processors (ATM, UPI, Account, Customer). It also writes metadata and
quarantine blobs into storage.

Environment variables used (from module scope):
- STORAGE_CONNECTION_STRING
- ATM_CONTAINER, UPI_CONTAINER, PROFILE_CONTAINER, ALERTS_CONTAINER
- METADATA_CONTAINER, QUARANTINE_CONTAINER
"""

import json
import logging
import os
import azure.functions as func
import csv
import io

# ------------------------------
# Import our new modular files
# ------------------------------
from .client.blob_client import read_blob_text
from .client.cosmos_client import get_or_create_container

from .utils.csv_utils import detect_source_type
from .utils.date_utils import utcnow

from .processor.atm_processor import process_atm
from .processor.upi_processor import process_upi
from .processor.account_processor import process_account_profiles
from .processor.customer_processor import process_customer_profiles


# -------------------------------------------------------------------
# Containers created ONCE (Option A — centralized creation)
# -------------------------------------------------------------------
ATM_CONTAINER_NAME = os.environ.get("ATM_CONTAINER", "ATMTransactions")
UPI_CONTAINER_NAME = os.environ.get("UPI_CONTAINER", "UPIEvents")
PROFILE_CONTAINER_NAME = os.environ.get("PROFILE_CONTAINER", "AccountProfile")
ALERT_CONTAINER_NAME = os.environ.get("ALERTS_CONTAINER", "FraudAlerts")
METADATA_CONTAINER = os.environ.get("METADATA_CONTAINER", "metadata")
QUARANTINE_CONTAINER = os.environ.get("QUARANTINE_CONTAINER", "quarantine")

# Cosmos DB containers (created on import)
atm_container = get_or_create_container(ATM_CONTAINER_NAME, "/AccountNumber")
upi_container = get_or_create_container(UPI_CONTAINER_NAME, "/AccountNumber")
profile_container = get_or_create_container(PROFILE_CONTAINER_NAME, "/CustomerID")
alert_container = get_or_create_container(ALERT_CONTAINER_NAME, "/AccountNumber")


# -------------------------------------------------------------------
# Helper: write metadata JSON to blob storage
# -------------------------------------------------------------------
from azure.storage.blob import BlobServiceClient
_STORAGE_CONN = os.environ.get("STORAGE_CONNECTION_STRING")
_blob_client = BlobServiceClient.from_connection_string(_STORAGE_CONN)


def write_metadata_blob(file_name: str, metadata: dict):
    """
    Persist metadata JSON blob for a processed file.

    Args:
        file_name: Base filename used to name the metadata blob.
        metadata: Arbitrary metadata mapping to be JSON serialized.
    """
    container_client = _blob_client.get_container_client(METADATA_CONTAINER)
    try:
        # create_container may fail if it already exists — ignore errors
        container_client.create_container()
    except Exception:
        pass

    blob = container_client.get_blob_client(f"{file_name}.metadata.json")
    blob.upload_blob(json.dumps(metadata, indent=2), overwrite=True)


# -------------------------------------------------------------------
# Helper: write quarantine CSV
# -------------------------------------------------------------------
def write_quarantine_blob(base_file_name: str, header, bad_rows):
    """
    Persist a quarantine CSV containing header and bad rows.

    Args:
        base_file_name: Source filename used for naming the quarantine blob.
        header: List of column names.
        bad_rows: Iterable of row lists (aligned with header) to write.
    """
    if not bad_rows:
        return
    container_client = _blob_client.get_container_client(QUARANTINE_CONTAINER)
    try:
        container_client.create_container()
    except Exception:
        pass

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(bad_rows)

    blob_name = f"{base_file_name}_badrows.csv"
    blob = container_client.get_blob_client(blob_name)
    blob.upload_blob(buf.getvalue(), overwrite=True)


# -------------------------------------------------------------------
# MAIN ENTRY FUNCTION
# -------------------------------------------------------------------
def main(msg: func.ServiceBusMessage):
    """
    Azure Function entrypoint triggered by Service Bus messages produced by the FileArrivalFunction.

    Expected message body (JSON): {"file_url": <blob_url>, "file_name": <filename>, "source_type": <optional>}.

    Flow:
    - Read message and download blob content
    - Detect source type and dispatch to appropriate processor
    - Handle quarantine blobs and persist metadata

    Error handling:
    - Failures are logged and metadata is updated with status and error text.
    """
    logging.info("BatchIngestionFunction triggered.")

    # -----------------------------
    # Read service bus message
    # -----------------------------
    try:
        body = json.loads(msg.get_body().decode("utf-8"))
    except Exception as e:
        logging.error(f"Invalid message: {e}")
        return

    file_url = body.get("file_url")
    file_name = body.get("file_name")

    if not file_url or not file_name:
        logging.error("Missing file_url or file_name in message")
        return

    # Identify source type
    source_type = detect_source_type(file_name)
    logging.info(f"Processing {file_name}, source_type={source_type}")

    # Initial metadata
    metadata = {
        "file_name": file_name,
        "file_url": file_url,
        "source_type": source_type,
        "status": "PROCESSING",
        "started_at": utcnow().isoformat(),
    }
    write_metadata_blob(file_name, metadata)

    # -----------------------------
    # Download blob CSV content
    # -----------------------------
    try:
        text = read_blob_text(file_url)
    except Exception as e:
        metadata["status"] = "DOWNLOAD_FAILED"
        metadata["error"] = str(e)
        write_metadata_blob(file_name, metadata)
        logging.error(f"Blob read failed: {e}")
        return

    # -----------------------------
    # DISPATCH TO PROCESSOR
    # -----------------------------
    result = {}

    try:
        if source_type == "ATM":
            result = process_atm(text, file_name, atm_container, alert_container)

        elif source_type == "UPI":
            result = process_upi(text, file_name, upi_container, alert_container)

        elif source_type == "ACCOUNT":
            result = process_account_profiles(text, file_name, profile_container, alert_container)

        elif source_type == "CUSTOMER":
            result = process_customer_profiles(text, file_name, profile_container)

        else:
            logging.error(f"Unknown source_type for file: {file_name}")
            metadata["status"] = "UNKNOWN_SOURCE"
            write_metadata_blob(file_name, metadata)
            return

    except Exception as e:
        logging.error(f"Processor exception: {e}")
        metadata["status"] = "PROCESSOR_FAILED"
        metadata["error"] = str(e)
        write_metadata_blob(file_name, metadata)
        return

    # ---------------------------------
    # Handle quarantine (if any)
    # ---------------------------------
    # processors now return 'bad_rows' and 'header' for quarantine
    bad_rows = result.get("bad_rows")
    header = result.get("header")
    if bad_rows and header:
        try:
            write_quarantine_blob(file_name, header, bad_rows)
            logging.info(f"Wrote {len(bad_rows)} bad rows to quarantine for {file_name}")
        except Exception as e:
            logging.error(f"Failed to write quarantine blob: {e}")


    # ---------------------------------
    # Finalize metadata
    # ---------------------------------
    metadata.update(
        {
            "status": "COMPLETED",
            "completed_at": utcnow().isoformat(),
            "rows_parsed": result.get("rows_parsed", 0),
            "valid": result.get("valid", 0),
            "invalid": result.get("invalid", 0),
            "quarantined": result.get("quarantined", 0),
            "alerts_generated": result.get("alerts", 0),
        }
    )

    write_metadata_blob(file_name, metadata)

    logging.info(f"Completed processing {file_name} → {json.dumps(metadata)}")
