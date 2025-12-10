"""
Small sanitization helpers used across validators and processors.

Responsibilities:
- Provide safe conversions and trimming helpers (strip, to_float, to_bool).

Notes:
- These helpers return None when conversion isn't possible, which callers
  interpret as validation failures.
"""

from typing import Any, Optional


def strip(value: Any) -> Any:
    """
    Safely strip whitespace from string values.

    Args:
        value: Value to strip. If it's a string, returns the trimmed string.
               Non-string values are returned unchanged.

    Returns:
        The trimmed string when input is a str, otherwise the original value.

    Examples:
        strip('  hello ') -> 'hello'
        strip(None) -> None
    """
    if isinstance(value, str):
        # Inline comment: use built-in strip to remove whitespace from both ends
        return value.strip()
    # Non-strings are returned unchanged (e.g., numbers, booleans)
    return value


def to_float(value: Any) -> Optional[float]:
    """
    Convert a value to float safely.

    Behavior:
    - Returns None when conversion is not possible or input is None.
    - For string inputs, common thousands separators (commas) are removed
      before conversion.

    Args:
        value: The value to convert (str, int, float, etc.).

    Returns:
        A float on successful conversion, or None on failure.

    Examples:
        to_float('1,234.56') -> 1234.56
        to_float('abc') -> None
    """
    if value is None:
        return None

    try:
        if isinstance(value, str):
            # Remove thousands separators and trim whitespace
            # Inline comment: this supports values like '1,234.56' or ' 1234 '
            value = value.replace(",", "").strip()
        return float(value)
    except Exception:
        # Conversion failed — return None so callers can treat as invalid
        return None


def to_bool(value: Any) -> Optional[bool]:
    """
    Convert common truthy/falsy representations to boolean.

    Supported truthy values: 'yes', 'true', '1', 'y' (case-insensitive)
    Supported falsy values: 'no', 'false', '0', 'n' (case-insensitive)

    Args:
        value: Input value to coerce.

    Returns:
        True/False if recognizable, otherwise None for ambiguous values.

    Examples:
        to_bool('Yes') -> True
        to_bool('0') -> False
        to_bool('maybe') -> None
    """
    if value is None:
        return None

    if isinstance(value, bool):
        # Already a boolean - return as-is
        return value

    s = str(value).strip().lower()
    if s in ["yes", "true", "1", "y"]:
        return True
    if s in ["no", "false", "0", "n"]:
        return False

    # Ambiguous value - caller should treat None as invalid/unparseable
    return None
