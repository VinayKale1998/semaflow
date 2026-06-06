import os, sys, urllib.request

DEST = "/semaflow/data"
os.makedirs(DEST, exist_ok=True)

# Known-good raw mirror of the 9 Olist CSVs
BASE = "https://raw.githubusercontent.com/fortunewalla/olist/main/datasets"
FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]

ok, failed = [], []
for f in FILES:
    url = f"{BASE}/{f}"
    out = os.path.join(DEST, f)
    try:
        print(f"Downloading {f} ...", end=" ", flush=True)
        urllib.request.urlretrieve(url, out)
        size = os.path.getsize(out)
        if size < 100:
            raise ValueError(f"file too small ({size} bytes), likely an error page")
        print(f"ok ({size:,} bytes)")
        ok.append(f)
    except Exception as e:
        print(f"FAILED: {e}")
        failed.append(f)

print(f"\nDone. {len(ok)} ok, {len(failed)} failed.")
if failed:
    print("Failed files:", failed)
    sys.exit(1)
