import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# CSV filename -> raw table name
TABLES = {
    "olist_customers_dataset.csv":            "raw_customers",
    "olist_geolocation_dataset.csv":          "raw_geolocation",
    "olist_order_items_dataset.csv":          "raw_order_items",
    "olist_order_payments_dataset.csv":       "raw_order_payments",
    "olist_order_reviews_dataset.csv":        "raw_order_reviews",
    "olist_orders_dataset.csv":               "raw_orders",
    "olist_products_dataset.csv":             "raw_products",
    "olist_sellers_dataset.csv":              "raw_sellers",
    "product_category_name_translation.csv":  "raw_category_translation",
}

for csv_name, table in TABLES.items():
    path = os.path.join(DATA, csv_name)
    print(f"Loading {csv_name} -> {table} ...", end=" ", flush=True)
    df = pd.read_csv(path)
    df.to_sql(table, engine, if_exists="replace", index=False, chunksize=10000)
    print(f"ok ({len(df):,} rows, {len(df.columns)} cols)")

print("\nRow counts from the database:")
with engine.connect() as conn:
    for table in TABLES.values():
        n = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        print(f"  {table:<28} {n:>10,}")

print("\nPass 1 complete. All raw tables loaded.")
