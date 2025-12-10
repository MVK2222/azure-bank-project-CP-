"""
Account processor - converts account CSV rows into Cosmos DB account documents and generates profile alerts.

Responsibilities:
- Parse CSV text into rows, validate them via `validate_account_row`, and build account documents.
- Query existing customer/profile docs to enrich alert generation (e.g., AnnualIncome).
- Persist generated alerts and upsert account documents into Cosmos DB.

Returns a concise metadata dictionary describing processing totals and alert counts.
"""

# processor/account_processor.py
import logging
from typing import Dict, Any, List

from ..utils.csv_utils import parse_csv
from ..utils.date_utils import parse_ts
from ..utils.sanitizer import strip, to_float

from ..validator.account_validator import validate_account_row
from ..alerts.profile_alerts import generate_profile_alerts
from ..client.cosmos_client import upsert_item, upsert_items_parallel


def _build_account_doc(normalized: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a Cosmos-friendly account document from a normalized CSV row.

    Args:
        normalized: Dict[str, Any] - row with trimmed string values (raw CSV headers preserved).

    Returns:
        Dict[str, Any]: Document shaped for insertion into the PROFILE container.

    Logic:
        - Normalize/parse numeric and date fields (Balance, AccountOpenDate).
        - Create an 'Account' subdocument containing relevant account metadata and KYC fields.
        - Return a top-level doc with 'id', 'AccountNumber', 'CustomerID' and 'Account'.

    Notes:
        - The returned 'id' uses the AccountNumber to satisfy Cosmos PK requirements.
        - Date fields are returned as date-only strings when the time portion is midnight.
    """
    # normalized row keys are raw strings; convert & organize into Account subdoc
    accnum = strip(normalized.get("AccountNumber"))
    custid = strip(normalized.get("CustomerID"))

    # parse/normalize balance and open date
    balance = to_float(normalized.get("Balance")) or 0.0
    open_dt = parse_ts(normalized.get("AccountOpenDate"))
    # Prefer date-only strings when the parsed datetime has no meaningful time
    if open_dt:
        try:
            if getattr(open_dt, "hour", None) == 0 and getattr(open_dt, "minute", None) == 0 and getattr(open_dt, "second", None) == 0:
                open_iso = open_dt.date().isoformat()
            else:
                open_iso = open_dt.isoformat()
        except Exception:
            open_iso = str(open_dt)
    else:
        open_iso = None

    account = {
        "AccountHolderName": strip(normalized.get("AccountHolderName")),
        "BankName": strip(normalized.get("BankName")),
        "BranchName": strip(normalized.get("BranchName")),
        "IFSC_Code": strip(normalized.get("IFSC_Code")),
        "AccountType": strip(normalized.get("AccountType")),
        "AccountStatus": strip(normalized.get("AccountStatus")),
        "AccountOpenDate": open_iso,
        "Balance": balance,
        "Currency": strip(normalized.get("Currency")),
        "KYC_Done": strip(normalized.get("KYC_Done")),
        "KYC_DocID": strip(normalized.get("KYC_DocID")),
        "KYC_DocumentVerificationStatus": strip(normalized.get("KYC_DocumentVerificationStatus")),
    }

    doc = {
        "id": str(accnum),
        "AccountNumber": accnum,
        "CustomerID": custid,
        "Account": account,
    }
    return doc


def process_account_profiles(text: str, file_name: str, profile_container, alert_container) -> Dict[str, Any]:
    """
    Process `account_master` CSV content, upsert account docs into PROFILE container and create profile alerts.

    Args:
        text (str): CSV content as a single string.
        file_name (str): Original filename (used for metadata/quarantine naming).
        profile_container: Cosmos container client for profile/account documents.
        alert_container: Cosmos container client for alerts.

    Returns:
        dict: Metadata summary including keys: rows_parsed, valid, invalid, quarantined, alerts.

    Processing steps (high level):
        1. Parse CSV into rows and validate using `validate_account_row`.
        2. Convert valid rows into account documents via `_build_account_doc`.
        3. Query existing profile docs to obtain customer-level data (e.g., AnnualIncome) used by alert heuristics.
        4. Generate profile alerts using `generate_profile_alerts` and persist alerts to alert_container.
        5. Upsert account documents in parallel to the profile_container.

    Error handling:
        - Validation errors are collected into `bad_rows` and returned to caller for quarantine.
        - Cosmos/network errors are logged; upsert failures are counted conservatively.
    """
    rows = parse_csv(text)
    total = len(rows)
    if total == 0:
        return {"rows_parsed": 0, "valid": 0, "invalid": 0, "quarantined": 0, "alerts": 0}

    valid_rows: List[Dict[str, Any]] = []
    bad_rows: List[List[str]] = []
    header = list(rows[0].keys()) if rows else []

    # ----------------------------
    # 1. Validation
    # ----------------------------
    for i, raw in enumerate(rows, start=1):
        errors = validate_account_row(raw)
        if errors:
            # Preserve original row shape for quarantine (aligned with header)
            bad_rows.append([raw.get(h, "") for h in header])
            logging.warning(f"Account row {i} invalid: {errors}")
        else:
            valid_rows.append(raw)

    quarantined = len(bad_rows)

    # ----------------------------
    # 2. Build account docs
    # ----------------------------
    docs = [_build_account_doc(r) for r in valid_rows]

    # ----------------------------
    # 3. Enrichment: fetch customer docs for income data
    # ----------------------------
    customer_map: Dict[str, Dict[str, Any]] = {}
    customer_ids = sorted({d["CustomerID"] for d in docs if d.get("CustomerID")})
    for cid in customer_ids:
        try:
            query = "SELECT * FROM c WHERE c.CustomerID=@cid"
            params = [{"name": "@cid", "value": cid}]
            items = list(profile_container.query_items(query=query, parameters=params, enable_cross_partition_query=True))
            # find a document that has a 'Customer' subdoc or top-level income
            cust_doc = None
            for it in items:
                if it.get("Customer"):
                    cust_doc = it.get("Customer")
                    break
            if not cust_doc and items:
                # fallback: attempt to construct customer doc from top-level fields
                candidate = items[0]
                cust_doc = {k: v for k, v in candidate.items() if k not in ("id", "Account", "AccountNumber")}
            if cust_doc:
                customer_map[cid] = cust_doc
        except Exception as e:
            logging.warning(f"Failed to query customer data for CustomerID={cid}: {e}")

    # ----------------------------
    # 4. Generate profile alerts
    # ----------------------------
    all_alerts: List[Dict[str, Any]] = []
    for doc in docs:
        cust_doc = customer_map.get(doc.get("CustomerID"))
        alerts = generate_profile_alerts(doc, customer_doc=cust_doc)
        all_alerts.extend(alerts)

    # Persist alerts first (best-effort)
    alerts_written = 0
    for a in all_alerts:
        try:
            upsert_item(alert_container, a)
            alerts_written += 1
        except Exception as e:
            logging.error(f"Failed to persist profile alert {a.get('id')}: {e}")

    # ----------------------------
    # 5. Upsert account docs in parallel
    # ----------------------------
    ingested = 0
    failed = 0
    if docs:
        try:
            s, f = upsert_items_parallel(profile_container, docs)
            ingested += s
            failed += f
        except Exception as e:
            logging.error(f"Failed to upsert account docs: {e}")
            # fallback conservative counts
            failed += len(docs)

    return {
        "rows_parsed": total,
        "valid": len(docs),
        "invalid": len(bad_rows),
        "quarantined": quarantined,
        "alerts": alerts_written,
    }
