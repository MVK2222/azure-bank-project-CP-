"""
CSV utilities for parsing and inferring source type from filenames.

Provides a thin wrapper over Python's csv module with a small fallback
for dialect detection, and a filename-based source type detector.
"""

import csv
import io
import logging
from typing import List, Dict


def parse_csv(text: str) -> List[Dict[str, str]]:
    """
    Parse CSV text into a list of dictionaries (one dict per row).

    Behavior:
    - If input text is falsy, returns an empty list.
    - Attempts to autodetect CSV dialect using csv.Sniffer on the first line.
      On failure, falls back to `csv.excel` (comma delimiter).

    Args:
        text: Raw CSV content as a string.

    Returns:
        A list of dicts where each dict maps column headers to string values.

    Notes:
        - This function does not coerce types — callers should run their
          sanitizers/validators on the returned rows.
    """
    if not text:
        return []

    try:
        # Use first line to help the Sniffer guess delimiter/dialect
        # Inline comment: Sniffer expects a representative sample; using the first line is a lightweight heuristic
        first_line = text.splitlines()[0]
        dialect = csv.Sniffer().sniff(first_line)
    except Exception:
        logging.warning("Failed to detect dialect, falling back to default comma delimiter")
        # Fallback to default comma-based dialect
        dialect = csv.excel

    # Create a DictReader using the detected/fallback dialect and return rows
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [row for row in reader]


def detect_source_type(file_name: str) -> str:
    """
    Infer the ingestion source type from a filename.

    Looks for keywords in the filename to classify the source as one of:
    'ATM', 'UPI', 'ACCOUNT', 'CUSTOMER', or 'UNKNOWN'.

    Args:
        file_name: Filename (or full path) of the uploaded file.

    Returns:
        A string constant representing the detected source type.
    """
    if not file_name:
        return "UNKNOWN"

    f = file_name.lower()
    # Inline comment: case-insensitive checks on the filename are sufficient for this demo pipeline
    if "atm" in f:
        return "ATM"
    if "upi" in f:
        return "UPI"
    if "account" in f:
        return "ACCOUNT"
    if "customer" in f:
        return "CUSTOMER"
    return "UNKNOWN"
