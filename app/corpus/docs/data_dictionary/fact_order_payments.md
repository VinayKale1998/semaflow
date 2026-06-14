# fact_order_payments

## Purpose
The payments table. Records every payment transaction associated with an 
order, including installments. The source of the famous payment fan-out.

## Grain
One row per `(order_id, payment_sequential)`. An order paid in 3 installments 
on a single credit card produces 3 rows. An order split across a voucher 
plus a credit card produces 2+ rows.

## Row count
~103,886 rows across ~99,441 orders. The excess (~4,400 rows) is the 
fan-out: orders with multiple payment rows.

## Columns
- `order_id` (text, FK to fact_orders): join to the parent order.
- `payment_sequential` (bigint): sequence number of the payment within the order. 
  Part of PK. 1 for single-payment orders, 1..N for split-payment orders.
- `payment_type` (text): method used. Values: `credit_card`, `boleto` (Brazilian 
  bank slip), `voucher`, `debit_card`, `not_defined`.
- `payment_installments` (bigint): number of installments the customer chose. 
  0 or 1 for single-payment, up to 24 for long credit installments.
- `payment_value` (double precision): amount paid in this row, in BRL.

## Key relationships
- Many-to-one with `fact_orders` via `order_id`.
- No direct relationship to items, products, or sellers. Payment is at the 
  order level, not the line-item level.

## Quirks worth knowing

### The fan-out (THE critical quirk)
Joining fact_orders directly to fact_order_payments multiplies rows because 
of the grain mismatch. Stage 1 baseline showed true revenue at 13.59M BRL 
(correct, from fact_order_items) vs 14.21M (incorrect, from naive join with 
payments). 4.5% inflation. **Never aggregate payment_value across the raw 
fact_order_payments without first reducing to one row per order.**

The fix: either `SUM(payment_value) GROUP BY order_id` in a subquery before 
joining, or join through fact_order_items for revenue questions (since item 
price is the true revenue measure anyway).

### payment_value vs price
`payment_value` includes installment fees and is at the payment-method 
grain. It is NOT the same as `SUM(price + freight_value)` from 
fact_order_items. The difference accounts for fees, rounding, and edge 
cases. For "what the customer paid" use payment_value. For "what the 
business recognized as revenue" use price.

### Installments tell a story
`payment_installments` reveals customer purchasing behavior. Long 
installment counts (12+) correlate with higher-ticket items. Useful for 
customer-segmentation questions.

## Common questions this table answers
- What payment methods are most used?
- What is the installment distribution?
- How much of total payment comes from credit vs boleto vs voucher?
- What is the average payment installment count?

## Questions this table CANNOT answer alone
- Order status filtering (need fact_orders).
- Product or category breakdown (no product link on this table).
- True revenue numbers (use fact_order_items.price instead).