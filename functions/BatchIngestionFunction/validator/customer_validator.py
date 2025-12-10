"""
Validators for customer_master rows.

Validates key customer fields such as CustomerID, DOB, and AnnualIncome.

This module is used by the customer processor to determine whether a row
should be upserted into the profile container or quarantined.
"""

from typing import Dict, List, Any

from ..utils.sanitizer import strip, to_float
from ..utils.date_utils import parse_ts


def validate_customer_row(row: Dict[str, Any]) -> List[str]:
    """
    Validate a single customer CSV row.

    Behavior:
    - Checks for presence of CustomerID.
    - Validates DOB can be parsed to a datetime.
    - Validates AnnualIncome can be converted to float.

    Args:
        row: Mapping of CSV headers to values for a single customer.

    Returns:
        A list of error messages. Empty list implies the row is valid.
    """

    errors: List[str] = []

    cust_id = strip(row.get("CustomerID"))
    if not cust_id:
        errors.append("Missing CustomerID")

    # Valid DOB — parse using shared utility which handles vendor quirks
    dob = parse_ts(row.get("DOB"))
    if dob is None:
        errors.append("Invalid DOB")

    # Annual Income must be numeric
    inc = to_float(row.get("AnnualIncome"))
    if inc is None:
        errors.append("Invalid AnnualIncome")

    return errors
