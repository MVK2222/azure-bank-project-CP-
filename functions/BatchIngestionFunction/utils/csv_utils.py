"""
csv_utils.py: CSV Parsing and File Type Detection Utilities

This module provides robust CSV parsing with automatic delimiter detection
and convention-based file type routing for the banking data platform.

Key Features:
- Automatic delimiter detection (comma, tab, pipe, semicolon)
- Graceful fallback to standard CSV format
- File type detection based on naming conventions
- Header preservation for schema validation

Design Philosophy:
- Fail-safe: Always return a result, even if suboptimal
- Convention over configuration: Filename patterns determine routing
- Simple and maintainable: No complex parsing logic or dependencies

Performance:
- parse_csv: O(n) where n = file size
- detect_source_type: O(1) string matching
- Memory: Entire CSV loaded into memory (suitable for <100MB files)

Supported File Types:
- ATM transactions: atm_*.csv, *_atm.csv, ATM_*.csv
- UPI transactions: upi_*.csv, *_upi.csv, UPI_*.csv  
- Account profiles: account_*.csv, *_account.csv
- Customer profiles: customer_*.csv, *_customer.csv

Author: Azure Bank Platform Team
Last Updated: 2024
"""

# utils/csv_utils.py
import csv
import io
import logging


def parse_csv(text: str):
    """
    Parse CSV text into list of dictionaries with automatic delimiter detection.
    
    This function handles various CSV formats produced by different systems:
    - Comma-separated: Standard format (Excel, Python)
    - Tab-separated: Database exports, legacy systems
    - Pipe-separated: Banking systems, mainframe exports
    - Semicolon-separated: European Excel (locale-specific)
    
    Args:
        text (str): Complete CSV file content as string.
            Must include header row as first line.
            Empty lines are skipped automatically by csv.DictReader.
    
    Returns:
        list[dict]: List of row dictionaries where keys are column names.
            Empty list if input is empty or contains only whitespace.
            
    Example Input:
        "TransactionID,Amount,Timestamp\n001,5000,2024-01-01T10:00:00\n002,3000,2024-01-01T10:05:00"
    
    Example Output:
        [
            {"TransactionID": "001", "Amount": "5000", "Timestamp": "2024-01-01T10:00:00"},
            {"TransactionID": "002", "Amount": "3000", "Timestamp": "2024-01-01T10:05:00"}
        ]
    
    Delimiter Detection Algorithm:
        1. csv.Sniffer analyzes first line to detect delimiter
        2. Checks for common patterns: ,;|\t
        3. Falls back to csv.excel (comma) if detection fails
        4. Detection works best with 3+ columns
    
    Edge Cases Handled:
        - Empty file: Returns empty list
        - Single column: May not detect delimiter (uses comma)
        - Quoted fields: csv.DictReader handles automatically
        - Escaped characters: Standard CSV escaping supported
        - Unicode: UTF-8 encoding assumed (caller responsibility)
    
    Performance:
        - Time: O(n) where n = file size
        - Memory: O(n) - entire file in memory plus parsed rows
        - Typical: 1-10ms for 1K rows, 100-500ms for 100K rows
    
    Error Handling:
        - Sniffer fails: Log warning, use default comma delimiter
        - Malformed CSV: csv.DictReader skips bad rows silently
        - Encoding errors: Raise exception (caller handles)
    
    Alternative for Large Files:
        For streaming large files, consider:
        ```
        def parse_csv_stream(file_handle):
            reader = csv.DictReader(file_handle)
            for row in reader:
                yield row  # Generator for memory efficiency
        ```
    
    TODO: Add option to enforce specific delimiter (disable auto-detection)
    TODO: Support Excel files (.xlsx) via openpyxl library
    TODO: Add row count limit for safety (prevent memory exhaustion)
    """
    if not text:
        return []  # Empty file - return empty list

    try:
        # Analyze first line to detect delimiter
        first_line = text.splitlines()[0]
        dialect = csv.Sniffer().sniff(first_line)
    except Exception:
        # Sniffer failed - use default comma delimiter
        logging.warning("Failed to detect dialect, falling back to default comma delimiter")
        dialect = csv.excel  # Standard Excel CSV format (comma, double-quote escaping)

    # Parse CSV with detected dialect
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [row for row in reader]  # Convert generator to list for random access


def detect_source_type(file_name: str) -> str:
    """
    Detect data source type based on filename conventions.
    
    This function implements convention-based routing: filename patterns
    determine which processor and schema validation to apply.
    
    Args:
        file_name (str): Original filename (e.g., "atm_20250101.csv", "customer_master.csv")
            Case-insensitive matching for robustness.
    
    Returns:
        str: Source type identifier:
            - "ATM": ATM transaction files
            - "UPI": UPI transaction files  
            - "ACCOUNT": Account profile/master files
            - "CUSTOMER": Customer profile/master files
            - "UNKNOWN": Unrecognized pattern (will be rejected downstream)
    
    Matching Rules:
        - ATM: Filename contains "atm" (case-insensitive)
        - UPI: Filename contains "upi" (case-insensitive)
        - ACCOUNT: Filename contains "account" (case-insensitive)
        - CUSTOMER: Filename contains "customer" (case-insensitive)
        - UNKNOWN: No matching pattern
    
    Pattern Priority:
        Rules evaluated in order (ATM, UPI, ACCOUNT, CUSTOMER).
        First match wins. Example: "atm_upi.csv" → ATM
    
    Example Filenames:
        "atm_20250101.csv" → ATM
        "upi_transactions_jan.csv" → UPI
        "account_master.csv" → ACCOUNT
        "customer_profiles_2024.csv" → CUSTOMER
        "transactions.csv" → UNKNOWN
        "ATM_DATA.CSV" → ATM (case-insensitive)
    
    Design Rationale:
        - Simple pattern matching: Easy to understand and maintain
        - No configuration files: Reduces deployment complexity
        - Extensible: New patterns can be added easily
        - Fast: O(1) string matching, no regex overhead
    
    Alternative Approaches:
        - Metadata files: Requires additional file uploads
        - Content inspection: Analyze CSV headers (slower, more complex)
        - Manifest files: Batch metadata in separate JSON
        - Explicit routing: API parameter or message property
    
    Limitations:
        - Ambiguous names: "data.csv" → UNKNOWN
        - Multiple patterns: "atm_upi.csv" → ATM (first match)
        - Misspellings: "atm_transactons.csv" → ATM (catches "atm")
    
    TODO: Add regex support for more complex patterns
    TODO: Support multiple source types per file (split processing)
    TODO: Add validation against whitelist of expected patterns
    """
    f = file_name.lower()  # Case-insensitive matching
    
    # Check patterns in priority order
    if "atm" in f:
        return "ATM"
    if "upi" in f:
        return "UPI"
    if "account" in f:
        return "ACCOUNT"
    if "customer" in f:
        return "CUSTOMER"
    
    # No matching pattern found
    return "UNKNOWN"
