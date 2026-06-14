# dim_products

## Purpose
Product dimension. Attributes of each SKU sold on the platform.

## Grain
One row per `product_id`.

## Row count
~32,951 products.

## Columns
- `product_id` (text, PK): unique product identifier.
- `product_category_name` (text): category in Portuguese. Join key to 
  dim_category_translation for the English version.
- `product_name_lenght` (double precision): character length of the product name 
  (note: column name has the typo "lenght" preserved from the raw data).
- `product_description_lenght` (double precision): character length of the description. 
  Same typo.
- `product_photos_qty` (double precision): number of product photos.
- `product_weight_g` (double precision): weight in grams.
- `product_length_cm` (double precision): length in cm.
- `product_height_cm` (double precision): height in cm.
- `product_width_cm` (double precision): width in cm.

## Key relationships
- One-to-many with `fact_order_items` via `product_id`.
- Many-to-one with `dim_category_translation` via `product_category_name`.

## Quirks worth knowing

### Numeric columns stored as double precision
All measurement and count columns (photos_qty, weight, dimensions, name 
length, description length) are stored as `double precision`, not integer. 
This is a load-time artifact: pandas to_sql converts integer columns with 
null values into floats (because NaN is a float in pandas). Cast to int 
in queries if you need integer semantics, but be aware some rows are null.

### Categories are Portuguese here
`product_category_name` is in Portuguese (e.g., `cama_mesa_banho`, 
`eletrodomesticos`, `informatica_acessorios`). For English category names, 
join to dim_category_translation. Most analytics queries will need this 
join to produce human-readable category labels.

### Typos preserved from raw data
`product_name_lenght` and `product_description_lenght` are spelled with 
the original typo from the Olist CSV. Preserved for source fidelity. 
Use the column names as-is.

### Nullable text-quality fields
A small number of products have null category_name, weight, dimensions, 
or photo count. Filter nulls when these fields matter for analysis.

### Category-token blurring
The Portuguese category tokens (cama_mesa_banho, eletrodomesticos, 
informatica_acessorios, etc.) embed close to each other in vector space 
because they share semantic neighborhoods. This is the documented 
retrieval failure mode the hybrid search in Stage 4 was designed to 
address. See the architecture bible.

## Common questions this table answers
- How many products are listed?
- What is the category distribution?
- What is the average product weight or size?

## Questions this table CANNOT answer alone
- Product sales or revenue (need fact_order_items).
- English category names (need dim_category_translation).
- Which sellers carry which products (need fact_order_items).