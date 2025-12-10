"""
Processor for UPI transaction CSVs.

Flow:
- Parse CSV text, validate rows via transaction validator.
- Upsert valid transactions into Cosmos container.
- Run fraud detection and persist alerts into alert container.

Returns a metadata dictionary summarizing processing results.
"""

from typing import Dict, Any

from ..utils.csv_utils import parse_csv
from ..validator.transaction_validator import validate_transaction_row
from ..alerts.transaction_alerts import fraud_detection
from ..client.cosmos_client import upsert_item


def process_upi(text: str, file_name: str, container, alert_container) -> Dict[str, Any]:
    """
    Process UPI transaction CSV content and persist results.

    Steps:
    1. Parse CSV and validate rows.
    2. Upsert valid rows into Cosmos container.
    3. Run fraud detection and persist alerts.

    Args:
        text: CSV content as string.
        file_name: Original filename (used for metadata/quarantine naming).
        container: Cosmos container client for UPI events.
        alert_container: Cosmos container client for alerts.

    Returns:
        A metadata dict with counts: rows_parsed, valid, invalid, quarantined, alerts.
    """
    # 1) Parse CSV text into a list of dict rows
    rows = parse_csv(text)
    total = len(rows)

    valid_rows = []
    bad_rows = []

    # ------------------------
    # 1. Validate
    # ------------------------
    for row in rows:
        errors, cleaned = validate_transaction_row(row, "UPI")
        if errors:
            # keep original row for potential quarantine or debugging
            bad_rows.append(row)
        else:
            valid_rows.append(cleaned)

    # ------------------------
    # 2. Upsert valid rows
    # ------------------------
    for r in valid_rows:
        # Cosmos requires id; use TransactionID as stable id
        r["id"] = str(r.get("TransactionID"))
        upsert_item(container, r)

    # ------------------------
    # 3. Fraud detection
    # ------------------------
    alerts = fraud_detection(valid_rows)

    for alert in alerts:
        # Normalize alert document structure for Cosmos
        a = {
            "id": alert.get("alert_id"),
            "alert_id": alert.get("alert_id"),
            "type": alert.get("type"),
            "reason": alert.get("reason"),
            "created_at": alert.get("transaction", {}).get("Timestamp"),
            "payload": alert.get("transaction") or alert.get("transactions"),
            "AccountNumber": alert.get("transaction", {}).get("AccountNumber", "UNKNOWN"),
        }
        upsert_item(alert_container, a)

    return {
        "rows_parsed": total,
        "valid": len(valid_rows),
        "invalid": len(bad_rows),
        "quarantined": len(bad_rows),
        "alerts": len(alerts),
    }
