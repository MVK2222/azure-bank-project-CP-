# ETL Process

This directory contains the Azure Databricks notebooks that implement the ETL (Extract, Transform, Load) process for the Azure Bank Platform. The process is divided into three main stages, corresponding to the Bronze, Silver, and Gold layers of the medallion architecture.

## Notebooks

### 1. `bronze.ipynb`

*   **Purpose:** This notebook is responsible for ingesting data from the raw sources into the Bronze layer of the data lakehouse.
*   **Sources:**
    *   **Azure Cosmos DB:** Reads real-time transactional data (ATM transactions, UPI events) from Cosmos DB containers.
    *   **Azure Data Lake Storage (ADLS):** Reads batch data (customer, account information) and KYC documents from the raw container in ADLS.
*   **Transformations:**
    *   Minimal transformations are applied at this stage.
    *   The main goal is to get the data into a Delta format for reliability and performance.
    *   Metadata columns are added to track the ingestion time and source of the data.
*   **Output:** Delta tables in the Bronze layer, partitioned by date or other relevant keys.

### 2. `silver.ipynb`

*   **Purpose:** This notebook takes the raw data from the Bronze layer and transforms it into a cleansed, conformed, and enriched Silver layer.
*   **Transformations:**
    *   **Data Cleaning:** Handles missing values, removes duplicates, and corrects data types.
    *   **Data Validation:** Enforces data quality rules and schemas.
    *   **Data Enrichment:** Joins different datasets to create a more complete view of the data (e.g., joining customer data with account data).
*   **Output:** Delta tables in the Silver layer, representing a single source of truth for the bank's core data entities.

### 3. `gold.ipynb`

*   **Purpose:** This notebook creates aggregated and business-focused data models in the Gold layer, ready for consumption by downstream applications.
*   **Transformations:**
    *   **Aggregation:** Creates pre-computed aggregates and summaries to improve query performance (e.g., daily transaction summaries, customer lifetime value).
    *   **Business Logic:** Applies business-specific rules and calculations.
    *   **Data Modeling:** Creates data marts and star schemas for specific analytical use cases (e.g., fraud detection, customer segmentation).
*   **Output:** Delta tables in the Gold layer, optimized for reporting, analytics, and machine learning.

