# Development Guide - Banking Data Platform

## Table of Contents
- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Local Development Environment](#local-development-environment)
- [Running the Application](#running-the-application)
- [Testing](#testing)
- [Debugging](#debugging)
- [Code Quality](#code-quality)
- [Development Workflow](#development-workflow)
- [Common Tasks](#common-tasks)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software
- **Python 3.10+**: Primary development language
  ```bash
  python --version  # Should be 3.10 or higher
  ```
- **Azure Functions Core Tools v4**: Local function runtime
  ```bash
  func --version  # Should be 4.x
  ```
- **Azure CLI**: Infrastructure management
  ```bash
  az --version  # Should be 2.50 or higher
  ```
- **Git**: Version control
  ```bash
  git --version
  ```

### Optional but Recommended
- **VS Code**: IDE with Azure Functions extension
- **Azure Storage Explorer**: GUI for ADLS Gen2 and Service Bus
- **Postman**: API testing and debugging
- **Docker**: Containerized development (future)

### Installation Guides

#### Windows (PowerShell)
```powershell
# Install Python from python.org or Microsoft Store
# Verify installation
python --version

# Install Azure Functions Core Tools via npm
npm install -g azure-functions-core-tools@4 --unsafe-perm true

# Install Azure CLI via MSI installer from docs.microsoft.com
az --version

# Install Git from git-scm.com
git --version
```

#### macOS (Homebrew)
```bash
# Install Python
brew install python@3.10

# Install Azure Functions Core Tools
brew tap azure/functions
brew install azure-functions-core-tools@4

# Install Azure CLI
brew install azure-cli

# Install Git
brew install git
```

#### Linux (Ubuntu/Debian)
```bash
# Install Python
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip

# Install Azure Functions Core Tools
wget -q https://packages.microsoft.com/config/ubuntu/20.04/packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
sudo apt-get update
sudo apt-get install azure-functions-core-tools-4

# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install Git
sudo apt install git
```

## Initial Setup

### 1. Clone Repository
```bash
# Clone the project (replace YOUR_ORG with your GitHub organization or username)
git clone https://github.com/YOUR_ORG/azure-bank-project-CP-.git
cd azure-bank-project-CP-

# Example with actual repository:
# git clone https://github.com/MVK2222/azure-bank-project-CP-.git

# Check out development branch
git checkout develop  # Or main, depending on your workflow
```

### 2. Create Python Virtual Environment
```bash
# Navigate to functions directory
cd functions

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# macOS/Linux:
source .venv/bin/activate

# Verify activation (should show .venv)
which python
```

### 3. Install Python Dependencies
```bash
# Install all required packages
pip install --upgrade pip
pip install -r requirements.txt

# Verify installation
pip list
```

**dependencies (requirements.txt)**:
```
azure-functions
azure-servicebus
azure-cosmos
azure-storage-blob
python-dateutil
```

### 4. Azure Login and Configuration
```bash
# Login to Azure
az login

# Set default subscription (if multiple subscriptions)
az account set --subscription "YOUR_SUBSCRIPTION_NAME_OR_ID"

# Verify current subscription
az account show
```

### 5. Create Local Settings File
Create `functions/local.settings.json` (NEVER commit this file - contains secrets):

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    
    "COSMOS_DB_CONNECTION_STRING": "AccountEndpoint=https://YOUR_COSMOS_ACCOUNT.documents.azure.com:443/;AccountKey=YOUR_KEY;",
    "COSMOS_DB_NAME": "operation-storage-db",
    
    "SERVICE_BUS_CONNECTION_STRING": "Endpoint=sb://YOUR_NAMESPACE.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=YOUR_KEY;",
    "SERVICE_BUS_QUEUE_NAME": "banking-ingest-queue",
    
    "STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=https;AccountName=YOUR_STORAGE_ACCOUNT;AccountKey=YOUR_KEY;EndpointSuffix=core.windows.net",
    
    "ATM_CONTAINER": "ATMTransactions",
    "UPI_CONTAINER": "UPIEvents",
    "PROFILE_CONTAINER": "AccountProfile",
    "ALERTS_CONTAINER": "FraudAlerts",
    "QUARANTINE_CONTAINER": "quarantine",
    "METADATA_CONTAINER": "metadata",
    
    "UPSERT_WORKERS": "8",
    "UPSERT_RETRIES": "3",
    "UPSERT_RETRY_BACKOFF": "0.5"
  },
  "ConnectionStrings": {}
}
```

**Getting Connection Strings**:
```bash
# Cosmos DB
az cosmosdb keys list --name YOUR_COSMOS_ACCOUNT --resource-group YOUR_RG --type connection-strings --query "connectionStrings[0].connectionString" -o tsv

# Service Bus
az servicebus namespace authorization-rule keys list --resource-group YOUR_RG --namespace-name YOUR_NAMESPACE --name RootManageSharedAccessKey --query primaryConnectionString -o tsv

# Storage Account
az storage account show-connection-string --name YOUR_STORAGE_ACCOUNT --resource-group YOUR_RG --query connectionString -o tsv
```

### 6. Create Test Data
Create sample CSV files in a local `test_data/` directory:

**test_data/atm_sample.csv**:
```csv
TransactionID,AccountNumber,CardNumber,TransactionTime,Amount,Location,Status,ATM_ID
TXN001,ACC001,CARD001,2024-01-01T10:00:00Z,5000,Mumbai,SUCCESS,ATM001
TXN002,ACC002,CARD002,2024-01-01T10:05:00Z,3000,Delhi,SUCCESS,ATM002
TXN003,ACC001,CARD001,2024-01-01T10:10:00Z,75000,Mumbai,SUCCESS,ATM001
```

**test_data/upi_sample.csv**:
```csv
TransactionID,AccountNumber,UPI_ID,Timestamp,Amount,Location,Status,DeviceID
UPI001,ACC001,user1@upi,2024-01-01T10:00:00Z,1000,Mumbai,SUCCESS,DEV001
UPI002,ACC002,user2@upi,2024-01-01T10:05:00Z,2000,Delhi,SUCCESS,DEV002
```

## Local Development Environment

### VS Code Setup

#### Recommended Extensions
- **Azure Functions** (ms-azuretools.vscode-azurefunctions)
- **Python** (ms-python.python)
- **Pylance** (ms-python.vscode-pylance)
- **Azure Account** (ms-vscode.azure-account)
- **GitLens** (eamodio.gitlens)

#### Workspace Settings (.vscode/settings.json)
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/functions/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true
  },
  "azureFunctions.deploySubpath": "functions",
  "azureFunctions.projectLanguage": "Python",
  "azureFunctions.projectRuntime": "~4",
  "azureFunctions.pythonVenv": ".venv"
}
```

#### Launch Configuration (.vscode/launch.json)
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Attach to Python Functions",
      "type": "python",
      "request": "attach",
      "port": 9091,
      "preLaunchTask": "func: host start"
    }
  ]
}
```

### Directory Structure
```
azure-bank-project-CP-/
├── .gitignore                    # Git ignore rules
├── README.md                     # Project overview
├── docs/                         # Documentation
│   ├── ARCHITECTURE.md
│   ├── DEVELOPMENT.md
│   ├── TESTING.md
│   ├── DEPLOYMENT.md
│   ├── SECURITY.md
│   └── TROUBLESHOOTING.md
├── functions/                    # Azure Functions project
│   ├── .venv/                    # Python virtual environment (not committed)
│   ├── host.json                 # Function app configuration
│   ├── local.settings.json       # Local configuration (not committed)
│   ├── requirements.txt          # Python dependencies
│   ├── FileArrivalFunction/
│   │   ├── __init__.py           # Function code
│   │   └── function.json         # Function binding configuration
│   └── BatchIngestionFunction/
│       ├── __init__.py           # Main orchestrator
│       ├── function.json         # Function binding
│       ├── alerts/               # Fraud detection
│       │   ├── transaction_alerts.py
│       │   └── profile_alerts.py
│       ├── client/               # Azure service clients
│       │   ├── blob_client.py
│       │   └── cosmos_client.py
│       ├── processor/            # Data processors
│       │   ├── atm_processor.py
│       │   ├── upi_processor.py
│       │   ├── account_processor.py
│       │   └── customer_processor.py
│       ├── validator/            # Validation logic
│       │   ├── transaction_validator.py
│       │   ├── account_validator.py
│       │   └── customer_validator.py
│       └── utils/                # Utility functions
│           ├── csv_utils.py
│           ├── date_utils.py
│           └── sanitizer.py
├── tests/                        # Unit and integration tests
│   ├── test_validators.py
│   ├── test_processors.py
│   └── test_alerts.py
└── test_data/                    # Sample data for testing
    ├── atm_sample.csv
    ├── upi_sample.csv
    ├── account_sample.csv
    └── customer_sample.csv
```

## Running the Application

### Start Local Functions Runtime
```bash
# Navigate to functions directory
cd functions

# Ensure virtual environment is activated
source .venv/bin/activate  # macOS/Linux
.\.venv\Scripts\Activate.ps1  # Windows

# Start functions runtime
func start

# Expected output:
# Azure Functions Core Tools
# Core Tools Version:       4.x.x
# Function Runtime Version: 4.x.x
#
# Functions:
#   FileArrivalFunction: eventGridTrigger
#   BatchIngestionFunction: serviceBusTrigger
#
# For detailed output, run func with --verbose flag.
```

### Trigger Functions Locally

#### Option 1: Using Azure Storage Explorer
1. Open Azure Storage Explorer
2. Connect to ADLS Gen2 account
3. Upload CSV to `raw/atm/` container
4. Event Grid triggers FileArrivalFunction (requires ngrok or Azure tunnel)

#### Option 2: Directly Trigger Service Bus Function
```bash
# Send message to Service Bus queue
az servicebus queue send \
  --namespace-name YOUR_NAMESPACE \
  --queue-name banking-ingest-queue \
  --body '{"file_url":"https://YOUR_STORAGE.blob.core.windows.net/raw/atm/atm_sample.csv","file_name":"atm_sample.csv","source_type":"ATM"}'

# BatchIngestionFunction will automatically pick up the message
```

#### Option 3: Using Postman (HTTP Trigger Alternative)
For development, you can temporarily add HTTP trigger to functions:

**function.json** (temporary):
```json
{
  "bindings": [
    {
      "authLevel": "anonymous",
      "type": "httpTrigger",
      "direction": "in",
      "name": "req",
      "methods": ["post"]
    },
    {
      "type": "http",
      "direction": "out",
      "name": "$return"
    }
  ]
}
```

Then POST JSON to `http://localhost:7071/api/BatchIngestionFunction`

### View Logs in Real-Time
```bash
# Function logs appear in terminal where 'func start' is running
# Look for:
# [INFO] Processing atm_sample.csv, source_type=ATM
# [INFO] Completed processing atm_sample.csv → {"status": "COMPLETED", ...}
```

### Verify Results

#### Cosmos DB (Azure Portal)
1. Open Cosmos DB account in Azure Portal
2. Navigate to Data Explorer
3. Query containers:
```sql
-- Check ATM transactions
SELECT * FROM c WHERE c.AccountNumber = "ACC001"

-- Check fraud alerts
SELECT * FROM c WHERE c.type = "HIGH_VALUE"
```

#### ADLS Gen2 (Azure Storage Explorer)
1. Open Storage Explorer
2. Check containers:
   - `metadata/`: Processing metadata JSON files
   - `quarantine/`: Invalid rows CSV files

## Testing

### Unit Tests
```bash
# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Run all tests
pytest tests/

# Run with coverage
pytest --cov=functions tests/

# Run specific test file
pytest tests/test_validators.py

# Run specific test
pytest tests/test_validators.py::test_transaction_validator_valid

# Verbose output
pytest -v tests/
```

### Integration Tests
```bash
# Test end-to-end flow with real Azure resources
# Requires local.settings.json with valid connection strings

# Run integration tests (tag with @integration)
pytest -m integration tests/

# Or create separate test directory
pytest integration_tests/
```

### Sample Test (tests/test_validators.py)
```python
import pytest
from BatchIngestionFunction.validator.transaction_validator import validate_transaction_row

def test_transaction_validator_valid():
    """Test valid transaction row"""
    row = {
        "TransactionID": "TXN001",
        "Amount": "5000",
        "Timestamp": "2024-01-01T10:00:00Z"
    }
    errors, cleaned = validate_transaction_row(row, "ATM")
    assert len(errors) == 0
    assert cleaned["Amount"] == 5000.0

def test_transaction_validator_missing_id():
    """Test missing transaction ID"""
    row = {
        "Amount": "5000",
        "Timestamp": "2024-01-01T10:00:00Z"
    }
    errors, cleaned = validate_transaction_row(row, "ATM")
    assert "Missing TransactionID" in errors

def test_transaction_validator_invalid_amount():
    """Test invalid amount"""
    row = {
        "TransactionID": "TXN001",
        "Amount": "invalid",
        "Timestamp": "2024-01-01T10:00:00Z"
    }
    errors, cleaned = validate_transaction_row(row, "ATM")
    assert "Invalid or non-positive Amount" in errors
```

### Manual Testing Workflow
1. **Upload test CSV**: Use Azure Storage Explorer to upload `atm_sample.csv` to `raw/atm/`
2. **Monitor logs**: Watch function terminal for processing logs
3. **Verify Cosmos DB**: Query for inserted records
4. **Check metadata**: Verify metadata JSON in `metadata/` container
5. **Validate alerts**: Check `FraudAlerts` container for generated alerts
6. **Review quarantine**: If errors expected, check `quarantine/` container

## Debugging

### VS Code Debugging
1. Set breakpoints in Python code (click left of line numbers)
2. Press F5 or Run > Start Debugging
3. Function app starts with debugger attached
4. Trigger function (upload file, send message)
5. Debugger pauses at breakpoints
6. Inspect variables, step through code

### Debug Specific Function
```bash
# Start with debugger on specific port
func start --python --port 7072

# Attach VS Code debugger to port 7072
# (Use launch.json configuration)
```

### Print Debugging (Quick)
```python
# Add logging statements
import logging

logging.info(f"Processing row: {row}")
logging.warning(f"Invalid row detected: {errors}")
logging.error(f"Failed to upsert: {e}", exc_info=True)

# Or use print (appears in terminal)
print(f"DEBUG: row={row}")
```

### Common Debugging Scenarios

#### Problem: Function not triggering
**Check**:
- Is `func start` running?
- Is Event Grid subscription configured correctly?
- Is Service Bus connection string valid?
- Check function.json binding configuration

#### Problem: Cosmos DB connection errors
**Check**:
- Is connection string correct in local.settings.json?
- Is Cosmos DB firewall allowing your IP?
- Test connection manually:
```python
from azure.cosmos import CosmosClient
client = CosmosClient.from_connection_string("YOUR_CONNECTION_STRING")
```

#### Problem: ADLS download failures
**Check**:
- Is storage connection string correct?
- Is file URL valid and accessible?
- Test blob download manually:
```python
from azure.storage.blob import BlobServiceClient
client = BlobServiceClient.from_connection_string("YOUR_CONNECTION_STRING")
# Try downloading blob
```

## Code Quality

### Linting with Flake8
```bash
# Install flake8
pip install flake8

# Run linter
flake8 functions/

# With specific rules
flake8 --max-line-length=120 --ignore=E501,W503 functions/

# Output violations to file
flake8 functions/ > lint_report.txt
```

### Formatting with Black
```bash
# Install black
pip install black

# Format all Python files
black functions/

# Check what would change (dry run)
black --check functions/

# Format specific file
black functions/BatchIngestionFunction/__init__.py
```

### Type Checking with mypy
```bash
# Install mypy
pip install mypy

# Run type checker
mypy functions/

# With strict mode
mypy --strict functions/
```

### Pre-commit Hooks (Recommended)
```bash
# Install pre-commit
pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml << EOF
repos:
  - repo: https://github.com/psf/black
    rev: 23.9.1
    hooks:
      - id: black
  - repo: https://github.com/PyCQA/flake8
    rev: 6.1.0
    hooks:
      - id: flake8
        args: [--max-line-length=120]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.5.1
    hooks:
      - id: mypy
        additional_dependencies: [types-python-dateutil]
EOF

# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Development Workflow

### Feature Development
```bash
# 1. Create feature branch
git checkout -b feature/add-new-fraud-rule

# 2. Make changes
# Edit code, add tests

# 3. Test locally
pytest tests/
func start  # Manual test

# 4. Commit changes
git add .
git commit -m "Add new fraud detection rule for XYZ pattern"

# 5. Push and create PR
git push origin feature/add-new-fraud-rule
# Create PR on GitHub
```

### Code Review Checklist
- [ ] All tests pass
- [ ] Code follows style guidelines (flake8, black)
- [ ] Comprehensive docstrings added
- [ ] Error handling implemented
- [ ] Logging added for debugging
- [ ] Performance considered (no obvious bottlenecks)
- [ ] Security reviewed (no secrets, input validation)
- [ ] Documentation updated (if needed)

### Merge to Main
```bash
# After PR approved and merged
git checkout main
git pull origin main

# Delete feature branch
git branch -d feature/add-new-fraud-rule
```

## Common Tasks

### Add New Fraud Detection Rule
1. Open `BatchIngestionFunction/alerts/transaction_alerts.py`
2. Add rule logic in `fraud_detection()` function
3. Update rule documentation and examples
4. Add unit tests in `tests/test_alerts.py`
5. Test with sample data
6. Update ARCHITECTURE.md with new rule details

### Add New Data Source Type
1. Create processor: `BatchIngestionFunction/processor/newsource_processor.py`
2. Create validator: `BatchIngestionFunction/validator/newsource_validator.py`
3. Update `csv_utils.detect_source_type()` to recognize new filename pattern
4. Update `BatchIngestionFunction/__init__.py` to route new type
5. Create Cosmos DB container (if needed)
6. Add tests
7. Update documentation

### Update Cosmos DB Schema
1. Add new fields to processor normalization logic
2. Update validator rules (if needed)
3. Test with old and new data (backward compatibility)
4. Update documentation
5. Consider migration script for existing data (if breaking change)

### Tune Fraud Detection Thresholds
1. Edit constants in `transaction_alerts.py`:
   ```python
   HIGH_VALUE_THRESHOLD = 75000.0  # Increase from 50000
   VELOCITY_TXN_COUNT = 15  # Increase from 10
   ```
2. Test with historical data to validate false positive rate
3. Document reasoning for changes
4. Deploy to dev environment first
5. Monitor alert volumes after deployment

## Troubleshooting

### Problem: Virtual environment not activating
**Solution**:
```bash
# Windows: Enable script execution
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Recreate virtual environment
rm -rf .venv
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Problem: Import errors (module not found)
**Solution**:
```bash
# Ensure in functions directory
cd functions

# Reinstall dependencies
pip install --upgrade -r requirements.txt

# Verify imports work
python -c "import azure.functions; print('OK')"
```

### Problem: Functions not starting
**Solution**:
```bash
# Check Python version
python --version  # Must be 3.10+

# Check Azure Functions Core Tools
func --version  # Must be 4.x

# Verbose logging
func start --verbose

# Clear cache
rm -rf __pycache__ */__pycache__
```

### Problem: Connection timeouts
**Solution**:
- Check firewall rules in Azure Portal
- Verify connection strings are correct
- Test connectivity:
```bash
# Test Cosmos DB
az cosmosdb check-name-exists --name YOUR_COSMOS_ACCOUNT

# Test Storage
az storage account show --name YOUR_STORAGE_ACCOUNT
```

### Problem: Out of memory errors
**Solution**:
- Process smaller batches (split large CSV files)
- Increase function timeout and memory allocation
- Profile memory usage:
```python
import tracemalloc
tracemalloc.start()
# Your code here
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
```

---

## Additional Resources

### Documentation Links
- [Azure Functions Python Developer Guide](https://docs.microsoft.com/azure/azure-functions/functions-reference-python)
- [Cosmos DB Python SDK](https://docs.microsoft.com/python/api/overview/azure/cosmos-readme)
- [Azure Storage Python SDK](https://docs.microsoft.com/python/api/overview/azure/storage-readme)

### Training Resources
- Microsoft Learn: Azure Functions
- Python Best Practices Guide
- Banking Industry Security Standards

### Getting Help
- **Internal**: Post in team Slack channel #data-platform
- **Azure**: Submit support ticket via Azure Portal
- **Python**: StackOverflow with `azure-functions` tag

---

**Next Steps**: See [TESTING.md](TESTING.md) for comprehensive testing guide.
