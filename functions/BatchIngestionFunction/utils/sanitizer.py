"""
sanitizer.py: Data Type Conversion and Sanitization Utilities

This module provides safe, fault-tolerant data type conversions for CSV data processing.
It handles common data quality issues found in real-world banking datasets:
- Extra whitespace and formatting characters
- Inconsistent boolean representations
- Numeric values with thousand separators
- Null/None values in various formats

Design Philosophy:
- Fail-safe: Never raise exceptions, return None for invalid data
- Preserve original: Return original value if conversion not applicable
- Explicit: Clear function names indicate purpose and return type
- Defensive: Handle edge cases and unexpected input formats

Use Cases:
- CSV field normalization before database insertion
- User input validation and sanitization
- Data quality checks and cleansing
- Type coercion for weakly-typed data sources

Author: Azure Bank Platform Team
Last Updated: 2024
"""

# utils/sanitizer.py


def strip(value):
    """
    Remove leading and trailing whitespace from strings.
    
    Common whitespace issues in CSV data:
    - Excel exports: Extra spaces around values
    - Manual editing: Accidental spaces during data entry
    - Copy-paste errors: Tab characters, non-breaking spaces
    - Legacy systems: Fixed-width format padding
    
    Args:
        value: Any Python value (str, int, float, None, etc.)
    
    Returns:
        str: Trimmed string if input is string
        original: Unchanged value if not a string
    
    Examples:
        strip("  hello  ") → "hello"
        strip("ACC001") → "ACC001"
        strip(12345) → 12345 (unchanged, not a string)
        strip(None) → None (unchanged)
        strip("") → "" (empty string remains empty)
    
    Design Note:
        Returns original non-string values unchanged (not converted to string).
        This preserves type information for downstream processing.
    """
    if isinstance(value, str):
        return value.strip()  # Remove leading/trailing whitespace
    return value  # Not a string - return as-is


def to_float(value):
    """
    Convert value to float with safe handling of common formatting issues.
    
    Handles common numeric formatting in banking data:
    - Thousand separators: "1,000,000" → 1000000.0
    - Decimal points: "1234.56" → 1234.56
    - Extra whitespace: " 1234 " → 1234.0
    - String numbers: "1234" → 1234.0
    - Already float: 1234.0 → 1234.0
    - Already int: 1234 → 1234.0
    
    Args:
        value: Any value that might represent a number
            (str, int, float, None, etc.)
    
    Returns:
        float: Converted numeric value
        None: If conversion fails or input is None
    
    Examples:
        to_float("1,000.50") → 1000.5
        to_float("  123  ") → 123.0
        to_float(456) → 456.0
        to_float("invalid") → None
        to_float(None) → None
        to_float("") → None
    
    Use Cases:
        - Amount fields: Transaction amounts with thousand separators
        - Balance fields: Account balances from various systems
        - Percentage values: Interest rates, growth rates
        - Financial metrics: Ratios, calculated values
    
    Error Handling:
        - Invalid formats: Returns None (caller decides how to handle)
        - None input: Returns None (preserves null semantics)
        - Non-numeric strings: Returns None (e.g., "N/A", "Unknown")
    
    Performance:
        - O(1) for numeric types (no conversion needed)
        - O(n) for strings where n = string length
        - Very fast for typical field sizes (<50 characters)
    
    TODO: Add support for currency symbols ($, ₹, €)
    TODO: Add support for scientific notation (1.5e6)
    TODO: Add option for strict mode (raise exception on failure)
    """
    if value is None:
        return None  # Preserve null values

    try:
        if isinstance(value, str):
            # Remove thousand separators (commas) and whitespace
            value = value.replace(",", "").strip()
            
            # Handle empty string after cleaning
            if not value:
                return None
        
        # Convert to float (handles int, float, numeric string)
        return float(value)
    except (ValueError, TypeError, AttributeError):
        # Conversion failed - return None for safe handling
        return None


def to_bool(value):
    """
    Convert various boolean representations to Python bool.
    
    Handles common boolean formats in banking data:
    - Text: "yes"/"no", "true"/"false", "y"/"n"
    - Numeric: 1/0, "1"/"0"
    - Case-insensitive: "YES", "True", "Y" all map to True
    
    Args:
        value: Any value that might represent a boolean
            (bool, str, int, None, etc.)
    
    Returns:
        True: If value represents affirmative/true/yes
        False: If value represents negative/false/no
        None: If value is ambiguous or invalid
    
    Examples:
        to_bool("yes") → True
        to_bool("YES") → True
        to_bool("1") → True
        to_bool(1) → True (via str conversion)
        to_bool("no") → False
        to_bool("0") → False
        to_bool("maybe") → None
        to_bool(None) → None
        to_bool("") → None
    
    Use Cases:
        - KYC status: "KYC_Done" field (yes/no)
        - Account status: Active flags (true/false, 1/0)
        - Feature flags: Enable/disable settings
        - User preferences: Opt-in/opt-out choices
    
    Design Rationale:
        - Returns None for ambiguous values (explicit is better than implicit)
        - Case-insensitive matching (handles data quality issues)
        - Multiple formats (compatible with various systems)
        - Preserves None (null semantics for optional fields)
    
    Alternative Values:
        Not supported (returns None):
        - "on"/"off" (add if needed)
        - "enabled"/"disabled" (add if needed)
        - "active"/"inactive" (add if needed)
        - Other languages (oui/non, ja/nein, etc.)
    
    TODO: Add support for additional boolean representations
    TODO: Add option for default value (instead of None)
    TODO: Add strict mode (raise exception for invalid input)
    """
    if value is None:
        return None  # Preserve null values

    if isinstance(value, bool):
        return value  # Already boolean - return as-is

    # Convert to lowercase string for comparison
    s = str(value).strip().lower()
    
    # Check for true-like values
    if s in ["yes", "true", "1", "y"]:
        return True
    
    # Check for false-like values
    if s in ["no", "false", "0", "n"]:
        return False

    # Ambiguous or unrecognized - return None
    return None
