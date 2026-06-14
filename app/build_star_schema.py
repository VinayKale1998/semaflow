import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

SQL = """
-- =========================================================
-- DIMENSIONS
-- =========================================================

DROP TABLE IF EXISTS dim_customers CASCADE;
CREATE TABLE dim_customers AS SELECT * FROM raw_customers;
ALTER TABLE dim_customers ADD PRIMARY KEY (customer_id);

DROP TABLE IF EXISTS dim_sellers CASCADE;
CREATE TABLE dim_sellers AS SELECT * FROM raw_sellers;
ALTER TABLE dim_sellers ADD PRIMARY KEY (seller_id);

DROP TABLE IF EXISTS dim_products CASCADE;
CREATE TABLE dim_products AS SELECT * FROM raw_products;
ALTER TABLE dim_products ADD PRIMARY KEY (product_id);

DROP TABLE IF EXISTS dim_category_translation CASCADE;
CREATE TABLE dim_category_translation AS SELECT * FROM raw_category_translation;
ALTER TABLE dim_category_translation ADD PRIMARY KEY (product_category_name);

-- geo_lookup already built with its primary key in the previous step.

-- =========================================================
-- FACTS
-- =========================================================

-- ORDERS: grain = one row per order
DROP TABLE IF EXISTS fact_orders CASCADE;
CREATE TABLE fact_orders AS SELECT * FROM raw_orders;
ALTER TABLE fact_orders ADD PRIMARY KEY (order_id);
ALTER TABLE fact_orders
  ADD CONSTRAINT fk_orders_customer
  FOREIGN KEY (customer_id) REFERENCES dim_customers(customer_id);

-- ORDER ITEMS: grain = one row per (order, item_sequence)
DROP TABLE IF EXISTS fact_order_items CASCADE;
CREATE TABLE fact_order_items AS SELECT * FROM raw_order_items;
ALTER TABLE fact_order_items ADD PRIMARY KEY (order_id, order_item_id);
ALTER TABLE fact_order_items
  ADD CONSTRAINT fk_items_order   FOREIGN KEY (order_id)   REFERENCES fact_orders(order_id),
  ADD CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES dim_products(product_id),
  ADD CONSTRAINT fk_items_seller  FOREIGN KEY (seller_id)  REFERENCES dim_sellers(seller_id);

-- PAYMENTS: grain = one row per (order, payment_sequential)
DROP TABLE IF EXISTS fact_order_payments CASCADE;
CREATE TABLE fact_order_payments AS SELECT * FROM raw_order_payments;
ALTER TABLE fact_order_payments ADD PRIMARY KEY (order_id, payment_sequential);
ALTER TABLE fact_order_payments
  ADD CONSTRAINT fk_payments_order FOREIGN KEY (order_id) REFERENCES fact_orders(order_id);

-- REVIEWS: grain = one row per review_id. (review_id has duplicates in raw, so
-- we de-duplicate by keeping the latest review per review_id.)
DROP TABLE IF EXISTS fact_order_reviews CASCADE;
CREATE TABLE fact_order_reviews AS
SELECT DISTINCT ON (review_id) *
FROM raw_order_reviews
ORDER BY review_id, review_answer_timestamp DESC NULLS LAST;
ALTER TABLE fact_order_reviews ADD PRIMARY KEY (review_id);
ALTER TABLE fact_order_reviews
  ADD CONSTRAINT fk_reviews_order FOREIGN KEY (order_id) REFERENCES fact_orders(order_id);
"""

with engine.begin() as conn:
    for stmt in SQL.split(";"):
        if stmt.strip():
            conn.execute(text(stmt))

# Verify
TABLES = [
    "dim_customers", "dim_sellers", "dim_products", "dim_category_translation",
    "geo_lookup",
    "fact_orders", "fact_order_items", "fact_order_payments", "fact_order_reviews",
]

print("Star schema built. Row counts:")
with engine.connect() as conn:
    for t in TABLES:
        n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
        print(f"  {t:<28} {n:>10,}")
