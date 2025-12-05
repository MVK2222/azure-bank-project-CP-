import os
import logging
import json
import csv
import io
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser

import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient, PartitionKey

# ---- Configuration from environment ----
SERVICE_BUS_CONN = os.environ.get("SERVICE_BUS_CONNECTION_STRING")  # used by trigger
STORAGE_CONN = os.environ.get("STORAGE_CONNECTION_STRING")
COSMOS_CONN = os.environ.get("COSMOS_DB_CONNECTION_STRING")
COSMOS_DB = os.environ.get("COSMOS_DB_NAME", "operaton-storage-db")
ATM_CONTAINER = os.environ.get("ATM_CONTAINER", "ATMTransactions")
UPI_CONTAINER = os.environ.get("UPI_CONTAINER", "UPIEvents")
PROFILE_CONTAINER = os.environ.get("PROFILE_CONTAINER", "AccountProfile")
ALERT_CONTAINER = os.environ.get("ALERTS_CONTAINER", "FraudAlerts")
QUARANTINE_CONTAINER = os.environ.get("QUARANTINE_CONTAINER", "quarantine")
METADATA_CONTAINER = os.environ.get("METADATA_CONTAINER", "metadata")

# Simple fraud thresholds — tweak as needed
HIGH_VALUE_THRESHOLD = 50000.0
VELOCITY_WINDOW_MINUTES = 5
VELOCITY_TXN_COUNT = 3

# Initialize clients once (cold start cost)
blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONN)
cosmos_client = CosmosClient.from_connection_string(COSMOS_CONN)
database = cosmos_client.create_database_if_not_exists(id=COSMOS_DB)

# Ensure containers (Cosmos) exist with basic partition keys
def ensure_cosmos_container(container_id, partition_key):
    try:
        container = database.create_container_if_not_exists(
            id=container_id,
            partition_key=PartitionKey(path=partition_key),
            offer_throughput=400
        )
        return container
    except Exception as e:
        logging.error(f"Failed to create or get Cosmos container {container_id}: {e}")
        raise

atm_container = ensure_cosmos_container(ATM_CONTAINER, "/TransactionID")
upi_container = ensure_cosmos_container(UPI_CONTAINER, "/TransactionID")
profile_container = ensure_cosmos_container(PROFILE_CONTAINER, "/CustomerID")
alert_container = ensure_cosmos_container(ALERT_CONTAINER, "/AccountNumber")

# Utility: write metadata to storage (JSON)
def write_metadata_blob(container_name, blob_name, content_dict):
    try:
        container_client = blob_service_client.get_container_client(container_name)
        # create container if not exists (storage container)
        try:
            container_client.create_container()
        except Exception:
            pass
        data = json.dumps(content_dict, default=str).encode("utf-8")
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(data, overwrite=True)
    except Exception as e:
        logging.error(f"Failed to write metadata blob {container_name}/{blob_name}: {e}")

# Utility: write quarantine CSV to storage
def write_quarantine_blob(container_name, blob_name, header, bad_rows):
    try:
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.create_container()
        except Exception:
            pass
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(bad_rows)
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(output.getvalue().encode("utf-8"), overwrite=True)
    except Exception as e:
        logging.error(f"Failed to write quarantine blob {container_name}/{blob_name}: {e}")

# Basic validation rules for a row depending on source_type
def validate_row(source_type, header, row):
    # row is list aligned with header
    # convert to dict
    data = dict(zip(header, row))
    errors = []

    # Example generic checks
    txn_id = (data.get("TransactionID") or "").strip()
    if not txn_id:
        errors.append("Missing TransactionID")
    else:
        data["TransactionID"] = txn_id  # normalize whitespace
    if source_type == "ATM" or source_type == "UPI":
        # amount numeric and >0 (support both TransactionAmount and Amount)
        amt_raw = data.get("TransactionAmount")
        if amt_raw is None or (isinstance(amt_raw, str) and not amt_raw.strip()):
            amt_raw = data.get("Amount")
        try:
            amt_val = float((amt_raw if amt_raw is not None else "0") or "0")
            if amt_val <= 0:
                errors.append("Amount <= 0")
        except Exception:
            errors.append("Invalid Amount")
        # timestamp parseable (support both TransactionTime and Timestamp)
        ts_str = data.get("TransactionTime")
        if ts_str is None or (isinstance(ts_str, str) and not ts_str.strip()):
            ts_str = data.get("Timestamp")
        try:
            parsed_ts = date_parser.parse(ts_str) if ts_str else None
            if not parsed_ts:
                errors.append("Missing Timestamp")
            else:
                # normalize: store back as ISO string in TransactionTime
                data["TransactionTime"] = parsed_ts.isoformat()
        except Exception:
            errors.append("Invalid Timestamp")
    return errors, data

