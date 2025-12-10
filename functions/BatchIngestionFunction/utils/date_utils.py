"""
Date-time utilities used across validators and processors.

Provides helpers to normalize vendor-specific datetime strings and to return
UTC-aware datetimes for consistent downstream processing.
"""

# utils/date_utils.py
from datetime import datetime, timezone
from dateutil import parser as date_parser
import logging
import re
from typing import Optional

# Pre-compiled regex to detect time strings with a dot separator (e.g. '14.16').
_HH_MM_DOT_RE = re.compile(r"\b(\d{1,2})\.(\d{2})\b")


def _normalize_datetime_string(value: Optional[str]) -> Optional[str]:
    """
    Normalize common non-standard datetime strings produced by some vendors.

    What this function does:
    - Returns falsy inputs (None or empty) unchanged.
    - Trims surrounding whitespace.
    - Detects and converts time portions that use a dot as a separator
      (e.g. '14.16' or '9.51') into colon-separated form ('14:16', '9:51').

    Args:
        value: Raw datetime string that may contain vendor-specific quirks.

    Returns:
        The normalized datetime string suitable for parsing by dateutil, or
        the original falsy input when provided.

    Notes:
        - This function only rewrites obvious time-separator issues; it does
          not attempt to fully validate the date/time semantics.
    """
    # Return early for None or empty strings
    if not value:
        return value

    # Trim whitespace to avoid parse issues from leading/trailing spaces
    value = value.strip()

    # Look for patterns like '14.16' and convert to '14:16'
    match = _HH_MM_DOT_RE.search(value)
    if match:
        hour = match.group(1)
        minute = match.group(2)
        # Replace only the matched substring to preserve other characters
        fixed = value.replace(match.group(0), f"{hour}:{minute}")
        return fixed

    # No change necessary
    return value


def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """
    Parse a timestamp string into a UTC-aware datetime object.

    Behavior:
    - Returns None for falsy inputs.
    - Normalizes common vendor-specific formats before parsing.
    - Uses dateutil.parser.parse with dayfirst=True to support DD-MM-YYYY
      style dates commonly found in CSVs.
    - If the parsed datetime is naive (no tzinfo), it is assumed to be UTC;
      timezone-aware datetimes are converted to UTC.

    Args:
        value: Timestamp string to parse (may be None).

    Returns:
        A timezone-aware datetime set to UTC on success, or None if parsing
        fails or input is falsy.

    Logs:
        A warning is emitted when dateutil fails to parse the string.
    """
    if not value:
        return None

    # Normalize vendor quirks (e.g. dot-separated times) before parsing
    value = _normalize_datetime_string(value)

    try:
        # Use dayfirst=True because many CSVs use a DD-MM-YYYY layout
        dt = date_parser.parse(value, dayfirst=True)
    except Exception:
        logging.warning(f"Failed to parse datetime: {value}")
        return None

    # Ensure the returned datetime is timezone-aware and in UTC
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC (explicit)
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # Convert any provided timezone to UTC for consistent downstream handling
        dt = dt.astimezone(timezone.utc)

    return dt


def utcnow() -> datetime:
    """
    Return the current UTC time as a timezone-aware datetime.

    Returns:
        A timezone-aware datetime representing the current time in UTC.
    """
    # datetime.now(timezone.utc) returns an aware datetime in UTC
    return datetime.now(timezone.utc)
