# Banking Data Platform – Azure Capstone Project

Event-Driven + Batch ETL Pipeline with Fraud Detection, Cosmos DB, Azure Functions, and Data Lake

---

## 1. Project Overview

This project implements a modern, cloud-native banking data platform capable of:

- Ingesting ATM, UPI, and Customer transaction records
- Processing data via Event Grid → Functions → Service Bus
- Loading validated records into Cosmos DB (NoSQL Operational Store)
- Running fraud detection rules on each batch
- Writing alerts to a dedicated FraudAlerts container
- Storing raw and curated data in ADLS Gen2

This architecture follows industry patterns used in real banks for:

- Real-time & batch ingestion
- Fraud detection
- Customer 360
- Scalable analytics

---

## 2. Architecture (High-Level)

- ADLS Gen2 → Raw Storage
- Event Grid → Blob Created Trigger
- Azure Function 1 → Metadata Validation + Service Bus Message (FileArrivalFunction)
- Service Bus Queue → Event Orchestration
- Azure Function 2 → Batch Processor (BatchIngestionFunction)
  - Reads file from ADLS
  - Validates schema
  - Inserts valid rows into Cosmos DB
  - Sends invalid rows to quarantine
  - Runs fraud detection rules
  - Writes alerts into Cosmos DB
  - Writes metadata logs
- Cosmos DB → Operational Store
- Logging & Monitoring via App Insights

---

## 3. Repository Structure

```
functions/
  host.json
  local.settings.json
  requirements.txt
  BatchIngestionFunction/
    __init__.py
    function.json
  FileArrivalFunction/
    __init__.py
    function.json
README.md
```

---

## 4. What Was Implemented Today

### 4.1 Azure Resources Created

- Storage Account (ADLS Gen2)
  - Raw containers:
    - raw/atm/
    - raw/upi/
    - raw/customers/
  - Quarantine container: quarantine/
  - System container: system/
- Service Bus Namespace
  - Queue: banking-ingest-queue
- Cosmos DB (Core SQL API)
  - Containers:
    - ATMTransactions (PK: /TransactionID)
    - UPIEvents (PK: /TransactionID)
    - AccountProfile (PK: /CustomerID)
    - FraudAlerts (PK: /AccountNumber)
- Azure Function App (Python 3.10)
  - Deployed 2 functions
- Event Grid Subscription
  - Triggered on Blob Created
  - Filtered by Subject Paths and data.api == PutBlob

### 4.2 Functions Implemented Today

#### Function 1: FileArrivalFunction (Event Grid Trigger)

- Validates file metadata
- Identifies file type (ATM, UPI, Customer)
- Publishes pointer message to Service Bus
- Best practices:
  - Idempotent design
  - Error catching
  - Logging
  - Environment variables only (no hardcoded secrets)

#### Function 2: BatchIngestionFunction (Service Bus Trigger)

- Downloads file from ADLS
- Parses CSV
- Validates each row
- Writes invalid rows → Quarantine container
- Inserts valid rows into Cosmos DB
- Generates fraud alerts
- Writes metadata logs → ADLS
- Best practices:
  - Upsert operations for idempotency
  - Partitioned Cosmos DB inserts
  - Normalization of keys & timestamps
  - Error isolation per record
  - Metadata-driven processing

---

## 5. Cloud Best Practices Followed Today

### Security / Identity

- No secrets in code
- Using environment variables
- Connection strings securely in App Settings
- IAM roles: Storage Blob Data Contributor, Cosmos DB Operator

### Scalability

- Event Grid decouples ingestion from compute
- Service Bus Queue supports backpressure
- Cosmos DB with partition keys for scale-out

### Reliability

- Metadata file written before & after processing
- Quarantine folder for corrupt rows
- Upsert ensures retry-safety
- No assumption that order equals correctness

### Observability

- Logging with context
- Warnings for bad rows
- Metadata logs (rows parsed, rows failed, alerts generated)
- Ready for ops dashboards (e.g., Power BI)

