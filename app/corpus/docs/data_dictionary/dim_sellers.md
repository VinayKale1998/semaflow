# dim_sellers

## Purpose
Seller dimension. The merchants fulfilling orders on the Olist platform.

## Grain
One row per `seller_id`. Sellers are stable identities (unlike customers, 
no per-order id quirk).

## Row count
~3,095 sellers.

## Columns
- `seller_id` (text, PK): unique seller identifier.
- `seller_zip_code_prefix` (bigint): seller's CEP zip prefix.
- `seller_city` (text): seller's city.
- `seller_state` (text): two-letter state code.

## Key relationships
- One-to-many with `fact_order_items` via `seller_id`.
- Many-to-one with `geo_lookup` via `seller_zip_code_prefix`.
- No direct link to fact_orders. A seller relates to orders only through 
  the items they fulfilled.

## Quirks worth knowing

### Sellers join through items, not orders
A common mistake is trying to join `dim_sellers` to `fact_orders` 
directly. There is no seller_id on the orders table. Sellers connect 
to orders through `fact_order_items.seller_id`. An order with items 
from multiple sellers will produce multiple seller rows when joined 
through items.

### Joining to geo_lookup uses different column names
This table's `seller_zip_code_prefix` column joins to geo_lookup's 
`zip_prefix` column. The two sides have different names. No foreign 
key constraint enforces the relationship. Use LEFT JOIN when seller 
geographic coverage matters.

### Geographic concentration
Sellers are heavily concentrated in southeast Brazil, especially Sao Paulo 
state. Any geographic seller analysis will show this skew.

### No seller history or status
The dim_sellers table has no "active" flag, no joined-on date, no 
performance score. It is identity plus location only. Performance is 
derived from fact_order_items aggregates.

## Common questions this table answers
- How many sellers are on the platform?
- What is the geographic distribution of sellers?
- How does seller location relate to customer location (cross-state shipping)?

## Questions this table CANNOT answer alone
- Seller revenue or volume (need fact_order_items).
- Seller satisfaction rates (need fact_order_reviews joined through items).
- Seller activity over time (need fact_order_items.shipping_limit_date).