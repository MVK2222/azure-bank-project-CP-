"""
Processor for ATM transaction CSVs.

Similar to UPI processor but returns 'bad_rows' and 'header' to support quarantine
CSV generation by the caller.
"""

from typing import Dict, Any

from ..utils.csv_utils import parse_csv
from ..validator.transaction_validator import validate_transaction_row
from ..alerts.transaction_alerts import fraud_detection
from ..client.cosmos_client import upsert_item


def process_atm(text: str, file_name: str, container, alert_container) -> Dict[str, Any]:
    """
    Process ATM transaction CSV content.

    Returns a dict including counts and, when applicable, the 'bad_rows' list
    and 'header' so the caller can write a quarantine file.

    Args:
        text: CSV content as string.
        file_name: Original filename (used for naming quarantine blobs).
        container: Cosmos container client for ATM transactions.
        alert_container: Cosmos container client for alerts.

    Returns:
        A metadata dict including: rows_parsed, valid, invalid, quarantined, alerts,
        bad_rows (list of lists), and header (list of column names) when rows exist.

    Note:
        - 'bad_rows' contains rows with validation errors, aligned with the 'header'.
        - 'header' provides the column names for the CSV, useful for quarantine file generation.
    """
    # Parse CSV text into rows
    rows = parse_csv(text)
    total = len(rows)

    valid_rows = []
    bad_rows = []
    header = list(rows[0].keys()) if rows else []

    # ------------------------
    # 1. Validate & normalize
    # ------------------------
    for row in rows:
        # Validate each row and normalize the data
        errors, cleaned = validate_transaction_row(row, "ATM")
        if errors:
            # store original row values aligned with header, for quarantine
            bad_rows.append([row.get(h, "") for h in header])
        else:
            # Collect valid and normalized rows
            valid_rows.append(cleaned)

    # ------------------------
    # 2. Upsert valid rows
    # ------------------------
    for r in valid_rows:
        # Cosmos requires id to upsert the item
        r["id"] = str(r.get("TransactionID"))
        # Upsert the valid transaction record into the container
        upsert_item(container, r)

    # ------------------------
    # 3. Fraud alerts
    # ------------------------
    # Detect potential fraud alerts from the valid transaction rows
    alerts = fraud_detection(valid_rows)

    for alert in alerts:
        # Normalize alert document structure
        a = {
            "id": alert.get("alert_id"),
            "alert_id": alert.get("alert_id"),
            "type": alert.get("type"),
            "reason": alert.get("reason"),
            "created_at": alert.get("transaction", {}).get("Timestamp"),
            "payload": alert.get("transaction") or alert.get("transactions"),
            "AccountNumber": (alert.get("transaction") or {}).get("AccountNumber", "UNKNOWN"),
        }
        # Upsert the alert record into the alert container
        upsert_item(alert_container, a)

    # Return processing metadata
    return {
        "rows_parsed": total,
        "valid": len(valid_rows),
        "invalid": len(bad_rows),
        "quarantined": len(bad_rows),
        "alerts": len(alerts),
        "bad_rows": bad_rows,
        "header": header,
    }
