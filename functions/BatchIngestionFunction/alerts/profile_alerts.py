"""
Profile-level alert generation for account documents.

Inspects account documents (and optional customer doc) to raise alerts such as
KYC issues, dormant accounts, balance/income mismatches and stale accounts.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List

from ..utils.date_utils import parse_ts
from ..utils.sanitizer import to_float

STALE_ACCOUNT_YEARS = 5
STALE_ACCOUNT_BALANCE_THRESHOLD = 100


def generate_profile_alerts(account_doc: Dict[str, Any], customer_doc: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Generate account-level alerts for a given account document.

    Alerts produced include:
      - KYC not done
      - KYC verification failed
      - Dormant/inactive account
      - Closed account
      - Balance vs declared income mismatch
      - Very old account with low balance (stale)

    Args:
        account_doc: Document with keys 'AccountNumber', 'CustomerID', and 'Account' subdoc.
        customer_doc: Optional customer subdocument (may contain 'AnnualIncome').

    Returns:
        A list of alert dictionaries. Each alert contains an 'id', 'type', 'reason', and 'payload'.
    """
    alerts: List[Dict[str, Any]] = []

    acc_num = account_doc.get("AccountNumber")
    cust_id = account_doc.get("CustomerID")
    acc = account_doc.get("Account", {})

    # ---------------------------
    # 1. KYC Not Done
    # ---------------------------
    kyc_done = (acc.get("KYC_Done") or "").upper()
    if kyc_done in ["NO", "FALSE", "0", "N"]:
        alerts.append(
            {
                "id": f"ALERT_KYC_NOT_DONE_{acc_num}",
                "type": "KYC_NOT_DONE",
                "AccountNumber": acc_num,
                "CustomerID": cust_id,
                "reason": "KYC is not completed",
                "payload": acc,
            }
        )

    # ---------------------------
    # 2. KYC Document Verification Failed
    # ---------------------------
    kyc_ver = (acc.get("KYC_DocumentVerificationStatus") or "").upper()
    if kyc_ver == "FAILED":
        alerts.append(
            {
                "id": f"ALERT_KYC_VERIFICATION_FAILED_{acc_num}",
                "type": "KYC_VERIFICATION_FAILED",
                "AccountNumber": acc_num,
                "CustomerID": cust_id,
                "reason": "KYC verification failed",
                "payload": acc,
            }
        )

    # ---------------------------
    # 3. Dormant / Inactive
    # ---------------------------
    status = (acc.get("AccountStatus") or "").upper()
    if status in ["DORMANT", "INACTIVE"]:
        alerts.append(
            {
                "id": f"ALERT_ACCOUNT_DORMANT_{acc_num}",
                "type": "ACCOUNT_DORMANT",
                "AccountNumber": acc_num,
                "CustomerID": cust_id,
                "reason": "Account is dormant or inactive",
                "payload": acc,
            }
        )

    # ---------------------------
    # 4. Closed account
    # ---------------------------
    if status == "CLOSED":
        alerts.append(
            {
                "id": f"ALERT_ACCOUNT_CLOSED_{acc_num}",
                "type": "ACCOUNT_CLOSED",
                "AccountNumber": acc_num,
                "CustomerID": cust_id,
                "reason": "Account is closed",
                "payload": acc,
            }
        )

    # ---------------------------
    # 5. Balance vs Income Risk
    # ---------------------------
    if customer_doc:
        bal = to_float(acc.get("Balance")) or 0
        inc = to_float(customer_doc.get("AnnualIncome")) or 0

        # If account balance far exceeds declared annual income, raise risk alert
        if inc > 0 and bal > (inc * 10):
            alerts.append(
                {
                    "id": f"ALERT_BALANCE_INCOME_MISMATCH_{acc_num}",
                    "type": "BALANCE_INCOME_MISMATCH",
                    "AccountNumber": acc_num,
                    "CustomerID": cust_id,
                    "reason": f"Balance {bal} greatly exceeds declared income {inc}",
                    "payload": {"balance": bal, "income": inc},
                }
            )

    # ---------------------------
    # 6. Very Old + Low Balance (Stale Account)
    # ---------------------------
    open_date = parse_ts(acc.get("AccountOpenDate"))
    bal = to_float(acc.get("Balance")) or 0

    if open_date:
        age_years = (datetime.now(timezone.utc) - open_date).days / 365
        if age_years >= STALE_ACCOUNT_YEARS and bal < STALE_ACCOUNT_BALANCE_THRESHOLD:
            alerts.append(
                {
                    "id": f"ALERT_STALE_ACCOUNT_{acc_num}",
                    "type": "STALE_ACCOUNT",
                    "AccountNumber": acc_num,
                    "CustomerID": cust_id,
                    "reason": "Account is very old and balance is too low",
                    "payload": {"age_years": age_years, "balance": bal},
                }
            )

    return alerts
