-- ============================================================================
-- Pre-paid DBU Burn-down (base query)
--
-- >>> EDIT THE TWO CTEs AT THE TOP (`contract`, `discounts`) WITH YOUR <<<
-- >>> NEGOTIATED CONTRACT TERMS BEFORE RUNNING.                          <<<
--
-- Everything else auto-computes from system.billing.
--
-- Assumes the caller has SELECT on system.billing.usage and
-- system.billing.list_prices (enabled by default for workspace admins).
-- ============================================================================

WITH contract AS (
  -- >>> REPLACE THESE VALUES WITH YOUR CONTRACT TERMS <<<
  SELECT
    DATE '<contract_start_date>'                       AS contract_start,         -- YYYY-MM-DD, contract effective date
    <contract_term_in_years>                            AS contract_years,         -- e.g. 3
    CAST(<total_contract_amount_usd>  AS DOUBLE)        AS contract_amount_usd,    -- e.g. 3000000
    CAST(<expected_annual_burn_usd>   AS DOUBLE)        AS expected_annual_dbu_usd -- e.g. 1000000
),

-- >>> REPLACE THESE DISCOUNT VALUES WITH YOUR NEGOTIATED RATES <<<
-- Per-product-group discount off list price.
-- 0.00 = no discount, 0.30 = 30% off.
-- Anything not listed defaults to 0 via the LEFT JOIN below.
discounts AS (
  SELECT * FROM (VALUES
    ('ALL_PURPOSE',             0.00),
    ('INTERACTIVE',             0.00),
    ('JOBS',                    0.00),
    ('DLT',                     0.00),
    ('SQL',                     0.00),
    ('MODEL_SERVING',           0.00),
    ('VECTOR_SEARCH',           0.00),
    ('AI_FUNCTIONS',            0.00),
    ('AI_GATEWAY',              0.00),
    ('AGENT_BRICKS',            0.00),
    ('AGENT_EVALUATION',        0.00),
    ('SUPERVISOR_AGENT',        0.00),
    ('DATA_QUALITY_MONITORING', 0.00),
    ('LAKEHOUSE_MONITORING',    0.00),
    ('PREDICTIVE_OPTIMIZATION', 0.00),
    ('LAKEFLOW_CONNECT',        0.00),
    ('LAKEBASE',                0.00),
    ('DATABASE',                0.00),
    ('APPS',                    0.00)
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
