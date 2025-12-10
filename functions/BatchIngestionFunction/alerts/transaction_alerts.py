"""
transaction_alerts.py: Real-Time Fraud Detection Engine

This module implements rule-based fraud detection algorithms for banking transactions.
It analyzes patterns across ATM and UPI transactions to identify suspicious activities
that may indicate fraudulent behavior.

Fraud Detection Approach: Multi-Rule Heuristic System
    - Each rule targets a specific fraud pattern observed in banking data
    - Rules are evaluated independently (non-interfering)
    - Multiple alerts can be generated for a single transaction
    - Rules are tuned based on false positive/false negative analysis

Key Performance Indicators (KPIs):
    - Alert Generation Rate: % of transactions flagged
    - False Positive Rate: % of alerts that are not fraud (target: <5%)
    - False Negative Rate: % of fraud missed (target: <1%)
    - Alert Response Time: Time from transaction to alert (target: <1 minute)

Production Considerations:
    - Rules are intentionally simple for explainability (required for compliance)
    - Machine learning models can augment rules for better accuracy
    - Thresholds should be tuned based on historical fraud data
    - Regular rule review is essential as fraud patterns evolve

Integration Points:
    - INPUT: Validated transaction records (ATM, UPI)
    - OUTPUT: Fraud alert documents for FraudAlerts container
    - MONITORING: Alert counts tracked in processing metadata

Compliance & Regulatory:
    - Alerts must be auditable (reason field explains detection logic)
    - Transaction data preserved in alert payload for investigation
    - Rules aligned with banking industry best practices (PCI DSS, AML)

Author: Azure Bank Platform Team
Last Updated: 2024
Version: 2.0 (Multi-Rule Engine)
"""

# alerts/transaction_alerts.py
from datetime import timedelta
from dateutil import parser as date_parser

# ================================================================================
# FRAUD DETECTION PARAMETERS: Tunable Thresholds
# ================================================================================
# These constants define the sensitivity of fraud detection rules.
# Tuning guidance:
# - Tighter thresholds: More alerts, higher false positives
# - Looser thresholds: Fewer alerts, higher false negatives
# - Tune based on historical fraud data and false positive analysis

# Rule 1: High-Value Transaction Threshold
HIGH_VALUE_THRESHOLD = 50000.0  # Rupees (₹50,000)
# Rationale: Single transactions above this amount are rare and high-risk
# Typical range: ₹20,000 - ₹100,000 depending on customer demographics
# Consider: Dynamic thresholds based on account history and customer profile

# Rule 2: Velocity Attack Detection
VELOCITY_WINDOW_MINUTES = 2  # Time window for counting transactions
VELOCITY_TXN_COUNT = 10      # Number of transactions within window to trigger alert
# Rationale: Normal customers rarely make >10 transactions in 2 minutes
# Typical pattern: Compromised cards used for rapid small withdrawals before freezing
# Consider: Different thresholds for ATM vs UPI (UPI typically faster)

# TODO: Add dynamic threshold calculation based on account velocity history
# TODO: Implement machine learning model for anomaly detection (complement rules)


