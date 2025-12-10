"""
Transaction-level fraud detection rules.

This module implements a small set of heuristics used to flag suspicious
transactions. Each rule is intentionally simple and should be treated as
alerts for human analysts or downstream ML pipelines.
"""

from datetime import timedelta
from dateutil import parser as date_parser
from typing import List, Dict, Any

# Threshold for high-value transactions
HIGH_VALUE_THRESHOLD = 50000.0
# Time window in minutes for velocity checks
VELOCITY_WINDOW_MINUTES = 2
# Transaction count threshold for velocity attacks
VELOCITY_TXN_COUNT = 10


def fraud_detection(parsed_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply transaction-level fraud rules and return a list of alert dicts.

    Rules implemented:
      1. High-value transactions (amount >= HIGH_VALUE_THRESHOLD)
      2. Velocity attacks: >= VELOCITY_TXN_COUNT within VELOCITY_WINDOW_MINUTES
      3. Geo-location switching: transactions from different locations within 10 minutes
      4. Balance drain: total withdrawals above 100,000 within 10 minutes

    Args:
        parsed_rows: List of normalized transaction dicts. Expected keys include
                     'Amount', 'Timestamp', 'TransactionID', 'AccountNumber', 'Location', 'CustomerID'.

    Returns:
        A list of alert dictionaries. Each alert includes an alert_id, type, reason,
        and payload (transactions or single transaction) describing the trigger.
    """
    alerts: List[Dict[str, Any]] = []

    # --------------------------------------
    # RULE 1: HIGH VALUE FRAUD
    # --------------------------------------
    for r in parsed_rows:
        try:
            amt = float(r.get("Amount") or 0)
            # Check if transaction amount exceeds the high-value threshold
            if amt >= HIGH_VALUE_THRESHOLD:
                alerts.append(
                    {
                        "alert_id": f"ALERT_HIGHVALUE_{r.get('TransactionID')}",
                        "type": "HIGH_VALUE",
                        "reason": f"Transaction amount {amt} exceeds threshold {HIGH_VALUE_THRESHOLD}",
                        "transaction": r,
                    }
                )
        except Exception:
            # If amount cannot be parsed, skip this rule for that row
            continue

    # --------------------------------------
    # RULE 2: VELOCITY FRAUD (Many txns in short time)
    # --------------------------------------
    # Group transactions by a customer identifier (CustomerID or AccountNumber)
    by_customer = {}
    for r in parsed_rows:
        cid = r.get("CustomerID") or r.get("AccountNumber") or "UNKNOWN"
        try:
            # Parse timestamp; parsed_rows are expected to have ISO timestamps but
            # accept flexible inputs.
            ts = date_parser.parse(r.get("Timestamp"))
        except Exception:
            # Skip rows with invalid timestamps for velocity calculations
            continue
        by_customer.setdefault(cid, []).append((ts, r))

    window = timedelta(minutes=VELOCITY_WINDOW_MINUTES)

    for cid, items in by_customer.items():
        # Sort transactions by timestamp
        items.sort(key=lambda x: x[0])

        for i in range(len(items)):
            j = i + 1
            count = 1
            # Count how many transactions fall within the sliding window
            while j < len(items) and (items[j][0] - items[i][0]) <= window:
                count += 1
                j += 1

            # If transaction count within the window exceeds the threshold, flag as velocity attack
            if count >= VELOCITY_TXN_COUNT:
                group_txns = [it[1] for it in items[i:j]]
                alerts.append(
                    {
                        "alert_id": f"ALERT_VELOCITY_{cid}_{items[i][0].isoformat()}",
                        "type": "VELOCITY_ATTACK",
                        "reason": f"{count} transactions within {VELOCITY_WINDOW_MINUTES} minutes",
                        "transactions": group_txns,
                    }
                )

    # --------------------------------------
    # RULE 3: GEO LOCATION SWITCHING FRAUD
    # --------------------------------------
    # Detect quick changes in location for the same customer
    for cid, items in by_customer.items():
        loc_map = {}
        for ts, r in items:
            loc = r.get("Location")
            loc_map.setdefault(loc, []).append(ts)

        timestamps = []
        for loc, ts_list in loc_map.items():
            for t in ts_list:
                timestamps.append((loc, t))

        # Sort by timestamp and look for rapid location changes
        timestamps.sort(key=lambda x: x[1])

        for i in range(len(timestamps)):
            loc1, t1 = timestamps[i]
            for j in range(i + 1, len(timestamps)):
                loc2, t2 = timestamps[j]
                # If location changes within 10 minutes, flag as geo location switch
                if loc1 != loc2 and (t2 - t1) <= timedelta(minutes=10):
                    alerts.append(
                        {
                            "alert_id": f"ALERT_GEO_{cid}_{t1.isoformat()}",
                            "type": "GEO_LOCATION_SWITCH",
                            "reason": f"Transaction from {loc1} → {loc2} within 10 minutes",
                            "transactions": [timestamps[i], timestamps[j]],
                        }
                    )

    # --------------------------------------
    # RULE 4: BALANCE DRAIN (Many withdrawals fast)
    # --------------------------------------
    for cid, items in by_customer.items():
        total_amt = 0
        items_sorted = sorted(items, key=lambda x: x[0])
        if not items_sorted:
            continue
        start = items_sorted[0][0]

        for ts, r in items_sorted:
            try:
                amt = float(r.get("Amount") or 0)
            except Exception:
                amt = 0

            total_amt += amt

            # If many withdrawals within 10 minutes exceed a high threshold,
            # flag as balance drain. Thresholds are intentionally simple.
            if (ts - start) <= timedelta(minutes=10) and total_amt >= 100000:
                alerts.append(
                    {
                        "alert_id": f"ALERT_BALANCE_DRAIN_{cid}_{ts.isoformat()}",
                        "type": "BALANCE_DRAIN",
                        "reason": f"Total withdrawals {total_amt} in 10 minutes",
                        "transactions": [x[1] for x in items_sorted],
                    }
                )
                break

    return alerts
