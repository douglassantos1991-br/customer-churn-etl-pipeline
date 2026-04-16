-- =============================================================================
-- TASK 3: SQL QUERIES
-- =============================================================================

-- Q1: List customers with a service visit within 365 days after their first purchase
-- Rule: First purchase is defined as the minimum transaction_date of type 'purchase'.
WITH FirstPurchase AS (
    SELECT customer_id, MIN(transaction_date) as first_purchase_date
    FROM clean_transactions
    WHERE transaction_type = 'purchase'
    GROUP BY customer_id
)
SELECT 
    fp.customer_id, 
    fp.first_purchase_date, 
    MIN(t.transaction_date) as first_service_after_purchase_date
FROM FirstPurchase fp
JOIN clean_transactions t ON fp.customer_id = t.customer_id
WHERE t.transaction_type = 'service' 
  AND t.transaction_date > fp.first_purchase_date 
  AND t.transaction_date <= fp.first_purchase_date + INTERVAL '365 days'
GROUP BY fp.customer_id, fp.first_purchase_date;


-- Q2: Response rate per campaign channel
-- Rule: Response = interaction with outcome 'interested' during the campaign period.
SELECT 
    c.channel,
    COUNT(DISTINCT c.campaign_id) as campaigns_in_channel,
    COUNT(i.interaction_id) as total_linked_interactions,
    SUM(CASE WHEN i.outcome = 'interested' THEN 1 ELSE 0 END) as positive_responses,
    ROUND(100.0 * SUM(CASE WHEN i.outcome = 'interested' THEN 1 ELSE 0 END) / 
        NULLIF(COUNT(i.interaction_id), 0), 2) as response_rate_pct
FROM raw_campaigns c
LEFT JOIN clean_interactions i ON i.campaign_id = c.campaign_id
  AND i.interaction_date BETWEEN c.start_date AND c.end_date
GROUP BY c.channel;


-- Q3: Customers with no interaction in the 180 days before 2024-06-01 (Reference Date)
-- Logic: Finding customers whose latest interaction is older than 180 days from the cutoff.
SELECT 
    customer_id, 
    segment, 
    EXTRACT(DAY FROM ('2024-06-01'::timestamp - MAX(interaction_date))) as days_since_last_interaction
FROM customer_360
JOIN clean_interactions USING (customer_id)
GROUP BY customer_id, segment
HAVING MAX(interaction_date) < '2024-06-01'::timestamp - INTERVAL '180 days'
ORDER BY days_since_last_interaction DESC;


-- Q4: Top 3 customers by total purchase amount per state
-- Rule: Use a window function to rank within each state.
SELECT * FROM (
    SELECT 
        state, 
        customer_id, 
        SUM(amount) as total_purchase_amount,
        RANK() OVER(PARTITION BY state ORDER BY SUM(amount) DESC) as rank_in_state
    FROM customer_360
    JOIN clean_transactions USING (customer_id)
    WHERE transaction_type = 'purchase'
      AND amount > 0 -- Using logic from Task 2 to focus on revenue-generating purchases
    GROUP BY state, customer_id
) ranked_customers
WHERE rank_in_state <= 3;