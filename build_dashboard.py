#!/usr/bin/env python3
"""Build the pre-paid DBU burn-down Lakeview dashboard.

All workspace-specific values (warehouse, parent path, profile, output path) and
contract values (start date, term, amount, expected annual burn) are passed in
as CLI args or environment variables. Discounts are kept inline in the CORE_CTE
below — edit the VALUES list to reflect the customer's negotiated rates.

Usage:
    python3 build_dashboard.py \\
        --warehouse-id <warehouse_id> \\
        --parent-path /Users/you@example.com \\
        --contract-start 2025-01-01 \\
        --contract-years 3 \\
        --contract-amount 3000000 \\
        --expected-annual-burn 1000000 \\
        --output ./dashboard_payload.json

Environment variable equivalents (CLI args take precedence):
    DBU_WAREHOUSE_ID, DBU_PARENT_PATH, DBU_PROFILE, DBU_OUTPUT_PATH,
    DBU_CONTRACT_START, DBU_CONTRACT_YEARS, DBU_CONTRACT_AMOUNT,
    DBU_EXPECTED_ANNUAL_BURN, LAKEVIEW_BUILDER_PATH
"""
import argparse
import json
import os
import sys


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--warehouse-id", default=os.environ.get("DBU_WAREHOUSE_ID"),
                   help="Databricks SQL warehouse ID the dashboard will run against.")
    p.add_argument("--parent-path", default=os.environ.get("DBU_PARENT_PATH"),
                   help="Workspace parent folder (e.g. /Users/you@example.com).")
    p.add_argument("--profile", default=os.environ.get("DBU_PROFILE"),
                   help="Databricks CLI profile name (reserved for downstream deploy steps).")
    p.add_argument("--output", default=os.environ.get("DBU_OUTPUT_PATH", "./dashboard_payload.json"),
                   help="Path to write the generated dashboard payload JSON.")
    p.add_argument("--contract-start", default=os.environ.get("DBU_CONTRACT_START"),
                   help="Contract effective date in YYYY-MM-DD format.")
    p.add_argument("--contract-years", type=int, default=int(os.environ.get("DBU_CONTRACT_YEARS", 0)) or None,
                   help="Contract term in years.")
    p.add_argument("--contract-amount", type=float,
                   default=float(os.environ.get("DBU_CONTRACT_AMOUNT", 0)) or None,
                   help="Total contract amount in USD.")
    p.add_argument("--expected-annual-burn", type=float,
                   default=float(os.environ.get("DBU_EXPECTED_ANNUAL_BURN", 0)) or None,
                   help="Expected annual DBU burn in USD.")
    p.add_argument("--lakeview-builder-path",
                   default=os.environ.get("LAKEVIEW_BUILDER_PATH",
                                          os.path.expanduser("~/.vibe/marketplace/plugins/fe-databricks-tools/skills/databricks-lakeview-dashboard/resources")),
                   help="Filesystem path to the lakeview_builder module.")
    args = p.parse_args()
    missing = [n for n, v in [
        ("--warehouse-id", args.warehouse_id),
        ("--parent-path", args.parent_path),
        ("--contract-start", args.contract_start),
        ("--contract-years", args.contract_years),
        ("--contract-amount", args.contract_amount),
        ("--expected-annual-burn", args.expected_annual_burn),
    ] if not v]
    if missing:
        p.error(f"Missing required values: {', '.join(missing)}")
    return args


args = parse_args()
sys.path.insert(0, args.lakeview_builder_path)
from lakeview_builder import LakeviewDashboard  # noqa: E402

# Default palette — swap to match the customer's brand colors if desired.
P_BLUE   = "#1F3A93"
P_CYAN   = "#39C0ED"
P_GREEN  = "#00A972"
P_RED    = "#E53935"
P_AMBER  = "#FFAB00"
P_GREY   = "#6B7280"
PALETTE = [P_BLUE, P_CYAN, P_GREEN, P_AMBER, P_RED, P_GREY,
           "#8BCAE7", "#AB4057", "#99DDB4", "#919191", "#BF7080"]

