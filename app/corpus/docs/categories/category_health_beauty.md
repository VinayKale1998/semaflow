# Category: health_beauty (beleza_saude)

## What it covers
Personal care products for hygiene, grooming, and general wellness. 
Includes: shampoos, soaps, deodorants, oral care, basic skin care, 
vitamins and supplements, first-aid items, hygiene products for all 
ages.

## What it does NOT cover
- Perfumes and fragrances (use `perfumery`)
- Baby-specific care items like diapers, baby shampoo, baby lotion 
  (use `baby`)
- Cosmetics for makeup and color (sometimes catalogued separately under 
  beauty subcategories not present in this dataset's translation)
- Medical devices or prescription medications (not sold on the platform)

## Collision cluster
This category sits in the personal-care cluster with `perfumery` and 
`baby`. Embeddings for all three live near each other in vector space 
because they share semantic neighborhoods (skin contact, personal use, 
fragrance, body). When retrieving for queries about "personal care" or 
"hygiene," all three may surface and the boundaries matter.

## Common analytics
The English name in dim_category_translation is `health_beauty`. This 
is consistently a top-revenue category in Olist. Often appears in 
"top categories by revenue" queries (~1.26M BRL revenue in the Stage 1 
baseline).