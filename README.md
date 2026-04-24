# Prodigy — Pre-paid DBU Burn-down

Dashboard + base SQL template showing how Prodigy is burning down their pre-paid DBU pool per month, broken out by workload / SKU group, based on Databricks `system.billing` system tables.

## What's deployed (reference instance)

| Artifact | Link |
|---|---|
| Dashboard | https://fevm-dazana-classic-ws.cloud.databricks.com/dashboardsv3/01f140018f0616dfbd74c3c3ac926c4b |
| Published | https://fevm-dazana-classic-ws.cloud.databricks.com/dashboardsv3/01f140018f0616dfbd74c3c3ac926c4b/published |
| Base SQL | `prodigy_burndown.sql` (this repo) |

> The reference instance runs against `dazana-classic-ws`'s own `system.billing.usage`. It's a real burn calculation — it will just use this workspace's DBU activity as a stand-in until the artifacts are installed in Prodigy's workspace.

## What the customer edits

Every widget is built on top of two CTEs at the top of each query. To onboard Prodigy, edit these two blocks and redeploy:

```sql
WITH contract AS (
  SELECT
    DATE '2025-01-01'        AS contract_start,          -- contract effective date
    3                         AS contract_years,          -- term in years
    CAST(3000000  AS DOUBLE) AS contract_amount_usd,     -- total $ signed
    CAST(1000000  AS DOUBLE) AS expected_annual_dbu_usd  -- expected annual burn
),
discounts AS (
  SELECT * FROM (VALUES
    ('ALL_PURPOSE', 0.25),
    ('JOBS',        0.30),
    ('DLT',         0.30),
    ('SQL',         0.35),
    ('MODEL_SERVING', 0.20),
    -- ... etc ...
  ) AS d(product_group, discount_pct)
)
```

- `contract`: one row, contract metadata. Burn-down line and % consumed are derived from these numbers.
- `discounts`: one row per Databricks product group (`billing_origin_product` value) with the fractional list-price discount from Prodigy's MSA. Unlisted groups default to 0% discount via `COALESCE`.

## What the dashboard shows

**Row 1 — KPIs** (Contract $, Spent to Date, Remaining, % Consumed, Avg Monthly Burn, List $ Pre-discount)

**Row 2 — Burn-down** — one line chart with three series:
- Actual cumulative contract $ spend (daily)
- Expected straight-line burn (contract $ / term)
- Contract budget ceiling

When actual climbs above expected, Prodigy is burning faster than planned; if it crosses the budget line before contract end, they'll need a top-up.

**Row 3 — Monthly breakdown**
- Stacked monthly bar: contract $ by product group per month
- Ranked bar: contract $ per product group, to date

**Row 4 — SKU detail table** — top 100 SKUs by contract $ with DBUs, avg list price, applied discount, list cost, contract cost.

## How contract $ is computed

```
contract_cost_usd = dbus × list_price_usd × (1 − discount_pct)
```

where:
- `dbus = system.billing.usage.usage_quantity` (filtered to `usage_unit = 'DBU'`)
- `list_price_usd = system.billing.list_prices.pricing.default`, joined on `sku_name` and the price's effective date range
- `discount_pct` comes from the `discounts` CTE via `billing_origin_product`

Key accuracy notes:
- We use `billing_origin_product` (coarse grouping) for discount lookup because discounts are typically negotiated at the workload level, not the line-item SKU level. If Prodigy's MSA negotiates at SKU-level, change the join to `sku_name`.
- We use `pricing.default` (published list price). If Prodigy wants to use `pricing.effective_list.default` (which resolves promotional pricing), swap that field.
- We filter usage to the contract window only — pre-contract consumption won't count against burn-down.
- The cumulative burn-down uses a calendar-spined series so weekends/zero-usage days don't create visual gaps.

## Deploying to Prodigy's workspace

1. Share `prodigy_burndown.sql` with Prodigy — they edit the `contract` and `discounts` CTEs with their real values.
2. Export this dashboard as JSON and import into Prodigy's workspace:
   ```
   databricks api get /api/2.0/lakeview/dashboards/01f140018f0616dfbd74c3c3ac926c4b \
     --profile Dazana-classic-ws-pat -o json > dashboard.json

   # In their workspace (after they edit the serialized_dashboard for their contract values):
   databricks api post /api/2.0/lakeview/dashboards --profile <their_profile> \
     --json @dashboard.json
   ```
3. Or: run `python3 build_dashboard.py` after editing the `CORE_CTE` string in that script with their values, then post the payload against their workspace.

## Files

```
prodigy_burndown/
├── README.md              # this file
├── prodigy_burndown.sql   # the stand-alone base query (for ad-hoc runs)
├── build_dashboard.py     # script that assembles the Lakeview JSON
└── dashboard_payload.json # assembled dashboard payload (generated)
```
