"""
Validators for account_master rows.

Checks for required identifiers (AccountNumber, CustomerID) and validates
Balance and AccountOpenDate.
"""

from typing import Dict, List, Any

from ..utils.sanitizer import strip, to_float
from ..utils.date_utils import parse_ts


def validate_account_row(row: Dict[str, Any]) -> List[str]:
    """
    Validate a single account CSV row.

    Behavior:
    - Ensures AccountNumber and CustomerID are present.
    - Validates Balance can be converted to float.
    - Validates AccountOpenDate can be parsed to a datetime.

    Args:
        row: Mapping of CSV headers to raw values.

    Returns:
        A list of error strings; empty list indicates the row is valid.
    """

    errors: List[str] = []
    acc = strip(row.get("AccountNumber"))
    cust = strip(row.get("CustomerID"))

    if not acc:
        errors.append("Missing AccountNumber")
    if not cust:
        errors.append("Missing CustomerID")

    # Balance must be numeric
    bal = to_float(row.get("Balance"))
    if bal is None:
        errors.append("Invalid Balance")

    # AccountOpenDate should parse successfully; parse_ts handles vendor quirks
    dt = parse_ts(row.get("AccountOpenDate"))
    if dt is None:
        errors.append("Invalid AccountOpenDate")

    return errors
