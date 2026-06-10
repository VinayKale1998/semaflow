# fact_order_items

*Counts in this document reflect the dataset as of Stage 1 build. 
For current row counts, query the table directly.*

## Purpose
The line-item table. One row per item within an order. The grain at which 
revenue, freight, and product-level analytics happen.

## Grain
One row per `(order_id, order_item_id)`. An order with 3 items has 3 rows.
The `order_item_id` is the sequence number within the order (1, 2, 3...).

## Row count
112,650 rows across ~99,441 orders. Most orders are single-item; the multi-item 
tail explains why item count exceeds order count.

## Columns
- `order_id` (text, FK to fact_orders): join to the parent order.
- `order_item_id` (bigint): sequence number of the item within the order. Part of PK.
- `product_id` (text, FK to dim_products): the product purchased.
- `seller_id` (text, FK to dim_sellers): the seller fulfilling this line item.
- `shipping_limit_date` (text, stored as text): deadline by which the seller 
  must hand the item to the carrier. Same `YYYY-MM-DD HH:MM:SS` text format 
  as fact_orders timestamps. Cast to use.
- `price` (double precision): item price in BRL (Brazilian real).
- `freight_value` (double precision): shipping cost for this item in BRL.

## Key relationships
- Many-to-one with `fact_orders` via `order_id`.
- Many-to-one with `dim_products` via `product_id`.
- Many-to-one with `dim_sellers` via `seller_id`.

## Quirks worth knowing

### Revenue is line-item, not order-level
Total revenue is `SUM(price)` from this table, not from fact_orders or 
fact_order_payments. fact_order_payments includes installment fees and 
payment-method splits that inflate totals (the fan-out). For clean revenue 
numbers, aggregate from here.

### Freight is separate from price
`price` and `freight_value` are stored as separate columns. "Revenue" in 
the strict sense is price alone. "Total customer spend" is price + freight. 
Both are valid measures depending on the question.

### Multi-seller orders exist
One order can have line items from different sellers. The `seller_id` lives 
on this table, not on fact_orders, because the relationship is at the item 
level, not the order level.

## Common questions this table answers
- What was total revenue in [period]?
- Which products or categories had the highest revenue?
- Which sellers sold the most?
- What is the average order value?
- What is the average items-per-order?

## Questions this table CANNOT answer alone
- Order status filtering (need fact_orders for delivered vs canceled).
- Payment method analysis (need fact_order_payments).
- Customer geographic breakdown (need dim_customers).
- Product category names in English (need dim_category_translation).