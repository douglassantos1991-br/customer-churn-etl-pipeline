\# Automotive CRM Data Pipeline



This project implements a robust ETL pipeline to integrate raw customer data from Salesforce CRM, dealerships, and marketing touchpoints. It prepares a "Customer 360" view and generates features for analytical churn models.



\## 1. Schema Design

I adopted a \*\*Star Schema\*\* approach for the refined layer:

\* \*\*Dimension Table:\*\* `customer\_360` serves as the canonical source of truth for customer attributes.

\* \*\*Fact Tables:\*\* `clean\_interactions` and `clean\_transactions` store event-based data.

\* \*\*Feature Table:\*\* `churn\_features` provides an aggregated, model-ready view.



\*\*Why:\*\* This structure separates static attributes from high-frequency events, allowing for efficient joins and clear data lineage.



\---



\## 2. Cleaning Decisions

\* \*\*Deduplication:\*\* When multiple records shared an email, I kept the one with the earliest `created\_at` timestamp to preserve the original acquisition date.

\* \*\*Phone Standardization:\*\* I used Regex to enforce a strictly numeric format (`DDD + 9 digits`). Invalid or non-conforming numbers were set to `null` to prevent downstream SMS/Call failures.

\* \*\*Transaction Flags:\*\* Added `amount\_flag = True` for purchases with a 0 value. These are kept in the ledger but excluded from total revenue calculations to avoid skewing average spend metrics.

\* \*\*Interaction Filtering:\*\* Removed "orphaned" interactions that did not have a corresponding ID in the `customer\_360` table to ensure the churn model only trains on verified users.



\---



\## 3. Assumptions

\* \*\*Time Zones:\*\* All timestamps are assumed to be in the same local time zone for the purpose of the 180-day and 365-day calculations.

\* \*\*Source Trust:\*\* I designated the \*\*'CRM'\*\* source system as the "source of truth" for interaction timestamps over 'Dealership' logs due to higher automated logging consistency.

\* \*\*Reference Date:\*\* `2024-06-01` was used as the fixed reference point for all "recency" and "response rate" calculations as per project requirements.



\---



\## 4. What I Would Do With More Time

\* \*\*Unit Testing:\*\* Implement `pytest` to verify the phone cleaning and deduplication logic automatically.

\* \*\*DVC Integration:\*\* Use Data Version Control (DVC) to track the raw CSV versions without committing large files to Git.

\* \*\*Logging:\*\* Replace `print` statements with a structured logging library to track pipeline health in a production environment.



\---



\## 5. One Thing That Surprised Me

I was surprised by the high volume of \*\*orphaned interactions\*\* (approximately 15% of the dataset) that had no matching record in the customer master file. This suggests that the front-end lead capture (e.g., call centers) is recording events before a formal customer profile is synchronized, which led me to propose the "Shadow Profile" architecture in the memo below.



\---



\## 6. Architecture Memo

\### To: CRM Product Manager

\*\*Request (A): 2-Hour Latency for Triggered Emails\*\*

I recommend moving from a batch process to an \*\*Event-Driven Architecture\*\*. By using Change Data Capture (CDC) or Webhooks from the CRM, we can stream "Test Drive" events into a message queue (e.g., Kafka). A lightweight consumer can then trigger the email service within minutes. 

\* \*\*Trade-off:\*\* This increases infra complexity but meets the business need for near-real-time engagement.

\* \*\*What NOT to do:\*\* I would NOT simply increase the frequency of the current Python batch script, as frequent polling places unnecessary load on the production database.



\*\*Request (B): Addressing the Missing 15% of Customers\*\*

I propose implementing \*\*"Shadow Profiles."\*\* If an interaction arrives for an unknown ID, the pipeline will create a placeholder record in the `customer\_360` table. These will be automatically merged when the master record arrives from Salesforce.

\* \*\*Trade-off:\*\* This ensures 100% of interaction data is available for model training, though some profiles will temporarily lack demographic details.

\* \*\*What NOT to do:\*\* I would NOT ignore these records or hard-delete them, as discarding 15% of interactions introduces significant "survivorship bias" into the churn model.

