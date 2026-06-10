# Seller Compliance Policy

## Purpose
Defines the requirements a seller must meet to remain active on the Olist 
platform. This policy is referenced when answering questions about seller 
quality, account suspensions, and platform standards.

## Core requirements

### Order fulfillment
Sellers must ship items to the carrier by the `shipping_limit_date` 
recorded in fact_order_items. Repeated late handoffs trigger automated 
warnings and, after a threshold, account review.

### Order acceptance rate
Sellers are expected to fulfill the orders they accept. Cancellations 
initiated by the seller (as opposed to the customer) count negatively 
against the seller's compliance score. Excessive seller-initiated 
cancellations lead to suspension.

### Listing accuracy
Product listings must match what is shipped. Discrepancies surface in 
customer reviews (low review_score with comment_message describing the 
mismatch) and in returns. Sellers with patterns of inaccurate listings 
are subject to listing audits.

### Response to customer reviews
Sellers are expected to respond to customer reviews, especially negative 
ones. The `review_answer_timestamp` in fact_order_reviews captures this. 
Sellers with low response rates receive lower placement in search results.

## Enforcement signals

The platform monitors:
- On-time shipment rate per seller (from fact_order_items.shipping_limit_date 
  and the actual handoff timestamps on fact_orders)
- Seller-initiated cancellation rate (from fact_orders.order_status)
- Average review_score per seller
- Review response rate

## Consequences of non-compliance

Sellers progress through warnings, suspension, and permanent deactivation. 
Deactivated sellers retain a row in dim_sellers but stop appearing as 
seller_id on new fact_order_items. The data model does not include a 
"suspended" flag; status is inferred from absence of recent activity.

## What this policy does NOT cover
- Product safety (covered by listing standards)
- Tax compliance (handled outside the platform)
- Customer-initiated returns (covered by the returns policy)