-- ============================================================================
-- PRODIGY — Pre-paid DBU Burn-down (base query)
--
-- Edit the two CTEs at the top (`contract`, `discounts`) with Prodigy's
-- negotiated terms. Everything else auto-computes from system.billing.
--
-- Assumes the caller has SELECT on system.billing.usage and
-- system.billing.list_prices (enabled by default for workspace admins).
-- ============================================================================

WITH contract AS (
  SELECT
    DATE '2025-01-01'        AS contract_start,
    3                         AS contract_years,
    CAST(3000000  AS DOUBLE) AS contract_amount_usd,      -- initial $ signed
    CAST(1000000  AS DOUBLE) AS expected_annual_dbu_usd   -- expected yearly burn
),

-- Per-product-group discount off list price.
-- 0.00 = no discount, 0.30 = 30% off.
-- Anything not listed defaults to 0 via the LEFT JOIN below.
discounts AS (
  SELECT * FROM (VALUES
    ('ALL_PURPOSE',             0.25),
    ('INTERACTIVE',             0.25),
    ('JOBS',                    0.30),
    ('DLT',                     0.30),
    ('SQL',                     0.35),
    ('MODEL_SERVING',           0.20),
    ('VECTOR_SEARCH',           0.15),
    ('AI_FUNCTIONS',            0.15),
    ('AI_GATEWAY',              0.15),
    ('AGENT_BRICKS',            0.15),
    ('AGENT_EVALUATION',        0.15),
    ('SUPERVISOR_AGENT',        0.15),
    ('DATA_QUALITY_MONITORING', 0.10),
    ('LAKEHOUSE_MONITORING',    0.10),
    ('PREDICTIVE_OPTIMIZATION', 0.10),
    ('LAKEFLOW_CONNECT',        0.10),
    ('LAKEBASE',                0.10),
    ('DATABASE',                0.10),
    ('APPS',                    0.10)
  ) AS d(product_group, discount_pct)
),

priced_usage AS (
  SELECT
    u.usage_date,
    u.billing_origin_product                       AS product_group,
    u.sku_name,
    u.usage_quantity                               AS dbus,
    lp.pricing.default                             AS list_price_usd,
    COALESCE(d.discount_pct, 0)                    AS discount_pct,
    u.usage_quantity * lp.pricing.default                            AS list_cost_usd,
    u.usage_quantity * lp.pricing.default * (1 - COALESCE(d.discount_pct, 0))
                                                   AS contract_cost_usd
  FROM system.billing.usage u
  JOIN system.billing.list_prices lp
    ON u.sku_name = lp.sku_name
   AND u.usage_date >= CAST(lp.price_start_time AS DATE)
   AND (lp.price_end_time IS NULL OR u.usage_date < CAST(lp.price_end_time AS DATE))
  LEFT JOIN discounts d ON d.product_group = u.billing_origin_product
  WHERE u.usage_unit = 'DBU'
    AND u.usage_date >= (SELECT contract_start FROM contract)
    AND u.usage_date <= (SELECT DATE_ADD(contract_start, contract_years*365) FROM contract)
)

SELECT
  p.usage_date,
  p.product_group,
  p.sku_name,
  p.dbus,
  p.list_price_usd,
  p.discount_pct,
  p.list_cost_usd,
  p.contract_cost_usd,
  c.contract_amount_usd,
  c.contract_years,
  c.expected_annual_dbu_usd,
  c.contract_start,
  DATE_ADD(c.contract_start, c.contract_years*365) AS contract_end
FROM priced_usage p
CROSS JOIN contract c;