# Simple in-batch fraud detection
def in_batch_fraud_detection(parsed_rows):
    alerts = []

    # =========================
    # Rule 1: HIGH VALUE FRAUD
    # =========================
    for r in parsed_rows:
        try:
            amt = float(r.get("TransactionAmount") or r.get("Amount") or 0)
            if amt >= HIGH_VALUE_THRESHOLD:
                alerts.append({
                    "alert_id": f"ALERT_HIGHVALUE_{r.get('TransactionID')}",
                    "type": "HIGH_VALUE",
                    "reason": f"Transaction amount {amt} exceeds threshold {HIGH_VALUE_THRESHOLD}",
                    "transaction": r
                })
        except:
            pass

    # ==================================
    # Rule 2: VELOCITY FRAUD (Burst Txn)
    # ==================================
    by_customer = {}
    for r in parsed_rows:
        cid = r.get("CustomerID") or r.get("AccountNumber") or "UNKNOWN"
        try:
            ts = date_parser.parse(r.get("Timestamp") or r.get("TransactionTime"))
        except:
            continue

        by_customer.setdefault(cid, []).append((ts, r))

    window = timedelta(minutes=VELOCITY_WINDOW_MINUTES)

    for cid, items in by_customer.items():
        items.sort(key=lambda x: x[0])

        for i in range(len(items)):
            j = i + 1
            count = 1
            while j < len(items) and (items[j][0] - items[i][0]) <= window:
                count += 1
                j += 1

            if count >= VELOCITY_TXN_COUNT:
                group_txns = [it[1] for it in items[i:j]]
                alerts.append({
                    "alert_id": f"ALERT_VELOCITY_{cid}_{items[i][0].isoformat()}",
                    "type": "VELOCITY_ATTACK",
                    "reason": f"{count} transactions within {VELOCITY_WINDOW_MINUTES} minutes",
                    "transactions": group_txns
                })

    # ====================================
    # Rule 3: GEO LOCATION SWITCHING FRAUD
    # ====================================
    for cid, items in by_customer.items():
        loc_map = {}
        for ts, r in items:
            loc = r.get("Location")
            loc_map.setdefault(loc, []).append(ts)

        # If more than 2 cities seen in < 10 minutes → suspicious
        timestamps = []
        for loc, tslist in loc_map.items():
            for t in tslist:
                timestamps.append((loc, t))

        timestamps.sort(key=lambda x: x[1])
        for i in range(len(timestamps)):
            city1, t1 = timestamps[i]
            for j in range(i + 1, len(timestamps)):
                city2, t2 = timestamps[j]
                if city1 != city2 and (t2 - t1) <= timedelta(minutes=10):
                    alerts.append({
                        "alert_id": f"ALERT_GEO_{cid}_{t1.isoformat()}",
                        "type": "GEO_LOCATION_SWITCH",
                        "reason": f"Transaction from {city1} → {city2} within 10 minutes",
                        "transactions": [timestamps[i], timestamps[j]]
                    })

    # =====================================
    # Rule 4: CONTINUOUS DEBIT / BALANCE DRAIN
    # =====================================
    for cid, items in by_customer.items():
        total_amt = 0
        start = items[0][0]
        for ts, r in items:
            try:
                amt = float(r.get("TransactionAmount") or r.get("Amount") or 0)
            except:
                amt = 0
            total_amt += amt

            if (ts - start) <= timedelta(minutes=10) and total_amt >= 100000:
                alerts.append({
                    "alert_id": f"ALERT_BALANCE_DRAIN_{cid}_{ts.isoformat()}",
                    "type": "BALANCE_DRAIN",
                    "reason": f"Total withdrawals {total_amt} in 10 minutes",
                    "transactions": [x[1] for x in items]
                })
                break

    # =====================================
    # Rule 5: STATUS BASED SUSPICIOUS PATTERNS
    # =====================================
    for r in parsed_rows:
        status = (r.get("Status") or "").upper()
        amt = float(r.get("TransactionAmount") or r.get("Amount") or 0)

        if status in ["FAILED", "CANCELLED"] and amt > 40000:
            alerts.append({
                "alert_id": f"ALERT_STATUS_FAIL_{r.get('TransactionID')}",
                "type": "FAILED_HIGH_VALUE",
                "reason": "High-value FAILED/CANCELLED transaction",
                "transaction": r
            })

        if status == "PENDING" and amt > 30000:
            alerts.append({
                "alert_id": f"ALERT_PENDING_HIGH_{r.get('TransactionID')}",
                "type": "PENDING_HIGH_VALUE",
                "reason": "High-value transaction stuck in PENDING status",
                "transaction": r
            })

    # =====================================
    # Rule 6: DEVICE ID ANOMALY (UPI Only)
    # =====================================
    by_device = {}
    for r in parsed_rows:
        dev = r.get("DeviceID")
        if not dev:
            continue
        try:
            ts = date_parser.parse(r.get("Timestamp") or r.get("TransactionTime"))
        except:
            continue
        by_device.setdefault(dev, []).append((ts, r))

    for dev, items in by_device.items():
        if len(items) >= 4:  # more than 4 UPI transactions via SAME device
            alerts.append({
                "alert_id": f"ALERT_DEVICE_{dev}",
                "type": "DEVICE_MISUSE",
                "reason": f"Multiple UPI transactions detected from device {dev}",
                "transactions": [x[1] for x in items]
            })

    # =====================================
    # Rule 7: ACCOUNT / CUSTOMER MISMATCH
    # =====================================
    for r in parsed_rows:
        acc = r.get("AccountNumber")
        cid = r.get("CustomerID")
        if acc and cid and not acc.startswith(acc[-3:]):  # simple mismatch logic placeholder
            alerts.append({
                "alert_id": f"ALERT_ACCOUNT_MISMATCH_{r.get('TransactionID')}",
                "type": "ACCOUNT_MISMATCH",
                "reason": "AccountNumber and CustomerID pattern mismatch",
                "transaction": r
            })

    return alerts

