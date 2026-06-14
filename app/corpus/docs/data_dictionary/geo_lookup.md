# geo_lookup

## Purpose
Cleaned geographic lookup. One row per Brazilian zip code prefix with 
deduplicated city, state, and average coordinates. Derived from the 
messy raw_geolocation table.

## Grain
One row per `zip_code_prefix`.

## Row count
~19,000 zip code prefixes.

## Columns
- `zip_code_prefix` (text or int, PK): the first 5 digits of the Brazilian 
  CEP postal code.
- `lat` (numeric): average latitude across all raw_geolocation rows for 
  this prefix.
- `lng` (numeric): average longitude.
- `city` (text): most-common (mode) city name for this prefix.
- `state` (text): most-common state code for this prefix.

## Key relationships
- One-to-many with `dim_customers` via `customer_zip_code_prefix`.
- One-to-many with `dim_sellers` via `seller_zip_code_prefix`.

## Quirks worth knowing

### Built via dedupe, not loaded
The raw_geolocation table has multiple rows per zip prefix with conflicting 
city names, state codes, and slightly different lat/lng. Stage 1 collapsed 
this into geo_lookup using two rules: **average the coordinates, take the 
mode of city and state.** This decision is locked in the architecture bible.

The averaging is reasonable because Brazilian CEP prefixes cover small 
geographic areas. Coordinate variance within a prefix is typically under 
a kilometer.

### Mismatches with dim_customers and dim_sellers
The customer_city stored on dim_customers may not match geo_lookup.city 
for the same zip prefix. This happens when the customer typed a city 
name that does not match the official one. Both values are kept. When in 
doubt, trust geo_lookup as the canonical source.

### Some zip prefixes in customers/sellers have no geo_lookup row
A small fraction of zip prefixes referenced in dim_customers or dim_sellers 
do not appear in raw_geolocation and therefore not in geo_lookup. Use 
LEFT JOIN if you want to preserve un-located customers or sellers.

### Use cases
This table powers geographic analytics: distance between customer and 
seller, regional sales distribution, state-level breakdowns. Without it, 
those queries would have to dedupe raw_geolocation inline, which is slow 
and error-prone.

## Common questions this table answers
- What is the city/state for a given zip prefix?
- What are the coordinates for a zip prefix?
- How is the customer/seller base distributed geographically?

## Questions this table CANNOT answer alone
- Volume or revenue (no fact data here).
- Customer or seller identity (need dim_customers or dim_sellers).