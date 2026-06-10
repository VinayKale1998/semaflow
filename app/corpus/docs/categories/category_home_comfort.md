# Category: home_comfort (cama_mesa_banho)

## What it covers
Bedding, table linens, and bath textiles. The literal translation of 
the Portuguese is "bed, table, and bath." Includes: sheets, pillows, 
duvets, towels, tablecloths, napkins, bathrobes, shower curtains.

## What it does NOT cover
- Bed frames or furniture (use `furniture_decor`)
- Bathroom fixtures or hardware (use a home-improvement category not 
  in this dataset)
- Decorative items that aren't textile (use `furniture_decor`)

## Collision cluster
Sits with `furniture_decor` and `housewares` in the home cluster. The 
token `cama_mesa_banho` is the canonical example of category-token 
blurring in the architecture bible: the compound Portuguese token 
contains three concepts (bed, table, bath) that each have their own 
semantic neighborhoods, making embedding-based retrieval messy.

## Common analytics
English name: `bed_bath_table`. Consistently a top-revenue category. 
The Stage 1 baseline showed it as the third-highest revenue category 
at ~1.04M BRL.