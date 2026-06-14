# dim_customers

## Purpose
Customer dimension. Identifies each customer-order relationship and links 
to geography. Distinguishes per-order customer identity from per-human 
customer identity.

## Grain
One row per `customer_id`. Note: customer_id is NOT one row per human.

## Row count
~99,441 rows. Matches the order count because customer_id is per-order, 
not per-human.

## Columns
- `customer_id` (text, PK): per-order customer identifier. Unique per 
  fact_orders row.
- `customer_unique_id` (text): per-human identifier. The same person 
  placing two orders has two customer_id values but one customer_unique_id.
- `customer_zip_code_prefix` (bigint): first 5 digits of the Brazilian 
  CEP postal code. Links to geo_lookup.
- `customer_city` (text): city name as recorded at order time.
- `customer_state` (text): two-letter Brazilian state code (e.g., SP, RJ, MG).

## Key relationships
- One-to-many with `fact_orders` via `customer_id`.
- Many-to-one with `geo_lookup` via `customer_zip_code_prefix`.

## Quirks worth knowing

### Joining to geo_lookup uses different column names
This table's `customer_zip_code_prefix` column joins to geo_lookup's 
`zip_prefix` column. The two sides have different names. There is no 
foreign key constraint enforcing this join, so a customer with a zip 
prefix that does not exist in geo_lookup will silently produce a null 
on left join (or be dropped on inner join). When geographic coverage 
matters, use LEFT JOIN and check for nulls.



### customer_id vs customer_unique_id (THE critical quirk)
This is the most-confused part of the Olist schema. `customer_id` is 
per-order. Every order has a new customer_id even for repeat customers. 
`customer_unique_id` is the actual human. To answer "how many unique 
customers did we serve" use `COUNT(DISTINCT customer_unique_id)`. To 
answer "how many orders had a customer attached" use `COUNT(customer_id)`.

The fact_orders table joins on customer_id, not customer_unique_id. This 
means a naive "orders per customer" using fact_orders.customer_id will 
always equal 1.0. To get real repeat-customer behavior, go through 
dim_customers to resolve customer_unique_id.

### City and state are denormalized
`customer_city` and `customer_state` are stored on this table for 
convenience. They are also derivable from `customer_zip_code_prefix` 
via geo_lookup. Mismatches can occur if the customer entered a city 
that doesn't match their zip's official city. Trust the zip-derived 
value when in doubt.

### Repeat-customer rate is low
The vast majority of customers in this dataset have one order. Repeat 
purchase behavior is sparse.

## Common questions this table answers
- How many unique customers (use customer_unique_id)?
- What is the geographic distribution of customers?
- What is the repeat-purchase rate?

## Questions this table CANNOT answer alone
- Revenue per customer (need fact_order_items via fact_orders).
- Customer lifetime value across orders (need fact_orders for time series).