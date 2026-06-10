# Category: perfumery (perfumaria)

## What it covers
Fragrances and scented body products. Includes: perfumes, colognes, 
body sprays, scented lotions where fragrance is the primary attribute. 
Both men's and women's fragrances.

## What it does NOT cover
- Unscented or function-first personal care (use `health_beauty`)
- Baby-specific scented products (use `baby`)
- Home fragrances like candles or diffusers (catalogued under 
  `home_comfort` or similar)

## Collision cluster
Sits with `health_beauty` and `baby` in the personal-care cluster. 
Vector embeddings of `perfumaria` are close to `beleza_saude` because 
both involve body-contact products, fragrance, and personal use. 
Disambiguation matters: a query about "skincare" should retrieve 
health_beauty, not perfumery.

## Common analytics
English name: `perfumery`. Smaller revenue category than health_beauty 
but consistently active. Sensitive to seasonal patterns (holiday gifting).