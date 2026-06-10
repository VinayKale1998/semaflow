# fact_orders

## Purpose
The orders table. One row per customer order placed on the Olist platform.
The temporal anchor for most analytics.

## Grain
One row per `order_id`. An order may contain multiple items (see fact_order_items)
and may be paid through multiple installments or payment methods (see
fact_order_payments).

## Row count
99,441 orders.

## Columns

### order_id (text, primary key)
Unique identifier for the order. Join key to fact_order_items,
fact_order_payments, and fact_order_reviews.

### customer_id (text, foreign key to dim_customers)
Identifier for the customer who placed this order. Note: Olist's data model
distinguishes `customer_id` (per-order) from `customer_unique_id` (per-human)
in dim_customers. One human placing two orders shows up as two different
customer_id values that share the same customer_unique_id. Always go through
dim_customers if you need customer-level aggregation.

### order_status (text)
Current status of the order. Eight possible values, heavily skewed toward delivered.

The delivered status dominates at 96,478 rows (97.02% of all orders). The
remaining 3% breaks down across seven non-delivered statuses: shipped (1,107
orders, 1.11%), canceled (625, 0.63%), unavailable (609, 0.61%), invoiced
(314, 0.32%), processing (301, 0.30%), created (5 orders), and approved (2
orders). The created and approved tails are tiny enough to be effectively
edge cases.

For most revenue and volume analytics, filtering to `order_status = 'delivered'`
is the right move. The non-delivered tail is small but non-zero and matters
for cancellation rate or fulfillment funnel analysis.

### order_purchase_timestamp (text, stored as text NOT timestamp)
When the order was placed. Format: `YYYY-MM-DD HH:MM:SS` (example:
`2017-10-02 10:56:33`). Must be cast to timestamp for date arithmetic:
`order_purchase_timestamp::timestamp`. This is the field used as the temporal
anchor for most "as-of" analytics.

### order_approved_at (text, stored as text)
When the order was approved (typically when payment cleared). Same string
format as order_purchase_timestamp. Expect nulls for orders that never
reached the approved state (canceled before approval, unavailable, etc).

### order_delivered_carrier_date (text, stored as text)
When the order was handed to the shipping carrier. Same format. Null for
orders that did not reach this stage.

### order_delivered_customer_date (text, stored as text)
When the order was delivered to the customer. Same format. Null for orders
not yet delivered, canceled, or otherwise non-completed. This is the field
used to compute delivery latency (`order_delivered_customer_date::timestamp
- order_purchase_timestamp::timestamp`).

### order_estimated_delivery_date (text, stored as text)
The estimated delivery date promised at purchase time. Same format. Used
together with order_delivered_customer_date to measure on-time vs late
delivery.

## Key relationships
- One-to-many with `fact_order_items`. One order has 1 to N items.
- One-to-many with `fact_order_payments`. One order may have N payment rows,
  one per installment or method. **This is the fan-out source** documented
  in Stage 1.
- One-to-one (effectively) with `fact_order_reviews`. The reviews table is
  deduplicated to latest-answer-wins, so each order maps to at most one
  current review.

## Quirks worth knowing

### Timestamps stored as text
All four date columns are stored as `text`, not `timestamp`. Any date
arithmetic or filtering must cast first. Pattern:
`WHERE order_purchase_timestamp::timestamp BETWEEN ...`. This is a known
data quality issue inherited from the raw Olist CSVs.

### The payment fan-out
Joining fact_orders to fact_order_payments without aggregating payments
first multiplies rows when an order has multiple installments or payment
methods. Stage 1 baseline showed true revenue of 13.59M (correct,
aggregated) vs 14.21M (incorrect, naive join). 4.5% inflation. Always
aggregate fact_order_payments to one row per order before joining, or
join through a different grain.

### Heavy delivered skew
97% of orders are delivered. Any analysis that does not filter by status
implicitly includes a small tail of canceled, unavailable, and in-progress
orders. For "what did the business do" questions, filter to delivered.
For "what is the fulfillment funnel" questions, keep all statuses.

### Reference date
Stage 1 set `dataset_reference_date: 2018-10-17` as the "as-of" point for
current calculations. Use this when answering "recent" or "current"
questions against the corpus.

## Common questions this table answers
- How many orders were placed in [period]?
- What is the cancellation rate?
- What is the order volume trend over time?
- What is the average delivery time?
- What fraction of orders are delivered on time vs late?

## Questions this table CANNOT answer alone
- Revenue or item-count questions (need fact_order_items)
- Payment method or installment questions (need fact_order_payments)
- Customer satisfaction questions (need fact_order_reviews)
- Customer-level aggregation across orders (need dim_customers to resolve
  customer_unique_id)
- Product or category questions (need fact_order_items joined to dim_products)