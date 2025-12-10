"""
Validators for transaction rows (ATM/UPI).

Provides normalization and validation rules for transaction CSV rows. Functions
return explicit error lists and cleaned/normalized dicts to help processors
decide whether to upsert or quarantine rows.

Key functions:
- _normalize_txn_type(raw) -> normalized token used in rule checks
- validate_transaction_row(row, source_type) -> (errors, cleaned_row)

Fraud/alert notes:
- Normalizing transaction types enables consistent rule application across
  slightly different vendor headers (e.g., 'Mini Statement' vs 'MiniStatement').
- Zero-amount transactions are allowed for balance inquiries; most other types
  are expected to have positive amounts and are flagged.
"""

from typing import Dict, Tuple, List, Any

from ..utils.date_utils import parse_ts
from ..utils.sanitizer import strip, to_float


def _normalize_txn_type(raw: str) -> str:
    """
    Normalize transaction type strings to a compact lowercase form.

    Behavior:
    - Returns an empty string for falsy inputs.
    - Trims whitespace, lowercases and removes common separators such as
      spaces, dashes and underscores to produce a stable token used for
      rule checks (e.g. 'Mini Statement' -> 'ministatement').

    Args:
        raw: Raw transaction type string from CSV.

    Returns:
        A normalized, compact transaction type token.
    """
    if not raw:
        return ""
    t = raw.strip().lower()
    # remove common separators and spaces
    for ch in [" ", "-", "_"]:
        t = t.replace(ch, "")
    # Inline comment: this stable token avoids brittle string comparisons in alerts
    return t


def validate_transaction_row(
    row: Dict[str, Any], source_type: str
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Validate and normalize a single transaction row from ATM or UPI sources.

    Behavior & contract:
    - Returns a tuple (errors, cleaned_row).
      * errors: list of human-readable error strings; empty when valid.
      * cleaned_row: normalized dict with canonical keys (e.g., 'Amount' as float,
        'Timestamp' as ISO string) suitable for upsert into Cosmos.
    - Does not raise on validation errors — callers decide how to handle errors
      (quarantine vs skip).

    Rules checked (non-exhaustive):
    - Presence of TransactionID
    - Amount is numeric and positive for most transaction types
    - Timestamp parses to a UTC-aware datetime

    Args:
        row: Mapping from CSV headers to raw string values.
        source_type: Source identifier (e.g., 'ATM' or 'UPI') — currently used
                     for potential source-specific rules (kept for future use).

    Returns:
        A tuple (errors, cleaned_row).
    """
    # Normalize keys and strip values (keep original header keys)
    cleaned = { (k.strip() if k else k): strip(v) for k, v in row.items() }
    errors: List[str] = []

    # Mandatory: TransactionID (support various header name variants)
    txn_id = (
        cleaned.get("TransactionID")
        or cleaned.get("TxID")
        or cleaned.get("transactionid")
        or cleaned.get("transaction_id")
    )
    if not txn_id:
        errors.append("Missing TransactionID")
    else:
        cleaned["TransactionID"] = str(txn_id).strip()

    # Transaction type normalization
    transaction_type_raw = (
        cleaned.get("TransactionType")
        or cleaned.get("Type")
        or cleaned.get("transactiontype")
        or cleaned.get("type")
    )
    transaction_type = _normalize_txn_type(transaction_type_raw)

    # Amount: support multiple header names and coerce to float
    amt = (
        cleaned.get("TransactionAmount")
        or cleaned.get("Amount")
        or cleaned.get("transactionamount")
        or cleaned.get("amount")
    )
    amt_val = to_float(amt)
    cleaned["Amount"] = amt_val

    # Allowed zero-amount transaction types (normalized tokens)
    zero_allowed = {
        "ministatement",
        "ministmt",
        "balanceenquiry",
        "balanceinquiry",
        "balanceenq",
        "balance",
    }

    if amt_val is None:
        errors.append("Invalid Amount")

    elif amt_val <= 0:
        # If this type allows zero amount, it's OK; otherwise flag as invalid
        if transaction_type not in zero_allowed:
            errors.append("Invalid or non-positive Amount")

    # Timestamp parsing using shared date utils
    ts_raw = (
        cleaned.get("TransactionTime")
        or cleaned.get("Timestamp")
        or cleaned.get("transactiontime")
        or cleaned.get("timestamp")
    )
    ts = parse_ts(ts_raw)
    if not ts:
        errors.append("Invalid Timestamp")
    else:
        # Use ISO format (UTC) for downstream storage and alerts
        cleaned["Timestamp"] = ts.isoformat()

    return errors, cleaned
