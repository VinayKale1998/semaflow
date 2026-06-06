import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv("/semaflow/.env")
engine = create_engine(os.environ["DATABASE_URL"])

# Collapse raw_geolocation (many rows per zip) into one row per zip prefix.
# Coordinates are averaged (center of the zip). City/state taken as the most
# common value per zip via mode, so we keep a sensible label.
SQL = """
DROP TABLE IF EXISTS geo_lookup;

CREATE TABLE geo_lookup AS
WITH ranked_labels AS (
    SELECT
        geolocation_zip_code_prefix AS zip_prefix,
        geolocation_city  AS city,
        geolocation_state AS state,
        COUNT(*) AS freq,
        ROW_NUMBER() OVER (
            PARTITION BY geolocation_zip_code_prefix
            ORDER BY COUNT(*) DESC
        ) AS rn
    FROM raw_geolocation
    GROUP BY geolocation_zip_code_prefix, geolocation_city, geolocation_state
),
coords AS (
    SELECT
        geolocation_zip_code_prefix AS zip_prefix,
        AVG(geolocation_lat) AS lat,
        AVG(geolocation_lng) AS lng
    FROM raw_geolocation
    GROUP BY geolocation_zip_code_prefix
)
SELECT
    c.zip_prefix,
    c.lat,
    c.lng,
    l.city,
    l.state
FROM coords c
JOIN ranked_labels l
  ON c.zip_prefix = l.zip_prefix AND l.rn = 1;

ALTER TABLE geo_lookup ADD PRIMARY KEY (zip_prefix);
"""

with engine.begin() as conn:
    for stmt in SQL.strip().split(";"):
        if stmt.strip():
            conn.execute(text(stmt))

with engine.connect() as conn:
    raw = conn.execute(text("SELECT COUNT(*) FROM raw_geolocation")).scalar()
    lookup = conn.execute(text("SELECT COUNT(*) FROM geo_lookup")).scalar()
    distinct = conn.execute(text(
        "SELECT COUNT(DISTINCT geolocation_zip_code_prefix) FROM raw_geolocation"
    )).scalar()
    sample = conn.execute(text(
        "SELECT zip_prefix, ROUND(lat::numeric,4), ROUND(lng::numeric,4), city, state "
        "FROM geo_lookup ORDER BY zip_prefix LIMIT 5"
    )).fetchall()

print(f"raw_geolocation rows:        {raw:,}")
print(f"distinct zip prefixes:       {distinct:,}")
print(f"geo_lookup rows:             {lookup:,}")
print(f"primary key on zip_prefix:   added (load would have failed if not unique)")
print("\nSample rows:")
for r in sample:
    print(" ", tuple(r))