# ---------------------------------------------------------------------------
# Shared CTE prefix so every dataset can override `contract` / `discounts` with
# dashboard parameters or keep the supplied defaults.
#
# >>> EDIT THE DISCOUNTS VALUES BELOW TO REFLECT THE CUSTOMER'S NEGOTIATED RATES <<<
# ---------------------------------------------------------------------------
CORE_CTE = f"""
WITH contract AS (
  SELECT
    DATE '{args.contract_start}'              AS contract_start,
    {args.contract_years}                      AS contract_years,
    CAST({args.contract_amount}  AS DOUBLE)   AS contract_amount_usd,
    CAST({args.expected_annual_burn}  AS DOUBLE) AS expected_annual_dbu_usd
),
discounts AS (
  SELECT * FROM (VALUES
    ('ALL_PURPOSE',0.25),('INTERACTIVE',0.25),('JOBS',0.30),('DLT',0.30),
    ('SQL',0.35),('MODEL_SERVING',0.20),('VECTOR_SEARCH',0.15),
    ('AI_FUNCTIONS',0.15),('AI_GATEWAY',0.15),('AGENT_BRICKS',0.15),
    ('AGENT_EVALUATION',0.15),('SUPERVISOR_AGENT',0.15),
    ('DATA_QUALITY_MONITORING',0.10),('LAKEHOUSE_MONITORING',0.10),
    ('PREDICTIVE_OPTIMIZATION',0.10),('LAKEFLOW_CONNECT',0.10),
    ('LAKEBASE',0.10),('DATABASE',0.10),('APPS',0.10)
  ) AS d(product_group, discount_pct)
),
priced_usage AS (
  SELECT u.usage_date, u.billing_origin_product AS product_group, u.sku_name,
         u.usage_quantity AS dbus, lp.pricing.default AS list_price_usd,
         COALESCE(d.discount_pct,0) AS discount_pct,
         u.usage_quantity*lp.pricing.default AS list_cost_usd,
         u.usage_quantity*lp.pricing.default*(1-COALESCE(d.discount_pct,0)) AS contract_cost_usd
  FROM system.billing.usage u
  JOIN system.billing.list_prices lp ON u.sku_name=lp.sku_name
    AND u.usage_date>=CAST(lp.price_start_time AS DATE)
    AND (lp.price_end_time IS NULL OR u.usage_date<CAST(lp.price_end_time AS DATE))
  LEFT JOIN discounts d ON d.product_group=u.billing_origin_product
  WHERE u.usage_unit='DBU'
    AND u.usage_date>=(SELECT contract_start FROM contract)
    AND u.usage_date<=(SELECT DATE_ADD(contract_start, contract_years*365) FROM contract)
)
"""

d = LakeviewDashboard("Pre-paid DBU Burn-down")
d.pages = []
d.add_page("Burn-down")

# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

# KPI: rolled-up single-row metrics
d.add_dataset("kpis", "Burn-down KPIs", CORE_CTE + """
SELECT
  (SELECT contract_amount_usd FROM contract)                                AS contract_amount_usd,
  (SELECT DATE_ADD(contract_start, contract_years*365) FROM contract)       AS contract_end,
  (SELECT contract_start FROM contract)                                      AS contract_start,
  (SELECT expected_annual_dbu_usd FROM contract)                            AS expected_annual_dbu_usd,
  SUM(contract_cost_usd)                                                    AS spent_to_date_usd,
  SUM(list_cost_usd)                                                        AS list_cost_to_date_usd,
  (SELECT contract_amount_usd FROM contract) - SUM(contract_cost_usd)       AS remaining_usd,
  ROUND(100.0 * SUM(contract_cost_usd) / NULLIF((SELECT contract_amount_usd FROM contract),0), 2) AS pct_consumed,
  ROUND(SUM(contract_cost_usd) / GREATEST(DATEDIFF(MAX(usage_date), MIN(usage_date))+1, 1) * 30, 2) AS avg_monthly_burn_usd,
  MAX(usage_date)                                                            AS latest_usage_date,
  MIN(usage_date)                                                            AS earliest_usage_date
FROM priced_usage
""")

# Daily cumulative: for burn-down line + expected-budget line
d.add_dataset("cum", "Daily cumulative burn vs expected (long)", CORE_CTE + """
, daily AS (
  SELECT usage_date, SUM(contract_cost_usd) AS daily_spend
  FROM priced_usage GROUP BY usage_date
),
calendar AS (
  SELECT explode(sequence(
    (SELECT contract_start FROM contract),
    LEAST((SELECT DATE_ADD(contract_start, contract_years*365) FROM contract), CURRENT_DATE()),
    INTERVAL 1 DAY
  )) AS dt
),
filled AS (
  SELECT c.dt AS usage_date, COALESCE(d.daily_spend, 0) AS daily_spend
  FROM calendar c LEFT JOIN daily d ON d.usage_date = c.dt
),
cumulative AS (
  SELECT usage_date,
         SUM(daily_spend) OVER (ORDER BY usage_date) AS cumulative_spend,
         (SELECT contract_amount_usd FROM contract) *
           DATEDIFF(usage_date, (SELECT contract_start FROM contract)) /
           ((SELECT contract_years FROM contract) * 365.0) AS expected_spend,
         (SELECT contract_amount_usd FROM contract) AS contract_amount
  FROM filled
)
-- Long format: one row per (date, series) so Lakeview can render both lines
SELECT usage_date, 'Actual contract spend' AS series, cumulative_spend AS value_usd
FROM cumulative
UNION ALL
SELECT usage_date, 'Expected linear burn'   AS series, expected_spend    AS value_usd
FROM cumulative
UNION ALL
SELECT usage_date, 'Contract budget'        AS series, contract_amount   AS value_usd
FROM cumulative
""")