---

## 6. Fraud Detection Rules Implemented Today

Documented rules so teammates & reviewers understand detection logic:

- Rule 1 — High-Value Fraud: Amount ≥ ₹50,000 triggers alert
- Rule 2 — Velocity Attack: ≥ 3 transactions within 5 minutes
- Rule 3 — Geo Location Switching: Different cities within 10 minutes
- Rule 4 — Balance Drain: Total withdrawals > ₹100,000 in 10 minutes
- Rule 5 — Status-Based Fraud: High-value FAILED or PENDING transactions
- Rule 6 — Device Anomaly: Same device used for rapid UPI transactions
- Rule 7 — Account / Customer mismatch: Basic pattern mismatch

Alerts are persisted in Cosmos DB (FraudAlerts).

---

## 7. Test Data Created Today

Dataset includes:

- Normal ATM + UPI transactions
- Fraudulent transactions:
  - High-value
  - Velocity
  - Balance drain
  - Geo shift
- Failed, Pending, Cancelled transactions
- Dirty rows for quarantine testing

Files:

- atm_final_test_ready.csv
- upi_final_test_ready.csv

---

## 8. Testing Performed Today

- Test 1 — Event Grid Trigger: Upload ATM file, verify FileArrivalFunction triggered
- Test 2 — Service Bus Message: Verify queue receives and processor consumes
- Test 3 — Cosmos DB Inserts: Valid rows in containers, bad rows in Quarantine
- Test 4 — Fraud Alerts: Alerts generated with expected schema

---

## 9. What Will Be Done Tomorrow (TODO)

- Implement Bronze → Silver → Gold layers in Databricks
- Create Delta tables for ATM and UPI
- Build Customer 360 table
- Build Power BI dashboards
- Add CI/CD pipelines
- Add application log monitoring in Log Analytics

---

## 10. How to Run This Project Locally

Prerequisites:

- Python 3.10+
- Azure Functions Core Tools
- Azure CLI
- Valid `functions/local.settings.json`

Windows PowerShell commands:

```powershell
# From repo root
cd D:\Mazenet\azure-bank-platform\functions

# Create and activate venv
python -m venv .venv
. .venv\Scripts\Activate.ps1

# Install deps and start Functions
pip install -r requirements.txt
func start
```

Environment variables (local.settings.json → Values):

- AzureWebJobsStorage
- FUNCTIONS_WORKER_RUNTIME = python
- COSMOS_DB_CONNECTION_STRING
- COSMOS_DB_NAME = operaton-storage-db
- SERVICE_BUS_CONNECTION_STRING
- STORAGE_CONNECTION_STRING
- ATM_CONTAINER = ATMTransactions
- UPI_CONTAINER = UPIEvents
- ALERTS_CONTAINER = FraudAlerts
- PROFILE_CONTAINER = AccountProfile
- QUARANTINE_CONTAINER = quarantine
- METADATA_CONTAINER = system

---

## 11. Tools & Technologies

- Azure Functions (Python)
- Azure Event Grid
- Azure Service Bus
- Azure Cosmos DB (Core SQL API)
- Azure Storage ADLS Gen2
- Python 3.10
- Azure CLI

---

## Appendix: Day-by-Day Setup Summary

Day 1: Storage & Event Simulation

- Create ADLS Gen2 containers: raw/atm, raw/upi, raw/customers, quarantine, system
- Upload test CSVs: atm_20250101.csv, upi_20250101.csv
- Configure Event Grid System Topic (BlobCreated, filter data.api == PutBlob)
- Create Event Grid subscription to Function (FileArrivalFunction)
- Create Service Bus namespace and queue banking-ingest-queue

Day 2: Processing Layer

- Modify FileArrivalFunction to send pointer messages to Service Bus
- Implement BatchIngestionFunction to parse and validate CSV rows
- Upsert valid transactions to Cosmos DB; quarantine invalid rows
- Generate basic fraud alerts and write to FraudAlerts
- Persist processing metadata to system container
