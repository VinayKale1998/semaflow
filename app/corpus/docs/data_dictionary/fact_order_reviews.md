# fact_order_reviews

## Purpose
The reviews table. Customer-submitted ratings and comments tied to orders. 
The post-purchase satisfaction signal.

## Grain
One row per `review_id` after deduplication. The raw_order_reviews table 
contains duplicates (same review_id appearing multiple times). Stage 1 
applied a "latest-answer-wins" dedupe: keep the row with the most recent 
`review_answer_timestamp` per review_id.

## Row count
~98,410 rows after dedupe. Lower than the order count (~99,441) because 
not every order receives a review.

## Columns
- `review_id` (text, PK): unique after dedupe.
- `order_id` (text, FK to fact_orders): the order being reviewed. Note: 
  a small number of orders have multiple reviews in the raw data, but after 
  dedupe this effectively functions as one-to-one with orders.
- `review_score` (bigint): 1 to 5, customer rating.
- `review_comment_title` (text, nullable): optional title.
- `review_comment_message` (text, nullable): optional free-text comment.
- `review_creation_date` (text, stored as text): when the review form was 
  sent to the customer. `YYYY-MM-DD HH:MM:SS` format.
- `review_answer_timestamp` (text, stored as text): when the customer 
  submitted the review. Used for the dedupe ordering.

## Key relationships
- Many-to-one with `fact_orders` via `order_id` (effectively one-to-one 
  post-dedupe).

## Quirks worth knowing

### order_id is nullable on this table
The foreign key to fact_orders exists but order_id is not marked NOT NULL. 
In practice all current rows have order_id populated, but the schema permits 
null. Filter for non-null if joining and counting matters.

### Latest-answer-wins dedupe
The raw data has duplicate review_id rows because the Olist platform 
allowed customers to re-submit reviews. Stage 1 build kept only the most 
recent `review_answer_timestamp` per review_id. Rows with null answer 
timestamps were ordered last (NULLS LAST). This is a permanent decision: 
the raw_order_reviews table still contains duplicates if anyone needs 
to audit, but fact_order_reviews is dedupe-clean.

### Not every order has a review
About 1% of orders have no review row. Filtering questions like "average 
review score for delivered orders" should LEFT JOIN, not INNER JOIN, if 
the answer should include unreviewed orders as a separate bucket.

### Comments are mostly empty
The `review_comment_title` and `review_comment_message` fields are 
nullable and frequently empty. For sentiment or text-analytics work, 
filter to non-null comments first.

## Common questions this table answers
- What is the average review score overall or by period?
- What percent of orders score 5 vs 1?
- How does review score correlate with delivery time?

## Questions this table CANNOT answer alone
- Customer-level patterns across orders (need dim_customers via fact_orders).
- Product or seller satisfaction (need fact_order_items joined in).
- Filtering by order status (need fact_orders).