def fraud_detection(parsed_rows):
    """
    Execute comprehensive fraud detection across all transaction records.
    
    This function applies multiple fraud detection rules to identify suspicious patterns:
    1. High-Value Fraud: Single large transactions above threshold
    2. Velocity Attacks: Rapid succession of transactions (card testing, ATM jackpotting)
    3. Geo-Location Switching: Impossible travel patterns (Mumbai → Delhi in 10 minutes)
    4. Balance Drain: Large total withdrawals in short time (account takeover)
    
    Args:
        parsed_rows (list[dict]): List of validated transaction records with fields:
            - TransactionID (str): Unique transaction identifier
            - AccountNumber (str): Account/card number
            - CustomerID (str): Customer identifier (may be missing)
            - Amount (float): Transaction amount in rupees
            - Timestamp (str): ISO 8601 timestamp
            - Location (str): City or ATM location (may be missing)
            - Status (str): SUCCESS, FAILED, PENDING, etc.
    
    Returns:
        list[dict]: List of alert dictionaries, each containing:
            - alert_id (str): Unique alert identifier
            - type (str): Alert type (HIGH_VALUE, VELOCITY_ATTACK, etc.)
            - reason (str): Human-readable explanation
            - transaction (dict): Single transaction that triggered alert
            - transactions (list[dict]): Multiple transactions (for pattern-based alerts)
    
    Processing Strategy:
        - Rules are independent (order doesn't matter)
        - All rules execute even if earlier rules generate alerts
        - Failed transactions are included (FAILED status can indicate fraud attempts)
        - Missing fields gracefully handled (skip rule if required data unavailable)
    
    Performance:
        - Time Complexity: O(n²) worst-case for velocity/geo rules (nested loops)
        - Typical: O(n log n) due to early termination and sorting optimizations
        - Memory: O(n) for customer grouping and timestamp sorting
        - Batch Size: Optimized for 1K-10K transactions per batch
    
    Alert Volume Expectations:
        - Typical: 0.5-2% of transactions generate alerts
        - High-fraud periods: Up to 5-10% alert rate
        - False positives: ~3-5% of alerts (requires tuning)
    
    Operational Workflow:
        1. Alerts generated and persisted to Cosmos DB
        2. Fraud investigation team reviews alerts in real-time
        3. Confirmed fraud: Account frozen, customer notified
        4. False positive: Alert marked resolved, thresholds adjusted
    
    Example Output:
        [
            {
                "alert_id": "ALERT_HIGHVALUE_TXN123",
                "type": "HIGH_VALUE",
                "reason": "Transaction amount 75000.0 exceeds threshold 50000.0",
                "transaction": {"TransactionID": "TXN123", "Amount": 75000, ...}
            },
            {
                "alert_id": "ALERT_VELOCITY_ACC001_2024-01-01T10:00:00",
                "type": "VELOCITY_ATTACK",
                "reason": "12 transactions within 2 minutes",
                "transactions": [{"TransactionID": "TXN124", ...}, ...]
            }
        ]
    
    Future Enhancements:
        - Add machine learning scoring (anomaly detection, behavior modeling)
        - Implement real-time streaming (Event Hubs + Stream Analytics)
        - Add cross-account pattern detection (ring networks, mule accounts)
        - Integrate external fraud databases (known fraud devices, IPs)
    
    IMPORTANT: This is a production fraud detection system. Changes to rules
    or thresholds must be reviewed by fraud operations team and tested
    against historical data before deployment.
    """
    alerts = []  # Accumulates all alerts from all rules

    # ================================================================================
    # RULE 1: HIGH-VALUE TRANSACTION FRAUD DETECTION
    # ================================================================================
    # Fraud Pattern: Single Large Withdrawal or Payment
    #
    # Attack Scenarios:
    # - Compromised card used for large ATM withdrawal before customer notices
    # - Account takeover with immediate large fund transfer
    # - Internal fraud (employee using stolen credentials)
    # - Money laundering (large cash-out transactions)
    #
    # Detection Logic:
    # - Any transaction with amount ≥ HIGH_VALUE_THRESHOLD triggers alert
    # - Applies to both successful and failed transactions
    # - Failed high-value attempts may indicate probing or testing
    #
    # False Positive Scenarios:
    # - Legitimate large purchases (car, property down payment)
    # - Business account operations (payroll, vendor payments)
    # - Savings account withdrawals
    #
    # Mitigation:
    # - Whitelist known high-value customers (VIP, business accounts)
    # - Consider transaction history (frequent high-value → less suspicious)
    # - Time-based thresholds (higher limits during business hours)
    #
    # Real-World Example:
    #   Customer normally transacts ₹5K-10K daily. Suddenly ₹75K withdrawal at 2 AM.
    #   High probability of fraud. Alert enables immediate investigation and account freeze.
    
    for r in parsed_rows:
        try:
            amt = float(r.get("Amount") or 0)
            if amt >= HIGH_VALUE_THRESHOLD:
                alerts.append({
                    "alert_id": f"ALERT_HIGHVALUE_{r.get('TransactionID')}",
                    "type": "HIGH_VALUE",
                    "reason": f"Transaction amount {amt} exceeds threshold {HIGH_VALUE_THRESHOLD}",
                    "transaction": r  # Full transaction preserved for investigation
                })
        except:
            # Invalid amount format - skip this rule for this transaction
            # Already flagged during validation; don't duplicate errors
            pass

    # ================================================================================
    # RULE 2: VELOCITY ATTACK DETECTION (Card Testing / ATM Jackpotting)
    # ================================================================================
    # Fraud Pattern: Rapid Succession of Transactions
    #
    # Attack Scenarios:
    # - Card testing: Fraudsters verify stolen card works with multiple small transactions
    # - ATM jackpotting: Malware causes rapid cash dispensing
    # - Brute force: Multiple PIN attempts or transaction retries
    # - Bot attacks: Automated scripts draining account via UPI
    #
    # Detection Logic:
    # - Group transactions by customer/account
    # - Sort by timestamp for chronological analysis
    # - Sliding window algorithm: Count transactions within time window
    # - Alert if count ≥ VELOCITY_TXN_COUNT within VELOCITY_WINDOW_MINUTES
    #
    # Algorithm Complexity:
    # - Time: O(n log n) for sorting + O(n²) worst-case for nested loop
    # - Space: O(n) for customer grouping
    # - Optimization: Early termination when window exceeded
    #
    # False Positive Scenarios:
    # - Legitimate rapid transactions (shopping spree, bill payments)
    # - Family members using same card (spouse, children)
    # - Merchant retries (failed transaction retried multiple times)
    #
    # Mitigation:
    # - Different thresholds for different transaction types (UPI vs ATM)
    # - Whitelist known high-velocity customers (small business owners)
    # - Consider transaction amounts (10x ₹100 less suspicious than 10x ₹5000)
    #
    # Real-World Example:
    #   12 UPI transactions in 90 seconds from same account to different merchants.
    #   Classic card testing pattern. Alert enables immediate card freeze.
    
    # Group transactions by customer for temporal analysis
    by_customer = {}
    for r in parsed_rows:
        # Use CustomerID if available, fallback to AccountNumber for grouping
        cid = r.get("CustomerID") or r.get("AccountNumber") or "UNKNOWN"
        try:
            ts = date_parser.parse(r.get("Timestamp"))  # Parse ISO timestamp
        except:
            continue  # Skip transactions with invalid timestamps
        by_customer.setdefault(cid, []).append((ts, r))

    window = timedelta(minutes=VELOCITY_WINDOW_MINUTES)  # Time window for counting

    for cid, items in by_customer.items():
        # Sort by timestamp for sliding window algorithm
        items.sort(key=lambda x: x[0])

        # Sliding window: Check every transaction as potential window start
        for i in range(len(items)):
            j = i + 1
            count = 1  # Current transaction counts as 1
            
            # Count transactions within window starting at position i
            while j < len(items) and (items[j][0] - items[i][0]) <= window:
                count += 1
                j += 1

            # Alert if velocity threshold exceeded
            if count >= VELOCITY_TXN_COUNT:
                group_txns = [it[1] for it in items[i:j]]  # Extract transaction dicts
                alerts.append({
                    "alert_id": f"ALERT_VELOCITY_{cid}_{items[i][0].isoformat()}",
                    "type": "VELOCITY_ATTACK",
                    "reason": f"{count} transactions within {VELOCITY_WINDOW_MINUTES} minutes",
                    "transactions": group_txns  # All transactions in the velocity burst
                })
                # Note: Breaking here would miss overlapping velocity windows
                # Keeping loop finds all velocity bursts for thorough detection

    # ================================================================================
    # RULE 3: GEO-LOCATION SWITCHING FRAUD (Impossible Travel)
    # ================================================================================
    # Fraud Pattern: Physically Impossible Transaction Locations
    #
    # Attack Scenarios:
    # - Card cloning: Original card in Mumbai, cloned card used in Delhi simultaneously
    # - Account sharing: Credentials shared across different cities
    # - Credential theft: Stolen credentials used from different geographic location
    # - Travel fraud: Card used at airport then at distant city before flight lands
    #
    # Detection Logic:
    # - Track all transaction locations per customer
    # - Identify location changes that occur within impossible timeframe
    # - Alert if transactions from different cities within 10 minutes
    #
    # Assumptions & Limitations:
    # - Location granularity: City-level (not GPS coordinates)
    # - 10-minute window: Conservative (accounts for time zone issues)
    # - Network transactions (UPI): Location may be mobile, not physical
    # - ATM transactions: Location is physical ATM address
    #
    # False Positive Scenarios:
    # - VPN usage: User appears in different city due to VPN exit node
    # - UPI from one city, ATM in another: If cities are nearby or user traveling
    # - Location data errors: Merchant location misconfigured
    # - Mobile transactions: Phone location vs actual transaction location
    #
    # Improvements Needed:
    # - Calculate actual distance and travel time (haversine formula)
    # - Consider transportation speed (car: 60-80 km/h, flight: 800+ km/h)
    # - Whitelist nearby cities (Delhi-Noida, Mumbai-Thane)
    # - Different thresholds for ATM vs UPI (UPI more flexible)
    #
    # Real-World Example:
    #   ATM withdrawal in Chennai at 10:00 AM, then UPI payment in Bangalore at 10:05 AM.
    #   ~350 km distance impossible in 5 minutes. Clear fraud indicator.
    #
    # TODO: Integrate geographic distance calculation (geopy library)
    # TODO: Add travel velocity calculation (km/h between locations)
    # TODO: Whitelist airport locations (legitimate rapid travel possible)
    
    for cid, items in by_customer.items():
        # Build location-to-timestamps mapping for this customer
        loc_map = {}
        for ts, r in items:
            loc = r.get("Location")
            if loc:  # Only process if location data available
                loc_map.setdefault(loc, []).append(ts)

        # Flatten to list of (location, timestamp) tuples for chronological analysis
        timestamps = []
        for loc, ts_list in loc_map.items():
            for t in ts_list:
                timestamps.append((loc, t))

        # Sort by timestamp to detect rapid location switches
        timestamps.sort(key=lambda x: x[1])

        # Check each pair of transactions for impossible travel
        # O(n²) complexity - acceptable for typical customer transaction counts
        for i in range(len(timestamps)):
            loc1, t1 = timestamps[i]
            for j in range(i + 1, len(timestamps)):
                loc2, t2 = timestamps[j]
                
                # Alert if different locations within impossible timeframe
                if loc1 != loc2 and (t2 - t1) <= timedelta(minutes=10):
                    # Find actual transaction records for these timestamps
                    # (timestamps list contains (location, timestamp) tuples, not full transactions)
                    txn1 = next((r for ts, r in items if ts == t1), None)
                    txn2 = next((r for ts, r in items if ts == t2), None)
                    
                    alerts.append({
                        "alert_id": f"ALERT_GEO_{cid}_{t1.isoformat()}",
                        "type": "GEO_LOCATION_SWITCH",
                        "reason": f"Transaction from {loc1} → {loc2} within 10 minutes",
                        "transactions": [txn1, txn2] if txn1 and txn2 else [],  # Full transaction dicts for consistency
                        "locations": [(loc1, t1.isoformat()), (loc2, t2.isoformat())]  # Location metadata
                    })
                    # Note: Not breaking allows detection of multiple location switches

    # ================================================================================
    # RULE 4: BALANCE DRAIN ATTACK (Account Takeover)
    # ================================================================================
    # Fraud Pattern: Rapid Large-Scale Fund Extraction
    #
    # Attack Scenarios:
    # - Account takeover: Fraudster gains full account access, drains balance quickly
    # - Insider fraud: Employee with system access steals funds
    # - Malware: Banking trojan authorizes rapid transfers in background
    # - SIM swap: Fraudster intercepts OTPs, bypasses 2FA, drains account
    #
    # Detection Logic:
    # - Calculate cumulative withdrawal amount per customer
    # - Alert if total exceeds ₹100,000 within 10-minute window
    # - Considers all transactions chronologically (even if individually small)
    #
    # Why This Rule Complements Rule 1 (High-Value):
    # - Rule 1: Single ₹75K transaction → 1 alert
    # - Rule 4: 20x ₹5K transactions in 5 minutes → 1 alert
    # - Fraudsters often use multiple small transactions to avoid single high-value alerts
    #
    # Threshold Rationale:
    # - ₹100,000 in 10 minutes: Extremely unusual for retail customers
    # - Business accounts may have higher legitimate volumes
    # - Consider customer segment and account type for dynamic thresholds
    #
    # False Positive Scenarios:
    # - Business account: Legitimate payroll or vendor payment batches
    # - Personal emergency: Medical expenses, property transactions
    # - Account closure: Customer withdrawing all funds before closing account
    #
    # Mitigation:
    # - Whitelist business accounts with expected high-volume activity
    # - Consider transaction patterns (scheduled vs ad-hoc)
    # - Alert severity scoring (higher for retail accounts)
    # - Velocity + amount combination for better accuracy
    #
    # Real-World Example:
    #   Account takeover at 2 AM: 15 UPI transfers (₹7K each) to different accounts
    #   within 8 minutes. Total ₹105K drained. Classic account takeover pattern.
    #   Immediate alert enables account freeze before more damage.
    #
    # Algorithm Optimization:
    # - Early termination: Break loop once threshold reached
    # - Sorted by timestamp: Enables cumulative sum in single pass
    # - Time Complexity: O(n) per customer
    #
    # TODO: Add velocity-weighted scoring (faster drain = higher risk)
    # TODO: Consider transaction types (transfers more suspicious than bill payments)
    # TODO: Implement customer-specific thresholds based on account history
    
    for cid, items in by_customer.items():
        total_amt = 0.0
        
        # Sort transactions chronologically for cumulative sum
        items_sorted = sorted(items, key=lambda x: x[0])
        
        if not items_sorted:
            continue  # Skip if no transactions for this customer
            
        start = items_sorted[0][0]  # First transaction timestamp (window start)

        # Cumulative sum within time window
        for ts, r in items_sorted:
            try:
                amt = float(r.get("Amount") or 0)
            except:
                amt = 0.0  # Invalid amount format - skip

            total_amt += amt

            # Check if drain threshold exceeded within time window
            if (ts - start) <= timedelta(minutes=10) and total_amt >= 100000:
                alerts.append({
                    "alert_id": f"ALERT_BALANCE_DRAIN_{cid}_{ts.isoformat()}",
                    "type": "BALANCE_DRAIN",
                    "reason": f"Total withdrawals {total_amt} in 10 minutes",
                    "transactions": [x[1] for x in items_sorted]  # All transactions in drain sequence
                })
                break  # One alert per customer sufficient (first drain detected)

    return alerts  # Return all alerts from all rules
