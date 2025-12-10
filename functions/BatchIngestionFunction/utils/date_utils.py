"""
date_utils.py: Timezone-Aware DateTime Parsing and Utilities

This module provides robust datetime parsing and manipulation with a focus on
timezone awareness - critical for banking systems operating across multiple regions.

Key Principles:
- ALWAYS timezone-aware: Naive datetimes are a source of bugs
- UTC normalization: All timestamps stored in UTC for consistency
- Flexible parsing: Handles multiple datetime formats automatically
- Defensive programming: Returns None on parse failure (no exceptions)

Timezone Importance in Banking:
- Transaction ordering: Ensure correct chronological sequence across time zones
- Fraud detection: Accurate time windows for velocity and geo-location rules
- Compliance: Regulatory reporting requires precise timestamps
- Customer experience: Display local time while storing UTC internally

Common Datetime Formats Handled:
- ISO 8601: "2024-01-01T10:00:00Z" (recommended)
- ISO with offset: "2024-01-01T10:00:00+05:30"
- Date only: "2024-01-01" (assumed start of day UTC)
- US format: "01/01/2024 10:00:00"
- European format: "01-01-2024 10:00:00"
- Natural language: "Jan 1, 2024" (via dateutil.parser)

Dependencies:
- python-dateutil: Robust datetime parsing library
- datetime: Standard library for timezone handling

Author: Azure Bank Platform Team
Last Updated: 2024
"""

# utils/date_utils.py
from datetime import datetime, timezone
import logging
from dateutil import parser as date_parser


def parse_ts(value):
    """
    Parse timestamp string into timezone-aware UTC datetime.
    
    This function is the single source of truth for datetime parsing across
    the banking platform. It ensures all timestamps are normalized to UTC
    for consistent storage and comparison.
    
    Args:
        value (str): Timestamp string in any common format.
            Supported formats (via dateutil.parser):
            - ISO 8601: "2024-01-01T10:00:00Z", "2024-01-01T10:00:00+05:30"
            - Date only: "2024-01-01" (time defaults to 00:00:00)
            - Slash format: "01/01/2024", "01/01/2024 10:00:00"
            - Dash format: "01-01-2024", "01-01-2024 10:00:00"
            - Natural: "Jan 1, 2024", "January 1, 2024"
            - Epoch: Not supported (add if needed)
    
    Returns:
        datetime: Timezone-aware datetime in UTC
        None: If value is empty, None, or unparseable
    
    Timezone Handling:
        1. If input has timezone info: Convert to UTC
        2. If input is naive (no timezone): Assume UTC
        3. Always return UTC-aware datetime
    
    Examples:
        parse_ts("2024-01-01T10:00:00Z") 
            → datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC)
        
        parse_ts("2024-01-01T10:00:00+05:30")
            → datetime(2024, 1, 1, 4, 30, 0, tzinfo=UTC)  # Converted to UTC
        
        parse_ts("2024-01-01")
            → datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        
        parse_ts("01/01/2024 15:30:00")
            → datetime(2024, 1, 1, 15, 30, 0, tzinfo=UTC)
        
        parse_ts("invalid")
            → None
        
        parse_ts(None)
            → None
        
        parse_ts("")
            → None
    
    Use Cases:
        - Transaction timestamps: ATM, UPI transaction times
        - Account dates: Account open date, last modified date
        - Customer DOB: Date of birth parsing
        - Alert timestamps: When fraud alert was generated
    
    Error Handling:
        - Parse failure: Log warning, return None
        - None input: Return None immediately
        - Empty string: Return None immediately
        - Invalid formats: dateutil.parser handles gracefully
    
    Performance:
        - dateutil.parser is slower than strptime (10-100x)
        - Trade-off: Flexibility vs speed
        - Typical: 1-5ms per parse
        - For high-performance scenarios: Pre-validate format, use strptime
    
    Timezone Best Practices:
        - Storage: Always UTC in Cosmos DB (ISO string)
        - Display: Convert to user's local timezone in UI/reports
        - Comparison: Compare UTC datetimes directly
        - Serialization: Use .isoformat() for JSON/string conversion
    
    Common Pitfalls:
        - Naive datetimes: Can't compare with aware datetimes (TypeError)
        - Timezone assumptions: Never assume local time zone
        - DST issues: UTC avoids daylight saving time complexity
        - Format ambiguity: "01/02/2024" (Jan 2 or Feb 1?) - prefer ISO 8601
    
    TODO: Add option to specify default timezone (instead of UTC assumption)
    TODO: Add support for Unix epoch timestamps (seconds/milliseconds)
    TODO: Add strict mode (raise exception instead of returning None)
    """
    if not value:
        return None  # Empty or None input

    try:
        # Use dateutil.parser for maximum flexibility
        # Handles dozens of datetime formats automatically
        dt = date_parser.parse(value)
    except Exception:
        # Parse failed - log for debugging and return None
        logging.warning(f"Failed to parse datetime: {value}")
        return None

    # ================================================================================
    # CRITICAL: Ensure Timezone Awareness
    # ================================================================================
    # Naive datetimes (no timezone) are dangerous in distributed systems.
    # Always attach UTC timezone to prevent ambiguity.
    
    if dt.tzinfo is None:
        # Naive datetime - assume UTC for safety
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        # Has timezone - convert to UTC for normalization
        dt = dt.astimezone(timezone.utc)

    return dt


def utcnow():
    """
    Get current UTC datetime with timezone awareness.
    
    Returns:
        datetime: Current time in UTC with timezone info
    
    Usage:
        - Timestamp generation: metadata["created_at"] = utcnow().isoformat()
        - Duration calculation: elapsed = utcnow() - start_time
        - Expiry checks: if utcnow() > expiry_time: ...
    
    Alternative:
        datetime.utcnow() - Returns naive datetime (BAD - avoid)
        datetime.now(timezone.utc) - Returns aware datetime (GOOD - use this)
    
    Example:
        utcnow() → datetime(2024, 1, 1, 10, 30, 45, tzinfo=UTC)
        utcnow().isoformat() → "2024-01-01T10:30:45+00:00"
    
    Design Note:
        This wrapper function ensures consistent timezone-aware datetime
        generation across the codebase. Prevents accidental use of naive datetime.now().
    """
    return datetime.now(timezone.utc)
