# dim_category_translation

## Purpose
Category name translation lookup. Maps Olist's Portuguese category names 
to their English equivalents. Used to produce human-readable category 
labels in analytics output.

## Grain
One row per Portuguese category name.

## Row count
~71 category translations.

## Columns
- `product_category_name` (text, PK): Portuguese category name 
  (e.g., `cama_mesa_banho`).
- `product_category_name_english` (text): English equivalent 
  (e.g., `bed_bath_table`).

## Key relationships
- One-to-many with `dim_products` via `product_category_name`.

## Quirks worth knowing

### Coverage is not complete
The translation table covers most but not all categories present in 
dim_products. A small number of products carry a category that has no 
translation row. Use LEFT JOIN if you want to keep the un-translated 
categories rather than drop them.

### English names are also snake_case
The English versions are not natural prose. They are snake_cased 
identifiers like `health_beauty`, `watches_gifts`, `computers_accessories`. 
For UI-grade labels you may want to post-process (replace underscores 
with spaces, title-case).

### Small table, big lift
This is a 71-row table that powers most user-facing category analytics. 
Cheap to join, high value.

## Common questions this table answers
- What is the English name for [Portuguese category]?
- How many distinct categories exist?

## Questions this table CANNOT answer alone
- Anything quantitative. This is a lookup, not a fact source.