# Automotive CRM Data Pipeline

This project is a practical implementation to integrate CRM, transaction, and interaction data. The main goal was the transformation of raw logs into a clean "Customer 360" view and a feature table ready for churn analysis.

## 1. Schema Design
A **Star Schema** was used for the final data layer:
* **`customer_360` (Dimension):** The main source for customer profiles.
* **`clean_interactions` & `clean_transactions` (Facts):** Event-based tables for behavior analysis.
* **`churn_features`:** A flattened table built specifically to feed the machine learning model.

**Reasoning:** This setup keeps customer details separate from event streams. The structure makes the database easier to scale and allows BI tools to run queries faster without complex joins.

## 2. Data Cleaning & Decisions
* **Deduplication:** For customers with the same email, the record with the earliest `created_at` was kept. This ensures the preservation of the actual date the customer first joined.
* **Phone Format:** Regex was used to keep only numbers in a `DDD + 9 digits` format. Invalid numbers were set to `NULL` to avoid errors in marketing tools or SMS gateways.
* **$0$ Amount Purchases:** These were flagged with `amount_flag`. The records are kept in the facts but excluded from revenue calculations to prevent spend metrics from being skewed.
* **Referential Integrity:** Interactions and transactions from IDs that do not exist in the master table were removed. This prevents "ghost" data from affecting churn model accuracy and ensures financial reconciliation.

## 3. Assumptions
* **Reference Date:** All time-based metrics (recency, 180-day windows) are calculated using `2024-06-01` as the reference point for this dataset.
* **Primary System:** The **'CRM'** system timestamps were designated as more reliable than dealership logs, as central systems usually have better sync consistency.
* **Timezones:** All timestamps were assumed to be in the same timezone for window calculations.

## 4. Execution Flow
To run the full process, the following sequence is required:
1. **Pipeline Execution:** `python pipeline.py` (Generates the `/output` files and Task 1 report).
2. **Data Validation:** `python validator.py` (Triggers the automated audit).

## 5. Data Validation & Quality Assurance
An automated audit tool (`validator.py`) was developed to ensure the reliability of the output files. The script performs the following checks:
* **ETL Integrity:** Verifies deduplication and ensures zero orphaned records in fact tables.
* **Business Logic Cross-Check:** Simulates the logic of the 4 SQL queries (Task 3) within the Python environment to guarantee consistency between layers.
* **Financial Reconciliation:** Performs a full sum check of the `total_revenue` in the feature table against the raw transaction facts to ensure no data loss occurred during transformation.

## 6. Extra Features (Task 4)
* **`avg_days_between_services`**: This feature was added to monitor maintenance consistency. In the automotive industry, a steady service interval is a key indicator of brand loyalty.

## 7. Future Improvements
* **Storage in Parquet:** Replacing CSVs with Parquet would reduce file size and make reading data much faster for larger volumes.
* **Automated Profiling:** Generation of an automatic data quality report (such as an HTML summary) for the business team.
* **Docker:** The use of a container would ensure the pipeline runs with the same environment versions on any server or machine.

## 8. One Thing That Surprised Me
The identification of **10 orphaned interactions** and **30 duplicate emails** in the raw files was an unexpected finding. It indicates that some events are recorded before the customer registration is fully processed. Specific filters were built to handle this, preventing the generation of biased churn metrics.

## 9. Architecture Memo

**To:** CRM Product Manager  
**From:** Senior Data Engineer  
**Subject:** Real-Time Engagement and Data Integrity Strategy

### Request (A): 2-Hour Latency for Emails
A daily batch process is insufficient for a 2-hour window. A move to an **Event-Driven Architecture** is recommended.
* **Solution:** Use CRM Webhooks or a messaging queue (such as Kafka or SQS) to stream "test drive" events. A lightweight service will trigger the email API immediately after the event is received.
* **Trade-off:** This adds more infrastructure complexity than a simple script, but it is the only way to hit the required timing for hot leads.
* **What NOT to do:** The current batch script should **NOT** be modified to run every few minutes. This would create unnecessary database load and would not scale efficiently.

### Request (B): Fixing the 15% Missing Customers
The loss of 15% of interactions due to missing IDs creates a significant blind spot for the model.
* **Solution:** The implementation of **"Shadow Profiles"** is proposed. When an interaction arrives for an unknown ID, a temporary placeholder is created. These profiles are then merged with official records once the CRM synchronization is complete.
* **Trade-off:** Full visibility into customer behavior is achieved, although some demographic fields will remain empty for a short period.
* **What NOT to do:** These orphaned records should **NOT** be ignored or excluded from the pipeline. Discarding 15% of the data creates a **survivorship bias**, making the model blind to prospects who might drop off early in the journey.