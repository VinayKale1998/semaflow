# Returns and Cancellations Policy

## Purpose
Defines how Olist handles customer-initiated returns and cancellations. 
Referenced when answering questions about order cancellation rates, the 
canceled status, and customer satisfaction patterns.

## Cancellation flow

### Pre-shipment cancellation
A customer can cancel an order any time before it reaches `shipped` 
status. The order transitions to `canceled` and the payment is reversed. 
This is the cleanest cancellation path and accounts for most of the 
canceled order tail visible in fact_orders.

### Post-shipment cancellation
After shipment, a customer cannot unilaterally cancel. The order must 
go through the returns process if the customer no longer wants the item.

### Seller-initiated cancellation
A seller may cancel an order they cannot fulfill (out of stock, listing 
error). This counts against the seller's compliance score and reflects 
on the platform's reliability metrics.

## Returns flow

### Eligibility
Customers can return items within a fixed window after delivery. Returns 
must be initiated through the platform, not directly with the seller.

### Reasons
Common reasons include: item not as described, damaged in transit, 
wrong item shipped, customer changed mind. Reasons are not captured in 
the current data model.

### Refund timing
Once a return is approved, refunds are processed back through the 
original payment method. For installment payments, the refund cancels 
the remaining installments and refunds the paid portion.

## Data model implications

The current schema captures:
- `canceled` as an order_status value on fact_orders
- The payment_value on fact_order_payments reflects the original payment, 
  not the refunded portion. Refunds are not represented in the data.

The schema does NOT capture:
- Return events (no return_id, no return timestamp)
- Refund amounts or status
- Reason codes for cancellation

## Analytics implications

- Cancellation rate can be computed from fact_orders.order_status.
- Return rate cannot be computed from this data. Questions about 
  "how often do customers return items" cannot be answered.
- Net revenue (gross revenue minus refunds) cannot be derived. Revenue 
  numbers from fact_order_items represent booked revenue, not net.