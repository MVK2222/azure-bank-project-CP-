# Azure Functions

This directory contains the Azure Functions used for orchestration and serverless processing in the Azure Bank Platform.

## Directory Structure

```
functions/
├── BatchIngestionFunction/
│   ├── __init__.py             # Main function entry point
│   ├── function.json           # Function binding configuration
│   ├── alerts/                 # Modules for sending alerts
│   │   ├── profile_alerts.py
│   │   └── transaction_alerts.py
│   ├── client/                 # Clients for external services
│   │   ├── blob_client.py
│   │   └── cosmos_client.py
│   ├── processor/              # Core data processing logic
│   │   ├── account_processor.py
│   │   ├── atm_processor.py
│   │   ├── customer_processor.py
│   │   └── upi_processor.py
│   ├── utils/                  # Utility functions
│   │   ├── csv_utils.py
│   │   ├── date_utils.py
│   │   └── sanitizer.py
│   └── validator/              # Data validation modules
│       ├── account_validator.py
│       ├── customer_validator.py
│       └── transaction_validator.py
├── FileArrivalFunction/
│   ├── __init__.py
│   └── function.json
├── host.json                   # Global configuration for all functions
├── local.settings.json         # Local development settings
└── requirements.txt            # Python package dependencies
```

*   **`BatchIngestionFunction/`**: This function is modularly designed to handle the complexity of batch data ingestion.
    *   `__init__.py`: The main entry point that orchestrates the ingestion process by using the various modules.
    *   `function.json`: Defines the function's trigger, input, and output bindings.
    *   `alerts/`: Contains logic for generating and sending alerts based on data processing outcomes.
    *   `client/`: Manages connections and interactions with external services like Azure Blob Storage and Cosmos DB.
    *   `processor/`: Holds the core business logic for transforming and processing each type of data (e.g., customer, account, transactions).
    *   `utils/`: A collection of reusable helper functions for common tasks like CSV manipulation, date handling, and data sanitization.
    *   `validator/`: Contains modules responsible for validating incoming data against predefined rules to ensure data quality.
*   **`FileArrivalFunction/`**: A simpler function triggered by file uploads, primarily for handling KYC documents.
*   **`host.json`**: Contains global configuration options that affect all functions in the Function App.
*   **`local.settings.json`**: Stores app settings and connection strings for local development. This file should not be committed to source control.
*   **`requirements.txt`**: Lists the Python packages that the functions depend on.

## Functions

### 1. `BatchIngestionFunction`

*   **Purpose:** This function is responsible for orchestrating the batch ingestion of data into the raw layer of the data lake.
*   **Trigger:** This function can be triggered in several ways:
    *   **HTTP Trigger:** Manually trigger the ingestion process via an HTTP request.
    *   **Timer Trigger:** Schedule the function to run at regular intervals (e.g., daily) to pick up new batch files.
*   **Logic:**
    1.  Connects to the source system (e.g., an SFTP server or another storage account) where the batch files are located.
    2.  Copies the new files to the `raw` container in Azure Data Lake Storage (ADLS).
    3.  Optionally, it can trigger a Databricks notebook job to start the Bronze layer processing.

### 2. `FileArrivalFunction`

*   **Purpose:** This function is triggered when a new file arrives in a specific container in ADLS. It's primarily used for processing KYC documents.
*   **Trigger:**
    *   **Blob Trigger:** The function is automatically triggered when a new blob (file) is created in the `kyc-documents` container in ADLS.
*   **Logic:**
    1.  When a new KYC document is uploaded, the function is triggered.
    2.  It reads the metadata of the file (e.g., customer ID, document type from the filename).
    3.  It can perform initial validation on the document.
    4.  It updates a metadata store (e.g., a Cosmos DB collection or an Azure SQL database) with the information about the new document.
    5.  It can move the file to a `processed` directory after successful processing.

## Setup and Deployment

### 1. Local Development & `local.settings.json`

You can run and debug the functions locally using the Azure Functions Core Tools. The `local.settings.json` file is crucial for this, as it stores app settings, connection strings, and other secrets that your function code relies on.

*   **Structure**: The file typically contains an `IsEncrypted` flag (which should be `false` for local, unencrypted settings) and a `Values` object. The `Values` object is a key-value store for your application settings.
    ```json
    {
      "IsEncrypted": false,
      "Values": {
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
        "FUNCTIONS_WORKER_RUNTIME": "python",
        "MyCosmosDBConnection": "AccountEndpoint=...",
        "MyStorageAccountConnection": "DefaultEndpointsProtocol=..."
      }
    }
    ```
*   **Security**: This file should **never** be committed to source control (e.g., Git). Ensure it is listed in your `.gitignore` file to prevent accidentally exposing secrets.

### 2. Deployment with Azure CLI

While you can use GitHub Actions or VS Code, you can also deploy the Function App directly from your command line using the Azure CLI and Azure Functions Core Tools.

**Step 1: Log in to Azure**
```bash
az login
```

**Step 2: Publish the Function App**
This command packages your local function project and deploys it to your specified Function App in Azure. If the app doesn't exist, you'll need to create it first.
```bash
# Ensure you are in the root of the 'functions' directory
func azure functionapp publish <YOUR_FUNCTION_APP_NAME>
```
### 3. Managing Application Settings
![img.png](../images/sql_db.png)
After deployment, your app will need its settings configured in the Azure environment. You can upload the settings from your `local.settings.json` file using the Azure CLI.

**Step 1: Set an individual setting**
```bash
az functionapp config appsettings set --name <YOUR_FUNCTION_APP_NAME> --resource-group <YOUR_RESOURCE_GROUP> --settings "MySetting=MyValue"
```

**Step 2: Upload all local settings**
The Azure Functions Core Tools provide a convenient way to publish all settings from `local.settings.json` at once.
```bash
# This command encrypts and publishes the settings
func azure functionapp publish <YOUR_FUNCTION_APP_NAME> --publish-local-settings -i
```
The `-i` flag will prompt you for confirmation before overwriting existing settings. Use `--overwrite-settings` to force an overwrite without prompting.
