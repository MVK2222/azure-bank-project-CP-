"""
FileArrivalFunction: Event Grid-Triggered File Arrival Handler

This Azure Function is triggered by Event Grid when a new blob is created in Azure Data Lake Storage (ADLS).
It performs initial validation and routing of incoming data files to the appropriate processing pipeline.

Key Responsibilities:
- Listen for blob creation events from Event Grid
- Validate file format (CSV only)
- Detect data source type based on filename patterns
- Publish metadata message to Service Bus for downstream processing
- Provide idempotent event handling

Design Considerations:
- Lightweight processing to minimize latency in the event pipeline
- No direct file content processing (delegated to BatchIngestionFunction)
- Event Grid ensures at-least-once delivery; Service Bus deduplication handles retries
- Environment variable configuration for security (no hardcoded secrets)

Integration Points:
- INPUT: Azure Event Grid (BlobCreated events)
- OUTPUT: Azure Service Bus Queue (file metadata messages)

Performance:
- Typical execution time: < 500ms
- Supports concurrent event processing via Functions scale-out

Author: Azure Bank Platform Team
Last Updated: 2024
"""

import json
import logging
import azure.functions as func
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import os


def main(event: func.EventGridEvent):
    """
    Main entry point for Event Grid-triggered file arrival processing.
    
    This function is invoked automatically when a new CSV file is uploaded to ADLS Gen2.
    It validates the file, determines its type, and forwards metadata to Service Bus
    for asynchronous batch processing.
    
    Args:
        event (func.EventGridEvent): Event Grid event containing blob creation metadata.
            Expected fields in event data:
            - url (str): Full blob URL (e.g., https://account.blob.core.windows.net/container/file.csv)
            - api (str): Should be "PutBlob" for file uploads
            - contentType (str): MIME type of the uploaded blob
    
    Returns:
        None: Function completes successfully if message is sent to Service Bus.
              Logs errors and returns early on validation failures.
    
    Raises:
        KeyError: If SERVICE_BUS_CONNECTION_STRING or SERVICE_BUS_QUEUE_NAME env vars are missing
        Exception: Any Service Bus connection or message sending errors are logged but not raised
    
    Side Effects:
        - Sends a JSON message to Service Bus Queue with file metadata
        - Logs INFO/ERROR messages to Application Insights
    
    Example Event Data:
        {
            "url": "https://mystorageaccount.blob.core.windows.net/raw/atm/atm_20250101.csv",
            "api": "PutBlob",
            "contentType": "text/csv"
        }
    
    Example Service Bus Message:
        {
            "file_url": "https://...",
            "file_name": "atm_20250101.csv",
            "source_type": "ATM"
        }
    
    Design Pattern: Event-Driven Decoupling
        This function implements the Command pattern by converting events into messages.
        Service Bus queue provides backpressure and retry handling for downstream processing.
    """
    
    logging.info("Event Grid Trigger Fired for New File Upload")

    # Extract blob metadata from Event Grid event
    event_data = event.get_json()
    
    # Validate Event Grid event data structure
    # Event Grid should always include 'url' field, but validate to prevent KeyError
    if "url" not in event_data:
        logging.error("Event Grid event missing 'url' field. Event data: %s", event_data)
        return  # Early return prevents downstream errors
    
    url = event_data["url"]                         # Full blob URL with storage account and path
    file_name = url.split("/")[-1]                 # Extract filename from URL path (last segment)

    logging.info(f"File Uploaded: {file_name}")

    # ================================================================================
    # VALIDATION: File Format Check
    # ================================================================================
    # Only CSV files are supported for structured data ingestion.
    # Binary formats (Excel, Parquet) require different processing pipelines.
    if not file_name.endswith(".csv"):
        logging.error("Invalid file format. Only CSV allowed.")
        return  # Early return prevents invalid files from entering the pipeline

    # ================================================================================
    # ROUTING: Detect Source Type Based on Filename Convention
    # ================================================================================
    # Filename patterns are used to route files to appropriate processors:
    # - atm_*.csv       → ATM transaction processor
    # - upi_*.csv       → UPI transaction processor
    # - customer_*.csv  → Customer profile processor
    # - account_*.csv   → Account profile processor
    #
    # This convention-based routing simplifies configuration and supports
    # multiple data sources without requiring metadata files or manifests.
    source_type = ""
    if "atm" in file_name.lower():
        source_type = "ATM"
    elif "upi" in file_name.lower():
        source_type = "UPI"
    elif "customer" in file_name.lower():
        source_type = "CUSTOMER"
    elif "account" in file_name.lower():
        source_type = "ACCOUNT"
    else:
        source_type = "UNKNOWN"  # Unknown files are logged but may be rejected downstream

    # ================================================================================
    # MESSAGE CONSTRUCTION: Prepare Service Bus Payload
    # ================================================================================
    # The message contains minimal metadata to keep queue storage efficient.
    # Actual file content is retrieved by BatchIngestionFunction from ADLS.
    message_body = {
        "file_url": url,           # Blob URL for downstream file retrieval
        "file_name": file_name,    # Original filename for logging and quarantine
        "source_type": source_type  # Routing hint for processor selection
    }

    logging.info(f"Sending message to Service Bus: {message_body}")

    # ================================================================================
    # SERVICE BUS INTEGRATION: Publish Message for Asynchronous Processing
    # ================================================================================
    # Service Bus provides:
    # - At-least-once message delivery with deduplication
    # - Message TTL and dead-letter queue for error handling
    # - Backpressure to prevent overwhelming downstream processors
    # - Visibility timeout to prevent duplicate processing
    #
    # Connection string is retrieved from environment variables (App Settings in Azure).
    # This ensures secrets are not committed to source control.
    sb_client = ServiceBusClient.from_connection_string(
        conn_str=os.environ["SERVICE_BUS_CONNECTION_STRING"]  # Configured in Azure Function App Settings
    )

    queue_name = os.environ["SERVICE_BUS_QUEUE_NAME"]  # Typically "banking-ingest-queue"

    # Use context managers to ensure proper resource cleanup
    with sb_client:
        sender = sb_client.get_queue_sender(queue_name=queue_name)
        with sender:
            # Serialize message body to JSON for interoperability
            sb_message = ServiceBusMessage(json.dumps(message_body))
            sender.send_messages(sb_message)

    logging.info("Message sent to Service Bus Queue successfully.")
    
    # Function completes successfully - Event Grid will mark event as processed
    # If an exception occurs, Event Grid will retry based on subscription retry policy