# Main function
def main(msg: func.ServiceBusMessage):
    logging.info("BatchIngestionFunction triggered by Service Bus message.")
    try:
        body = msg.get_body().decode('utf-8')
        message = json.loads(body)
    except Exception as e:
        logging.error(f"Failed to parse Service Bus message: {e}")
        return

    file_url = message.get("file_url")
    file_name = message.get("file_name")
    source_type = message.get("source_type", "UNKNOWN").upper()

    logging.info(f"Processing file: {file_name} - {file_url} - source_type={source_type}")

    # Record metadata
    metadata = {
        "file_name": file_name,
        "file_url": file_url,
        "source_type": source_type,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "status": "PROCESSING"
    }

    # Save initial metadata blob
    md_blob_name = f"{file_name}.metadata.json"
    write_metadata_blob(METADATA_CONTAINER, md_blob_name, metadata)

    # Download blob content
    try:
        # file_url is like https://<account>.blob.core.windows.net/<container>/<path>
        # parse container and blob path
        parts = file_url.split("/")
        # parts: ['https:', '', 'account.blob.core.windows.net', 'container', 'path', 'to', 'file.csv']
        container_name = parts[3]
        blob_path = "/".join(parts[4:])
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_path)
        downloader = blob_client.download_blob()
        raw_bytes = downloader.readall()
        text = raw_bytes.decode("utf-8")
    except Exception as e:
        logging.error(f"Failed to download blob {file_url}: {e}")
        metadata["status"] = "DOWNLOAD_FAILED"
        metadata["error"] = str(e)
        write_metadata_blob(METADATA_CONTAINER, md_blob_name, metadata)
        return

    # Parse CSV
    csv_reader = csv.reader(io.StringIO(text))
    try:
        header = next(csv_reader)
    except StopIteration:
        logging.error("CSV file is empty.")
        metadata["status"] = "EMPTY_FILE"
        write_metadata_blob(METADATA_CONTAINER, md_blob_name, metadata)
        return

    parsed_rows = []
    bad_rows = []
    row_num = 1  # header is row 0
    for row in csv_reader:
        row_num += 1
        errors, data = validate_row(source_type, header, row)
        if errors:
            bad_rows.append(row)
            logging.warning(f"Row {row_num} invalid: {errors}")
            continue
        # normalize keys: strip whitespace
        normalized = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        # do NOT synthesize TransactionID; only ingest rows with real TransactionID
        parsed_rows.append(normalized)

    # If bad rows exist, write to quarantine
    if bad_rows:
        q_blob_name = f"{file_name}_badrows.csv"
        write_quarantine_blob(QUARANTINE_CONTAINER, q_blob_name, header, bad_rows)
        logging.info(f"Wrote {len(bad_rows)} bad rows to {QUARANTINE_CONTAINER}/{q_blob_name}")

    # Upsert parsed rows into Cosmos DB containers
    success_count = 0
    fail_count = 0
    target_container = atm_container if source_type == "ATM" else upi_container if source_type == "UPI" else atm_container

    for r in parsed_rows:
        try:
            # Ensure required ID & partition key presence for Cosmos DB
            txn_id = r.get("TransactionID")
            if not txn_id or not str(txn_id).strip():
                raise ValueError("TransactionID missing for parsed row; should have been quarantined")
            # Cosmos requires an 'id' field; set it to TransactionID
            r["id"] = str(r["TransactionID"]).strip()

            # upsert_item will create or replace
            target_container.upsert_item(r)
            success_count += 1
        except Exception as e:
            logging.error(f"Failed to upsert row {r.get('TransactionID') or r.get('id')}: {e}; item keys: {list(r.keys())}")
            fail_count += 1

    logging.info(f"Upserted {success_count} rows, failed {fail_count} rows into container {target_container.id}")

    # In-batch fraud scan
    alerts = in_batch_fraud_detection(parsed_rows)
    logging.info(f"Generated {len(alerts)} alerts from in-batch fraud detection")
    for alert in alerts:
        # normalize alert document
        try:
            alert_doc = {
                "id": alert.get("alert_id"),
                "type": alert.get("type"),
                "reason": alert.get("reason"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "payload": alert.get("transaction") or alert.get("transactions")
            }
            # partition key is /AccountNumber in alert container; attempt to supply an account number
            acct = None
            payload = alert_doc["payload"]
            if isinstance(payload, dict):
                acct = payload.get("AccountNumber") or payload.get("CustomerID")
            elif isinstance(payload, list) and len(payload) > 0:
                # Find first dict element
                first_dict = next((p for p in payload if isinstance(p, dict)), None)
                if first_dict:
                    acct = first_dict.get("AccountNumber") or first_dict.get("CustomerID")
                else:
                    # Normalize non-dict entries into a simple dict structure
                    normalized_list = []
                    for p in payload:
                        if isinstance(p, tuple) and len(p) == 2:
                            normalized_list.append({"Location": p[0], "Timestamp": p[1].isoformat() if hasattr(p[1], "isoformat") else str(p[1])})
                        else:
                            normalized_list.append({"value": str(p)})
                    alert_doc["payload"] = normalized_list
            if acct:
                alert_doc["AccountNumber"] = acct
            else:
                alert_doc["AccountNumber"] = "UNKNOWN"

            # upsert into alerts container
            alert_container.upsert_item(alert_doc)
        except Exception as e:
            logging.error(f"Failed to upsert alert {alert.get('alert_id')}: {e}")

    # Finalize metadata
    metadata["status"] = "COMPLETED"
    metadata["rows_parsed"] = len(parsed_rows)
    metadata["rows_bad"] = len(bad_rows)
    metadata["rows_ingested"] = success_count
    metadata["rows_failed_ingest"] = fail_count
    metadata["alerts_generated"] = len(alerts)
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    write_metadata_blob(METADATA_CONTAINER, md_blob_name, metadata)

    logging.info(f"Finished processing file {file_name}. Metadata written: {METADATA_CONTAINER}/{md_blob_name}")
