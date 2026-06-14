# Listing Standards Policy

## Purpose
Defines the minimum quality requirements for product listings on the 
Olist platform. Referenced when answering questions about product data 
quality and the fields in dim_products.

## Required fields

Every listed product must have:
- A category (`product_category_name` in dim_products)
- A product name (length captured in `product_name_lenght`)
- A description (length captured in `product_description_lenght`)
- At least one photo (`product_photos_qty` >= 1)
- Physical dimensions (weight in grams, length/height/width in cm)

The schema allows nulls in these fields, reflecting historical data 
where listings predated stricter enforcement. Current listings must 
populate all required fields.

## Photo requirements
Photos must show the actual product. The platform encourages multiple 
angles. `product_photos_qty` captures the count but not quality. 
Listings with one low-quality photo pass schema validation but may be 
flagged in manual review.

## Category accuracy
Products must be listed in the most specific applicable category. 
Listing a phone in `eletronicos` instead of `telefonia_celular` is 
considered miscategorization and is corrected during manual review. 
This is one source of the semantic-similarity collisions in the 
category taxonomy (see category definition docs).

## Dimension accuracy
Weight and dimensions are used to compute shipping cost (`freight_value` 
on fact_order_items). Inaccurate dimensions inflate freight calculations 
and lead to customer disputes when the item arrives lighter or smaller 
than declared.

## Name and description length

The `product_name_lenght` and `product_description_lenght` columns are 
preserved with the Portuguese typo "lenght" (instead of "length") from 
the original data source. These capture character counts, not word 
counts. Listings with very short names or descriptions are flagged for 
review.

## Translation
For categories with English translations available 
(`dim_category_translation`), product listings carry the Portuguese 
category internally. The English name is rendered to international 
users at presentation time, not stored on the product row.

## What this policy does NOT cover
- Pricing strategy (sellers set their own prices)
- Inventory levels (not represented in the data model)
- Shipping carrier selection (handled separately)