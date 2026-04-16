import pandas as pd
import numpy as np
import logging
import re
from pathlib import Path
from datetime import datetime

# --- LOGGING CONFIGURATION ---
# basicConfig sets the global threshold for importance and defines the output structure.
# We use INFO level to track pipeline progress without cluttering logs with DEBUG details.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initializing a logger named after the module for better traceability in production logs.
logger = logging.getLogger(__name__)

# --- CONSTANTS ---
DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
REF_DATE = pd.to_datetime("2024-06-01")

class DataPipeline:
    """
    Main ETL Orchestrator. 
    Designed with a modular approach to separate data ingestion, 
    quality reporting, transformation, and feature engineering.
    """
    
    def __init__(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.dfs = {}

    def load_raw_data(self):
        """Loads data with optimized date parsing."""
        files = {
            "customers": ("raw_customers.csv", ["created_at", "birth_date"]),
            "interactions": ("raw_interactions.csv", ["interaction_date"]),
            "transactions": ("raw_transactions.csv", ["transaction_date"]),
            "campaigns": ("raw_campaigns.csv", ["start_date", "end_date"])
        }
        for key, (file, dates) in files.items():
            path = DATA_DIR / file
            if path.exists():
                self.dfs[key] = pd.read_csv(path, parse_dates=dates)
                logger.info(f"Table {key} loaded: {len(self.dfs[key])} rows.")
            else:
                logger.error(f"File not found: {path}")

    def run_quality_report(self):
        """
        Task 1: Data Quality Report.
        Logging row counts and null values to ensure pipeline observability.
        We specifically monitor orphaned records to detect sync issues between 
        source systems and the CRM master.
        """
        logger.info("Starting Data Quality Report...")
        for name, df in self.dfs.items():
            null_count = df.isnull().sum().sum()
            logger.info(f"Check {name}: {len(df)} rows, {null_count} null values found.")
        
        # Referential Integrity Check
        orphans = self.dfs['interactions'][~self.dfs['interactions']['customer_id'].isin(self.dfs['customers']['customer_id'])]
        if not orphans.empty:
            logger.warning(f"Anomaly Detected: {len(orphans)} orphaned interactions (no matching customer).")

    def transform_data(self):
        """
        Task 2: Cleaning and Standardization.
        - Deduplication strategy: Prioritizing the earliest 'created_at' to maintain original acquisition data.
        - Phone cleaning: Using Regex to enforce data types, crucial for downstream CRM automation.
        - Integrity: Filtering orphaned interactions to avoid skewed churn analysis.
        """
        # 1. Customer 360 Construction
        cust = self.dfs['customers'].copy()
        cust['email'] = cust['email'].str.lower().str.strip()
        
        # Phone Standardization (Senior Approach: Regex + Validation)
        def clean_phone(val):
            digits = re.sub(r'\D', '', str(val))
            # Returning as string to prevent scientific notation (e.g., 1.19e10)
            return digits if len(digits) == 11 else np.nan
        
        cust['phone'] = cust['phone'].apply(clean_phone)
        cust['is_duplicate_email'] = cust.duplicated(subset=['email'], keep=False)
        c360 = cust.sort_values('created_at').drop_duplicates('email', keep='first')

        # 2. Interactions Cleaning (Filtering by Trusted IDs)
        inter = self.dfs['interactions'].copy()
        inter = inter[inter['customer_id'].isin(c360['customer_id'])]
        inter.loc[inter['duration_seconds'] < 0, 'duration_seconds'] = np.nan

        # 3. Transactions Cleaning
        trans = self.dfs['transactions'].copy()
        trans = trans[trans['customer_id'].isin(c360['customer_id'])]
        
        trans['amount_flag'] = (trans['transaction_type'] == 'purchase') & (trans['amount'] == 0)

        return c360, inter, trans

    def generate_features(self, c360, inter, trans):
        """
        Task 4: Analytical Feature Store.
        Consolidating behavioral and transactional data into a single customer-level grain.
        Calculations include Recency/Frequency/Monetary (RFM) logic and service loyalty intervals.
        """
        logger.info("Generating analytical features...")
        
        # 1. Interaction Metrics
        last_inter = inter.groupby('customer_id')['interaction_date'].max()
        count_90d = inter[inter['interaction_date'] >= (REF_DATE - pd.Timedelta(days=90))].groupby('customer_id').size()
        
        # 2. Campaign Response Rate (% of 'interested' outcomes)
        camp_inter = inter[inter['campaign_id'].notnull()]
        total_camp = camp_inter.groupby('customer_id').size()
        pos_camp = camp_inter[camp_inter['outcome'] == 'interested'].groupby('customer_id').size()
        camp_rate = (pos_camp / total_camp)
        
        # 3. Transaction Metrics (Purchases only)
        purchases = trans[trans['transaction_type'] == 'purchase']
        purchase_count = purchases.groupby('customer_id').size()
        last_purchase = purchases.groupby('customer_id')['transaction_date'].max()
        # Revenue: Sum amount where not flagged as zero-purchase
        revenue = purchases[purchases['amount'] > 0].groupby('customer_id')['amount'].sum()
        
        # 4. Test Drive Flag (1 if exists, else 0)
        has_td = trans[trans['transaction_type'] == 'test_drive']['customer_id'].unique()

        # 5. Average Days Between Services
        services = trans[trans['transaction_type'] == 'service'].sort_values(['customer_id', 'transaction_date'])
        services['prev_date'] = services.groupby('customer_id')['transaction_date'].shift(1)
        services['days_diff'] = (services['transaction_date'] - services['prev_date']).dt.days
        # Only calculated if more than 1 service visit exists
        avg_service_interval = services.groupby('customer_id')['days_diff'].mean()

        # --- Final Consolidation ---
        features = c360[['customer_id']].copy()
        features['recency_days'] = (REF_DATE - features['customer_id'].map(last_inter)).dt.days
        features['interaction_count_90d'] = features['customer_id'].map(count_90d).fillna(0)
        features['purchase_count'] = features['customer_id'].map(purchase_count).fillna(0)
        features['days_since_last_purchase'] = (REF_DATE - features['customer_id'].map(last_purchase)).dt.days
        features['total_revenue'] = features['customer_id'].map(revenue).fillna(0)
        features['campaign_response_rate'] = features['customer_id'].map(camp_rate)
        features['has_test_drive'] = features['customer_id'].isin(has_td).astype(int)
        features['avg_days_between_services'] = features['customer_id'].map(avg_service_interval)
        
        return features

    def run(self):
        """
        Pipeline Execution Flow:
        1. Ingest -> 2. Audit -> 3. Clean -> 4. Persist Facts -> 5. Engineer Features.
        """
        
        self.load_raw_data()
        self.run_quality_report()
        c360, inter, trans = self.transform_data()
        
        # Persist refined layer to /output
        c360.to_csv(OUTPUT_DIR / "customer_360.csv", index=False)
        inter.to_csv(OUTPUT_DIR / "clean_interactions.csv", index=False)
        trans.to_csv(OUTPUT_DIR / "clean_transactions.csv", index=False)
        
        # Task 4 Output
        features = self.generate_features(c360, inter, trans)
        features.to_csv(OUTPUT_DIR / "churn_features.csv", index=False)
        logger.info("Pipeline completed successfully with all features generated.")

if __name__ == "__main__":
    DataPipeline().run()