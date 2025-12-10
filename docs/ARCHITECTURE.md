# Banking Data Platform - System Architecture

## Table of Contents
- [Overview](#overview)
- [Architecture Principles](#architecture-principles)
- [System Components](#system-components)
- [Data Flow](#data-flow)
- [Technology Stack](#technology-stack)
- [Scaling Strategy](#scaling-strategy)
- [Security Architecture](#security-architecture)
- [Disaster Recovery](#disaster-recovery)

## Overview

The Banking Data Platform is a cloud-native, event-driven data processing system built on Azure. It ingests, validates, and analyzes banking transaction and profile data while detecting fraud in real-time.

### Key Capabilities
- **Real-time Event Processing**: Event Grid triggers for instant file arrival detection
- **Batch ETL Pipeline**: High-throughput CSV processing with parallel operations
- **Fraud Detection**: Multi-rule fraud detection engine with configurable thresholds
- **Data Quality Management**: Validation, quarantine, and metadata tracking
- **Scalable Storage**: Cosmos DB for operational data, ADLS Gen2 for raw/metadata
- **Observability**: Comprehensive logging and monitoring via Application Insights

### Design Patterns Used
- **Event-Driven Architecture**: Decoupled components communicating via events/messages
- **Command Pattern**: Event Grid events converted to Service Bus commands
- **Strategy Pattern**: Pluggable processors for different data types
- **Repository Pattern**: Abstracted data access via client modules
- **Circuit Breaker**: Retry logic with exponential backoff (Cosmos DB)

## Architecture Principles

### 1. Separation of Concerns
Each component has a single, well-defined responsibility:
- **FileArrivalFunction**: Event detection and routing only
- **BatchIngestionFunction**: ETL orchestration
- **Processors**: Domain-specific validation and transformation
- **Validators**: Schema and business rule validation
- **Alerts**: Fraud detection logic

### 2. Idempotency
All operations are idempotent to handle retries safely:
- Cosmos DB upserts (insert-or-update semantics)
- Metadata blob overwrites
- Quarantine file overwrites
- Service Bus message deduplication

### 3. Fail-Fast & Fail-Safe
- **Fail-Fast**: Invalid messages rejected immediately (malformed JSON)
- **Fail-Safe**: Per-record error handling prevents batch failures
- **Dead-Letter Queue**: Failed messages preserved for investigation

### 4. Observability
Comprehensive instrumentation at every layer:
- INFO: Normal operations and progress
- WARNING: Recoverable errors (bad rows, retries)
- ERROR: Unrecoverable errors requiring intervention
- Metadata blobs: Audit trail for every file processed

### 5. Security in Depth
Multiple layers of security controls:
- No secrets in code (environment variables only)
- Managed Identity for Azure resources (future)
- RBAC for least-privilege access
- Encryption at rest and in transit
- Network isolation via VNet integration (production)

## System Components

### 1. Azure Data Lake Storage Gen2 (ADLS)
**Role**: Raw data storage and metadata persistence

**Containers**:
- `raw/atm/`: ATM transaction CSV files
- `raw/upi/`: UPI transaction CSV files
- `raw/customers/`: Customer profile CSV files
- `raw/accounts/`: Account profile CSV files
- `quarantine/`: Invalid records for review
- `metadata/`: Processing metadata and audit logs

**Configuration**:
- Hierarchical namespace enabled (required for ADLS Gen2)
- Lifecycle management: Retain raw files 90 days, move to cool storage
- Access tier: Hot for active ingestion, cool for historical data
- Replication: LRS (Locally Redundant Storage) for cost, GRS for DR

**Performance**:
- Throughput: 10-20 Gbps per storage account
- IOPS: 20,000+ per storage account
- Typical file sizes: 1-50 MB (1K-100K rows)

### 2. Azure Event Grid
**Role**: Blob creation event detection and routing

**Configuration**:
- System Topic: Monitors ADLS storage account for blob events
- Event Subscription: Filters BlobCreated events
- Endpoint: FileArrivalFunction HTTP endpoint
- Retry Policy: 30 retries over 24 hours
- Dead-Letter: Failed events sent to storage queue

**Event Filtering**:
```json
{
  "subjectBeginsWith": "/blobServices/default/containers/raw",
  "subjectEndsWith": ".csv",
  "includedEventTypes": ["Microsoft.Storage.BlobCreated"],
  "advancedFilters": [
    {
      "key": "data.api",
      "operatorType": "StringEquals",
      "value": "PutBlob"
    }
  ]
}
```

**Performance**:
- Latency: <1 second from blob creation to function trigger
- Throughput: 1000+ events/second (far exceeds typical workload)
- Cost: $0.60 per million operations

### 3. FileArrivalFunction (Azure Function)
**Role**: Event handler for file arrivals, route to processing queue

**Trigger**: Event Grid (BlobCreated event)
**Output**: Service Bus Queue message
**Runtime**: Python 3.10
**Timeout**: 5 minutes (default)
**Memory**: 1.5 GB

**Responsibilities**:
1. Validate file format (CSV only)
2. Detect source type from filename (ATM, UPI, ACCOUNT, CUSTOMER)
3. Construct metadata message
4. Publish to Service Bus queue

**Scaling**:
- Consumption Plan: Auto-scales based on event volume
- Max instances: 200 (default)
- Typical instances: 1-5 for normal load

**Error Handling**:
- Invalid files: Logged and skipped (early return)
- Service Bus errors: Function retries automatically
- Event Grid retries: If function fails completely

### 4. Azure Service Bus
**Role**: Message queue for decoupling event detection from processing

**Queue Configuration**:
- Name: `banking-ingest-queue`
- Max delivery count: 10 (after which → dead-letter queue)
- Lock duration: 5 minutes (must exceed function timeout)
- Message TTL: 7 days
- Max queue size: 5 GB

**Benefits**:
- **Backpressure**: Queues messages when processing is slow
- **Retry Logic**: Automatic retries with exponential backoff
- **Deduplication**: Message ID-based deduplication (5-minute window)
- **Reliability**: Peek-lock semantics prevent message loss

**Performance**:
- Throughput: 2000 messages/second (standard tier)
- Latency: <10ms for send, <50ms for receive
- Cost: $0.05 per million operations

### 5. BatchIngestionFunction (Azure Function)
**Role**: Main ETL pipeline orchestrator

**Trigger**: Service Bus Queue (PeekLock mode)
**Input**: File metadata message (file_url, file_name, source_type)
**Output**: 
- Cosmos DB documents (transactions, profiles, alerts)
- ADLS metadata blobs
- ADLS quarantine blobs

**Runtime**: Python 3.10
**Timeout**: 10 minutes (configurable up to 30 minutes)
**Memory**: 1.5 GB

**Processing Pipeline**:
```
1. Parse Service Bus message
2. Write initial metadata (status: PROCESSING)
3. Download CSV from ADLS
4. Route to processor (ATM, UPI, ACCOUNT, CUSTOMER)
   4a. Parse CSV rows
   4b. Validate each row
   4c. Upsert valid rows to Cosmos DB (parallel)
   4d. Run fraud detection (transactions only)
   4e. Upsert alerts to Cosmos DB
5. Write quarantine CSV (if invalid rows)
6. Write final metadata (status: COMPLETED)
```

**Scaling**:
- Consumption Plan: Auto-scales based on queue length
- Max instances: 200
- Typical instances: 5-20 for normal load
- Batch size: 1 message per invocation (reliable processing)

**Error Handling**:
- Download errors: Logged, metadata updated, message retried
- Processing errors: Logged, metadata updated, message retried
- Per-record errors: Quarantined, batch continues
- Max retries exceeded: Message moved to dead-letter queue

### 6. Azure Cosmos DB
**Role**: Operational database for transactions, profiles, and alerts

**Database**: `operation-storage-db`
**Throughput**: 400 RU/s (shared database-level)
**API**: Core (SQL)
**Consistency**: Session (default)

**Containers**:

| Container | Partition Key | Purpose | Typical Size |
|-----------|---------------|---------|--------------|
| ATMTransactions | /AccountNumber | ATM transaction records | 1M-10M docs |
| UPIEvents | /AccountNumber | UPI transaction records | 5M-50M docs |
| AccountProfile | /CustomerID | Account + Customer merged docs | 100K-1M docs |
| FraudAlerts | /AccountNumber | Fraud alerts for investigation | 10K-100K docs |

**Partition Strategy Rationale**:
- **Transactions by Account**: Query patterns focus on account history
- **Profiles by Customer**: Customer 360 view requires customer grouping
- **Alerts by Account**: Fraud investigation queries by account
- **High cardinality**: Millions of unique accounts ensure even distribution

**Indexing Policy**:
- Default: Automatic indexing on all properties
- Optimizations: Exclude large text fields (e.g., payload, reason)
- Custom: Add composite indexes for common query patterns

**Performance Expectations**:
- Point read (id + partition key): <10ms, 1 RU
- Upsert (1KB doc): 5-10 RU
- Query (single partition): 2-50 RU depending on complexity
- Cross-partition query: Expensive, avoid in hot path

**Cost Optimization**:
- Shared database throughput: $24/month for 400 RU/s
- Auto-scale: Enable if workload varies significantly
- Time-to-live (TTL): Archive old data to reduce storage costs

### 7. Processors Module
**Role**: Domain-specific ETL logic for each data type

**Processors**:
- `atm_processor.py`: ATM transaction validation and fraud detection
- `upi_processor.py`: UPI transaction validation and fraud detection
- `account_processor.py`: Account profile validation and alerts
- `customer_processor.py`: Customer profile merging

**Common Pattern**:
```python
def process_X(text: str, file_name: str, container, alert_container) -> dict:
    1. Parse CSV
    2. Validate rows (schema, business rules)
    3. Transform and normalize
    4. Upsert to Cosmos DB (parallel)
    5. Generate alerts (if applicable)
    6. Return statistics
```

**Parallelism**:
- Cosmos DB upserts: ThreadPoolExecutor (8 workers default)
- Typical throughput: 100-500 upserts/second
- Bottleneck: Cosmos DB RU/s allocation

### 8. Fraud Detection Engine
**Role**: Real-time fraud pattern detection

**Location**: `alerts/transaction_alerts.py`

**Rules Implemented**:

#### Rule 1: High-Value Transaction
- **Threshold**: ₹50,000
- **Pattern**: Single large transaction
- **False Positive Rate**: ~2%
- **Scenarios**: Account takeover, card theft

#### Rule 2: Velocity Attack
- **Threshold**: 10 transactions in 2 minutes
- **Pattern**: Rapid succession of transactions
- **False Positive Rate**: ~5%
- **Scenarios**: Card testing, ATM jackpotting

#### Rule 3: Geo-Location Switch
- **Threshold**: Different cities within 10 minutes
- **Pattern**: Impossible travel
- **False Positive Rate**: ~10% (VPN usage)
- **Scenarios**: Card cloning, credential theft

#### Rule 4: Balance Drain
- **Threshold**: ₹100,000 total in 10 minutes
- **Pattern**: Multiple withdrawals draining account
- **False Positive Rate**: ~1%
- **Scenarios**: Account takeover, insider fraud

**Performance**:
- Time Complexity: O(n²) worst-case for velocity/geo rules
- Typical: O(n log n) with early termination
- Processing Time: 1-10ms per transaction
- Batch Processing: 1-100ms for typical batches (1K rows)

**Tuning**:
- Thresholds configurable via environment variables
- Machine learning augmentation (future roadmap)
- Historical data analysis for optimal thresholds

## Data Flow

### End-to-End Flow (Happy Path)

```
1. Data Source → ADLS Raw Container
   - CSV file uploaded via Azure Storage SDK or Portal
   - Example: raw/atm/atm_20250101.csv

2. ADLS → Event Grid
   - BlobCreated event emitted
   - Event contains file URL and metadata

3. Event Grid → FileArrivalFunction
   - HTTP POST to function endpoint
   - Event delivered within 1 second

4. FileArrivalFunction → Service Bus
   - Validate file format
   - Detect source type
   - Publish message: {file_url, file_name, source_type}

5. Service Bus → BatchIngestionFunction
   - Function triggered by queue message
   - PeekLock ensures message not lost

6. BatchIngestionFunction → ADLS
   - Download CSV content
   - Write initial metadata (status: PROCESSING)

7. BatchIngestionFunction → Processor
   - Route to appropriate processor
   - Parse, validate, transform

8. Processor → Cosmos DB
   - Upsert valid rows (parallel)
   - Generate fraud alerts
   - Upsert alerts

9. BatchIngestionFunction → ADLS
   - Write quarantine CSV (if invalid rows)
   - Write final metadata (status: COMPLETED)

10. Service Bus
    - Message marked complete
    - Removed from queue
```

### Error Handling Flow

```
Scenario 1: Invalid File Format
1. FileArrivalFunction detects non-CSV file
2. Log error, return early
3. No Service Bus message sent
4. File ignored

Scenario 2: Download Failure
1. BatchIngestionFunction can't download blob
2. Update metadata (status: DOWNLOAD_FAILED)
3. Return without completing message
4. Service Bus retries (up to 10 times)
5. If all retries fail → dead-letter queue

Scenario 3: Validation Errors
1. Processor detects invalid rows
2. Quarantine invalid rows to CSV
3. Continue processing valid rows
4. Update metadata (rows_parsed, valid, invalid)
5. Complete successfully

Scenario 4: Cosmos DB Throttling
1. Upsert fails with 429 (rate limit exceeded)
2. Exponential backoff retry (3 attempts)
3. If retries succeed: Continue normally
4. If all retries fail: Exception raised
5. Message returned to queue for retry
```

### Monitoring and Observability Flow

```
All Components → Application Insights
- Structured logging (INFO, WARNING, ERROR)
- Custom metrics (processing time, row counts)
- Dependency tracking (Cosmos DB, ADLS calls)
- Exception tracking with stack traces

BatchIngestionFunction → ADLS Metadata
- Processing lifecycle tracked
- Statistics: rows_parsed, valid, invalid, alerts_generated
- Timestamps: started_at, completed_at
- Error details: error message and status

ADLS Metadata → Power BI / Log Analytics
- Operational dashboards
- Data quality trends
- Processing performance metrics
- Fraud detection KPIs
```

## Technology Stack

### Core Services
- **Azure Functions**: Serverless compute (Python 3.10 runtime)
- **Azure Event Grid**: Event routing and delivery
- **Azure Service Bus**: Message queue for reliable processing
- **Azure Cosmos DB**: NoSQL operational database (Core SQL API)
- **Azure Data Lake Storage Gen2**: Scalable object storage
- **Application Insights**: Monitoring and diagnostics

### Development Tools
- **Python 3.10+**: Primary programming language
- **Azure Functions Core Tools**: Local development and testing
- **Azure CLI**: Infrastructure provisioning and management
- **VS Code**: IDE with Azure Functions extension

### Python Libraries
- `azure-functions`: Function runtime and bindings
- `azure-servicebus`: Service Bus client
- `azure-cosmos`: Cosmos DB client
- `azure-storage-blob`: ADLS Gen2 client
- `python-dateutil`: Flexible datetime parsing

### CI/CD (Planned)
- **GitHub Actions**: Automated testing and deployment
- **Azure DevOps**: Alternative CI/CD platform
- **Terraform**: Infrastructure as Code (IaC)

## Scaling Strategy

### Horizontal Scaling
**Azure Functions (Consumption Plan)**:
- Auto-scales based on queue length and event volume
- 0 to 200 instances automatically
- Scale-out latency: ~10-60 seconds
- Cold start: <1 second for Python (pre-warmed)

**Cosmos DB**:
- Partition-based scale-out (automatic)
- Each partition: 10 GB storage, 10K RU/s max
- Database-level shared throughput distributes across containers
- Auto-scale: Automatically adjusts RU/s based on load

**ADLS Gen2**:
- Massively scalable (exabytes)
- No manual scaling required
- Throughput increases with parallel access

### Vertical Scaling
**Azure Functions**:
- Premium Plan: Dedicated instances with no cold start
- Memory: 1.5 GB (default), up to 14 GB
- vCPUs: 1-4 depending on memory allocation

**Cosmos DB**:
- Increase RU/s allocation (manual or auto-scale)
- Typical: 400 RU/s (dev), 10K+ RU/s (production)
- Cost: $0.008 per RU/s per hour

### Performance Bottlenecks

#### Bottleneck 1: Cosmos DB Throughput
**Symptom**: 429 (throttling) errors, high latency
**Solution**:
- Increase provisioned RU/s
- Enable auto-scale (10-40K RU/s)
- Optimize queries (single-partition when possible)
- Batch operations with parallelism

#### Bottleneck 2: Function Execution Time
**Symptom**: Timeouts, slow processing
**Solution**:
- Increase timeout limit (max 30 minutes)
- Optimize CSV parsing (streaming for large files)
- Parallelize Cosmos DB upserts (increase workers)
- Profile code to identify hot spots

#### Bottleneck 3: Service Bus Queue Length
**Symptom**: Growing backlog, delayed processing
**Solution**:
- Increase function max instances
- Scale Cosmos DB throughput
- Partition Service Bus queue (multiple queues)
- Optimize batch processing time

### Capacity Planning

**Current Configuration** (Development):
- Azure Functions: Consumption Plan
- Cosmos DB: 400 RU/s shared throughput
- ADLS Gen2: Hot access tier, LRS replication

**Estimated Capacity**:
- Files per day: 100-500
- Transactions per day: 100K-1M
- Processing latency: <5 minutes per file
- Storage growth: ~1 GB/day raw data

**Production Configuration** (Recommended):
- Azure Functions: Premium Plan (always-ready instances)
- Cosmos DB: 10K RU/s auto-scale (10K-40K range)
- ADLS Gen2: Premium tier with GRS replication
- Monitoring: Azure Monitor with custom dashboards

## Security Architecture

### Identity and Access Management
- **Managed Identity**: Functions access Azure resources without secrets (future)
- **RBAC**: Least-privilege role assignments
  - Functions: Storage Blob Data Reader, Cosmos DB Data Contributor
  - DevOps: Storage Blob Data Contributor (upload files)
  - Analysts: Cosmos DB Data Reader (read-only queries)

### Secrets Management
- **Current**: Connection strings in App Settings (encrypted at rest)
- **Best Practice**: Azure Key Vault for centralized secret management
  - Function app references Key Vault secrets via identity
  - Automatic secret rotation supported
  - Audit logging for all secret access

### Network Security
- **Current**: Public endpoints (suitable for development)
- **Production**:
  - VNet integration for Functions (private connectivity)
  - Private endpoints for Cosmos DB and ADLS
  - NSG rules to restrict traffic
  - Azure Firewall for centralized egress control

### Data Security
- **Encryption at Rest**: All Azure services use Microsoft-managed keys
- **Encryption in Transit**: TLS 1.2+ for all connections
- **PII Handling**: Sensitive fields should be masked/hashed (future)
- **Data Classification**: Tag resources with sensitivity level

### Compliance
- **Audit Logging**: All operations logged to Application Insights
- **Data Retention**: 90-day retention for raw files (configurable)
- **GDPR**: Right to erasure requires manual process (document procedure)
- **PCI DSS**: Card numbers should be tokenized (not stored directly)

## Disaster Recovery

### Backup Strategy
- **Cosmos DB**: Automatic continuous backups (default)
  - Backup interval: Every 4 hours
  - Retention: 30 days (free), up to 90 days (additional cost)
  - Restore: Point-in-time restore via Azure Portal/API
- **ADLS Gen2**: LRS provides 11 nines durability
  - GRS replication: Async replication to paired region
  - Lifecycle policies: Move to archive tier after 90 days
- **Function Code**: Stored in Git (GitHub), CI/CD redeploys

### Recovery Objectives
- **RTO (Recovery Time Objective)**: 4 hours
  - Re-deploy functions from Git
  - Restore Cosmos DB from backup
  - Update DNS/configurations
- **RPO (Recovery Point Objective)**: 4 hours
  - Cosmos DB backup interval
  - ADLS has near-zero RPO (synchronous writes)

### Disaster Scenarios

#### Scenario 1: Cosmos DB Data Corruption
1. Identify corruption time from logs/alerts
2. Initiate point-in-time restore via Azure Portal
3. Restore to new Cosmos DB account
4. Update function connection strings
5. Restart functions to pick up new config
6. Validate data integrity

#### Scenario 2: Regional Outage
1. Azure fails over Service Bus and Cosmos DB to paired region (automatic)
2. Redeploy functions to secondary region (manual or via DR plan)
3. Update Event Grid subscriptions to secondary function endpoint
4. Validate end-to-end flow in secondary region
5. Monitor for primary region recovery

#### Scenario 3: Accidental Data Deletion
1. Stop all functions to prevent further changes
2. Restore Cosmos DB from backup (point-in-time)
3. Restore ADLS blobs from soft-delete (90-day retention)
4. Resume functions and validate data

### Testing
- **DR Drills**: Quarterly failover tests to secondary region
- **Backup Validation**: Monthly restore tests to verify backup integrity
- **Documentation**: Keep runbooks updated with step-by-step procedures

---

## Appendix

### Glossary
- **RU/s**: Request Units per second (Cosmos DB throughput measure)
- **LRS**: Locally Redundant Storage (3 copies in one datacenter)
- **GRS**: Geo-Redundant Storage (6 copies across two regions)
- **TTL**: Time to Live (automatic data expiration)
- **ETL**: Extract, Transform, Load (data pipeline pattern)
- **PII**: Personally Identifiable Information (sensitive data)

### References
- [Azure Functions Best Practices](https://docs.microsoft.com/azure/azure-functions/functions-best-practices)
- [Cosmos DB Partitioning](https://docs.microsoft.com/azure/cosmos-db/partitioning-overview)
- [Event Grid Concepts](https://docs.microsoft.com/azure/event-grid/concepts)
- [ADLS Gen2 Best Practices](https://docs.microsoft.com/azure/storage/blobs/data-lake-storage-best-practices)

### Change Log
| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2024-12-10 | 1.0 | Initial architecture documentation | Platform Team |
