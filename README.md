# Prodigy — Pre-paid DBU Burn-down

Dashboard + base SQL template showing how a customer is burning down their pre-paid DBU pool per month, broken out by workload / SKU group, based on Databricks `system.billing` system tables.

## What you edit before running

All customer-specific values are **parameterized** — you supply them at build time. There are no hardcoded workspace IDs, paths, or contract values shipped in this repo.

### Contract terms

The two CTEs at the top of every query (`contract`, `discounts`) drive every widget. You supply them in one of two ways:

**Option A — `prodigy_burndown.sql` (ad-hoc runs):** Open the file and replace the placeholder tokens in the `contract` and `discounts` CTEs:

```sql
WITH contract AS (
  SELECT
    DATE '<contract_start_date>'                AS contract_start,          -- YYYY-MM-DD
    <contract_term_in_years>                     AS contract_years,          -- e.g. 3
    CAST(<total_contract_amount_usd>  AS DOUBLE) AS contract_amount_usd,     -- e.g. 3000000
    CAST(<expected_annual_burn_usd>   AS DOUBLE) AS expected_annual_dbu_usd  -- e.g. 1000000
),
discounts AS (
  SELECT * FROM (VALUES
    ('ALL_PURPOSE',   0.00),    -- replace 0.00 with the negotiated fractional discount
    ('JOBS',          0.00),
    ('DLT',           0.00),
    -- ... etc ...
  ) AS d(product_group, discount_pct)
)
```

**Option B — `build_dashboard.py` (dashboard build):** Pass contract values as CLI args or env vars. The discount table is still inlined in `CORE_CTE` inside the script — edit those numbers there.

### Workspace / deployment values

| Value | CLI flag | Env var | Notes |
|---|---|---|---|
| SQL warehouse ID | `--warehouse-id` | `DBU_WAREHOUSE_ID` | Workspace warehouse the dashboard queries run on |
| Workspace parent folder | `--parent-path` | `DBU_PARENT_PATH` | e.g. `/Users/you@example.com` |
| Databricks CLI profile | `--profile` | `DBU_PROFILE` | Used by deploy commands below |
| Output payload path | `--output` | `DBU_OUTPUT_PATH` | Defaults to `./dashboard_payload.json` |
| Lakeview builder path | `--lakeview-builder-path` | `LAKEVIEW_BUILDER_PATH` | Path to the `lakeview_builder` module (defaults to the vibe marketplace location under `$HOME/.vibe/...`) |

## What the dashboard shows

**Row 1 — KPIs** (Contract $, Spent to Date, Remaining, % Consumed, Avg Monthly Burn, List $ Pre-discount)

**Row 2 — Burn-down** — one line chart with three series:
- Actual cumulative contract $ spend (daily)
- Expected straight-line burn (contract $ / term)
- Contract budget ceiling

When actual climbs above expected, the customer is burning faster than planned; if it crosses the budget line before contract end, they'll need a top-up.

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
- We use `billing_origin_product` (coarse grouping) for discount lookup because discounts are typically negotiated at the workload level, not the line-item SKU level. If your MSA negotiates at SKU-level, change the join to `sku_name`.
- We use `pricing.default` (published list price). If you want to use `pricing.effective_list.default` (which resolves promotional pricing), swap that field.
- Usage is filtered to the contract window — pre-contract consumption won't count against burn-down.
- The cumulative burn-down uses a calendar-spined series so weekends/zero-usage days don't create visual gaps.

## Building the dashboard payload

```bash
python3 build_dashboard.py \
  --warehouse-id <your_warehouse_id> \
  --parent-path /Users/you@example.com \
  --profile <your_cli_profile> \
  --contract-start 2025-01-01 \
  --contract-years 3 \
  --contract-amount 3000000 \
  --expected-annual-burn 1000000 \
  --output ./dashboard_payload.json
```

Or set the equivalent env vars (`DBU_WAREHOUSE_ID`, `DBU_PARENT_PATH`, `DBU_PROFILE`, `DBU_CONTRACT_START`, `DBU_CONTRACT_YEARS`, `DBU_CONTRACT_AMOUNT`, `DBU_EXPECTED_ANNUAL_BURN`) and run without flags.

The generated `dashboard_payload.json` is intentionally **not** checked in (see `.gitignore`) — it bakes in customer-specific contract values and workspace IDs and should be produced per-deployment.

## Deploying

1. Edit the discount values inside `build_dashboard.py` (or `prodigy_burndown.sql`) to reflect the customer's negotiated rates.
2. Run `build_dashboard.py` with the customer's contract terms and target workspace's warehouse ID + parent path (see above).
3. Post the generated payload to the customer's workspace:
   ```bash
   databricks api post /api/2.0/lakeview/dashboards \
     --profile <your_cli_profile> \
     --json @dashboard_payload.json
   ```

## Files

```
.
├── README.md              # this file
├── prodigy_burndown.sql   # the stand-alone base query (for ad-hoc runs)
├── build_dashboard.py     # script that assembles the Lakeview JSON
└── dashboard_payload.json # assembled dashboard payload (generated; gitignored)
```