# Monthly stacked bar by product group
d.add_dataset("monthly", "Monthly spend by product group", CORE_CTE + """
SELECT DATE_TRUNC('MONTH', usage_date) AS month,
       product_group,
       ROUND(SUM(contract_cost_usd), 2) AS contract_cost_usd,
       ROUND(SUM(dbus), 1) AS dbus
FROM priced_usage
GROUP BY 1, 2
ORDER BY 1
""")

# Product-group spend to date (bar)
d.add_dataset("by_sku", "Spend by product group", CORE_CTE + """
SELECT product_group,
       ROUND(SUM(dbus), 1) AS dbus,
       ROUND(SUM(list_cost_usd), 2) AS list_cost_usd,
       ROUND(SUM(contract_cost_usd), 2) AS contract_cost_usd,
       ROUND(AVG(discount_pct) * 100, 1) AS avg_discount_pct,
       ROUND(100.0 * SUM(contract_cost_usd) / SUM(SUM(contract_cost_usd)) OVER (), 2) AS pct_of_total
FROM priced_usage
GROUP BY 1
ORDER BY contract_cost_usd DESC
""")

# Detailed table
d.add_dataset("detail", "Detail by product group & SKU", CORE_CTE + """
SELECT product_group, sku_name,
       ROUND(SUM(dbus), 1) AS dbus,
       ROUND(AVG(list_price_usd), 4) AS avg_list_price,
       ROUND(AVG(discount_pct)*100, 1) AS discount_pct,
       ROUND(SUM(list_cost_usd), 2) AS list_cost_usd,
       ROUND(SUM(contract_cost_usd), 2) AS contract_cost_usd
FROM priced_usage
GROUP BY 1, 2
ORDER BY contract_cost_usd DESC
LIMIT 100
""")

# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

# Row 1 — KPI tiles (6-wide grid)
d.add_counter("kpis", "contract_amount_usd", "SUM", "Contract Amount ($)",
              position={"x": 0, "y": 0, "width": 1, "height": 3})
d.add_counter("kpis", "spent_to_date_usd", "SUM", "Contract $ Spent to Date",
              position={"x": 1, "y": 0, "width": 1, "height": 3})
d.add_counter("kpis", "remaining_usd", "SUM", "Contract $ Remaining",
              position={"x": 2, "y": 0, "width": 1, "height": 3})
d.add_counter("kpis", "pct_consumed", "SUM", "% of Contract Consumed",
              position={"x": 3, "y": 0, "width": 1, "height": 3})
d.add_counter("kpis", "avg_monthly_burn_usd", "SUM", "Avg Monthly Burn ($)",
              position={"x": 4, "y": 0, "width": 1, "height": 3})
d.add_counter("kpis", "list_cost_to_date_usd", "SUM", "List $ To Date (pre-discount)",
              position={"x": 5, "y": 0, "width": 1, "height": 3})

# Row 2 — single burn-down chart: Actual vs Expected vs Contract budget
d.add_line_chart("cum", "usage_date", "value_usd", "SUM",
                 title="Contract $ Burn-down — Actual vs. Expected vs. Budget",
                 color_field="series",
                 position={"x": 0, "y": 3, "width": 6, "height": 7})

# Row 3 — monthly stacked bar (spend by product group)
d.add_bar_chart("monthly", "month", "contract_cost_usd", "SUM",
                title="Monthly Contract $ Spend by Product Group",
                color_field="product_group",
                position={"x": 0, "y": 10, "width": 4, "height": 6},
                colors=PALETTE, show_labels=False)

# Row 3 — spend share by product group
d.add_bar_chart("by_sku", "product_group", "contract_cost_usd", "SUM",
                title="Contract $ by Product Group",
                position={"x": 4, "y": 10, "width": 2, "height": 6},
                sort_descending=True, colors=[P_BLUE])

# Row 4 — detail table
d.add_table("detail",
            columns=[
              {"field": "product_group", "title": "Product Group", "type": "string"},
              {"field": "sku_name", "title": "SKU", "type": "string"},
              {"field": "dbus", "title": "DBUs", "type": "float", "format": "#,##0"},
              {"field": "avg_list_price", "title": "Avg List Price ($)", "type": "float", "format": "$#,##0.0000"},
              {"field": "discount_pct", "title": "Discount (%)", "type": "float", "format": "0.0%"},
              {"field": "list_cost_usd", "title": "List Cost ($)", "type": "float", "format": "$#,##0"},
              {"field": "contract_cost_usd", "title": "Contract Cost ($)", "type": "float", "format": "$#,##0"},
            ],
            title="Detail by SKU (top 100 by spend)",
            position={"x": 0, "y": 16, "width": 6, "height": 8})

# ---------------------------------------------------------------------------
# Emit payload
# ---------------------------------------------------------------------------
payload = {
    "display_name": d.name,
    "warehouse_id": args.warehouse_id,
    "parent_path": args.parent_path,
    "serialized_dashboard": d.to_json()
}
with open(args.output, "w") as f:
    json.dump(payload, f)
print(f"Wrote payload to {args.output} ({len(payload['serialized_dashboard'])} bytes)")
print(f"Datasets: {[ds['name'] for ds in d.datasets]}")
