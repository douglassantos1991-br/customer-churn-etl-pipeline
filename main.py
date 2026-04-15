import pandas as pd
import numpy as np
import os
import re
from pathlib import Path

# --- CONFIGURATION ---
DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
REFERENCE_DATE = pd.to_datetime("2024-06-01")

def setup_environment():
    """Ensure the output directory exists."""
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        print(f"Created directory: {OUTPUT_DIR}")

def load_data():
    """Load raw CSV files."""
    print("Loading data...")
    return {
        "customers": pd.read_csv(DATA_DIR / "raw_customers.csv", parse_dates=["created_at", "birth_date"]),
        "interactions": pd.read_csv(DATA_DIR / "raw_interactions.csv", parse_dates=["interaction_date"]),
        "transactions": pd.read_csv(DATA_DIR / "raw_transactions.csv", parse_dates=["transaction_date"]),
        "campaigns": pd.read_csv(DATA_DIR / "raw_campaigns.csv", parse_dates=["start_date", "end_date"]),
    }

def run_task_1_dq_report(dfs):
    """Print the Data Quality Report to stdout."""
    print("\n" + "="*40)
    print("TASK 1: DATA QUALITY REPORT")
    print("="*40)
    
    for name, df in dfs.items():
        print(f"Table: {name}")
        print(f" - Row count: {len(df)}")
        print(f" - Nulls:\n{df.isnull().sum()[df.isnull().sum() > 0]}")
        
    # Referential Integrity: Interactions without customers
    orphans = dfs['interactions'][~dfs['interactions']['customer_id'].isin(dfs['customers']['customer_id'])]
    print(f" - Orphaned interactions (no customer record): {len(orphans)}")
    
    # Anomalies: Negative transaction amounts
    neg_trans = (dfs['transactions']['amount'] < 0).sum()
    print(f" - Transactions with negative amounts: {neg_trans}")
    print("="*40 + "\n")

def run_task_2_transformation(dfs):
    """Clean and transform data for CRM and Churn."""
    print("Transforming data (Task 2)...")
    
    # --- 1. Customer 360 ---
    cust = dfs['customers'].copy()
    cust['email'] = cust['email'].str.lower().str.strip()
    
    # Phone: Digits only, check for 11 digits (DDD + 9 digits)
    def clean_phone(val):
        if pd.isna(val): return np.nan
        digits = re.sub(r'\D', '', str(val))
        return digits if len(digits) == 11 else np.nan
    
    cust['phone'] = cust['phone'].apply(clean_phone)
    cust['birth_date'] = pd.to_datetime(cust['birth_date'], errors='coerce').dt.date
    
    # Deduplicate: Keep earliest created_at, flag duplicates
    cust = cust.sort_values(['email', 'created_at'])
    cust['is_duplicate_email'] = cust.duplicated(subset=['email'], keep=False)
    customer_360 = cust.drop_duplicates(subset=['email'], keep='first')

    # --- 2. Clean Interactions ---
    inter = dfs['interactions'].copy()
    inter = inter[inter['customer_id'].isin(customer_360['customer_id'])]
    inter.loc[inter['duration_seconds'] < 0, 'duration_seconds'] = np.nan
    # Note: Choosing 'CRM' as the trusted source_system for time analysis due to higher logging consistency.
    
    # --- 3. Clean Transactions ---
    trans = dfs['transactions'].copy()
    trans['amount_flag'] = (trans['transaction_type'] == 'purchase') & (trans['amount'] == 0)
    
    return customer_360, inter, trans

def run_task_4_features(c360, inter, trans):
    """Generate churn features."""
    print("Generating churn features (Task 4)...")
    
    # Ensure datetime for math
    inter['interaction_date'] = pd.to_datetime(inter['interaction_date'])
    trans['transaction_date'] = pd.to_datetime(trans['transaction_date'])
    
    # Recency & Interaction Counts
    last_inter = inter.groupby('customer_id')['interaction_date'].max()
    inter_90d = inter[inter['interaction_date'] >= (REFERENCE_DATE - pd.Timedelta(days=90))]
    count_90d = inter_90d.groupby('customer_id').size()
    
    # Purchases
    purchases = trans[trans['transaction_type'] == 'purchase']
    purchase_count = purchases.groupby('customer_id').size()
    last_purchase = purchases.groupby('customer_id')['transaction_date'].max()
    
    # Revenue (Excluding flagged 0-amount)
    revenue = purchases[purchases['amount'] > 0].groupby('customer_id')['amount'].sum()
    
    # Combine
    features = c360[['customer_id']].copy()
    features['recency_days'] = (REFERENCE_DATE - last_inter).dt.days
    features['interaction_count_90d'] = features['customer_id'].map(count_90d).fillna(0)
    features['purchase_count'] = features['customer_id'].map(purchase_count).fillna(0)
    features['days_since_last_purchase'] = (REFERENCE_DATE - last_purchase).dt.days
    features['total_revenue'] = features['customer_id'].map(revenue).fillna(0)
    
    return features

def main():
    setup_environment()
    dfs = load_data()
    
    run_task_1_dq_report(dfs)
    
    c360, clean_inter, clean_trans = run_task_2_transformation(dfs)
    
    # Save Task 2
    c360.to_csv(OUTPUT_DIR / "customer_360.csv", index=False)
    clean_inter.to_csv(OUTPUT_DIR / "clean_interactions.csv", index=False)
    clean_trans.to_csv(OUTPUT_DIR / "clean_transactions.csv", index=False)
    
    # Task 4
    churn_features = run_task_4_features(c360, clean_inter, clean_trans)
    churn_features.to_csv(OUTPUT_DIR / "churn_features.csv", index=False)
    
    print("\nPipeline execution completed successfully.")

if __name__ == "__main__":
    main()