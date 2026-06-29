# CLO Bloomberg Data Needed

## Why This Exists

This note makes the Chapter 4 Bloomberg air-gap route decision-complete. It
states exactly what the Bloomberg-connected machine should export for loan-level
collateral valuation, `PD`, `LGD`, trigger history, and the inputs used to
calibrate `rho`.

The workbook still resolves Bloomberg-specific fields into the normalized
Chapter 4 contract before the files are transferred to the analysis machine. The
important change is that `fact_clo_collateral_position.csv` is now a valuation
tape, not merely a balance / PD / CPR / LGD tape.

## Air-Gap Package Layout

Use one workbook on the Bloomberg-connected machine with these tabs:

- `README`
- `field_dictionary`
- `tranche_export`
- `collateral_export`
- `manager_export`
- optional `default_export`
- optional `recovery_export`
- optional `cohort_export`
- optional `stress_export`

Required values-only exports:

- `bbg_clo_tranche_export.csv`
- `bbg_loan_collateral_export.csv`
- `field_dictionary.csv`

Preferred values-only exports:

- `bbg_clo_manager_export.csv`
- `bbg_clo_cohort_export.csv`
- `scenario_clo_stress.csv`

Optional values-only exports used when Bloomberg coverage exists:

- `bbg_loan_default_export.csv`
- `bbg_loan_recovery_export.csv`

## Exact Export Files

### `bbg_clo_tranche_export.csv`

- Status: required
- Grain: one row per `deal_id x tranche`
- Canonical columns:
  - `deal_id`
  - `tranche`
  - `attach`
  - `detach`
  - `coupon_bps`
  - `cusip`
  - `figi`
  - `manager_name`
  - `source_family`
  - optional `trigger_level`
- Pull from Bloomberg:
  - representative deal and tranche stack from `PREL`
  - static tranche identifiers and terms
  - direct trigger level only when Bloomberg exposes a deal-level static
    threshold that maps cleanly to Chapter 4 `trigger_level`
- Use:
  - build `dim_clo_tranche.csv`
  - provide direct `trigger_level` only when no manager-report backfill is
    required

### `bbg_loan_collateral_export.csv`

- Status: required
- Grain: one row per active collateral position as of the run date
- Canonical columns:
  - `deal_id`
  - `as_of_date`
  - `loan_id`
  - `loan_identifier`
  - `sector`
  - `current_balance`
  - `annual_pd`
  - `annual_cpr`
  - `lgd`
  - `rating`
  - `market_price`
  - `coupon_spread_bps`
  - `reference_rate`
  - `coupon_floor`
  - `maturity_years`
  - `discount_margin_bps`
  - `source_family`
- Pull from Bloomberg:
  - collateral universe for the representative deal
  - stable loan or obligor identifier
  - issuer or facility name
  - sector or industry bucket
  - current par or balance
  - current mid, evaluated, or BVAL-style loan mark when available
  - coupon spread or margin over the floating-rate index
  - current reference rate and contractual floor
  - remaining term or maturity date converted to years
  - discount margin, yield spread, or comparable valuation spread when available
  - one 1Y point-in-time default probability field
  - one annual CPR field only if your workflow derives it from Bloomberg
    history; otherwise populate an explicit workbook-side overlay
  - one expected recovery or recovery-style field that can be converted to
    `lgd = 1 - expected_recovery`
- Use:
  - build `fact_clo_collateral_position.csv`
  - value the collateral loan by loan before tranche allocation
  - supply `annual_pd`, `annual_cpr`, `lgd`, coupon, maturity, and at least one
    valuation anchor (`market_price` or `discount_margin_bps`) directly into the
    live pool

### `bbg_clo_manager_export.csv`

- Status: preferred
- Grain: one row per `deal_id x report_date x tranche`
- Canonical columns:
  - `deal_id`
  - `report_date`
  - `tranche`
  - `oc_ratio`
  - `oc_trigger_level`
  - `ic_ratio`
  - `ccc_bucket_pct`
  - `source_family`
- Pull from Bloomberg:
  - `TRIG` or equivalent CLO trigger and manager-report history
  - monthly report history for each tranche
- History window:
  - 24 monthly reports minimum
  - 36 monthly reports preferred
- Use:
  - build `fact_clo_manager_report.csv`
  - backfill `trigger_level` from the latest `oc_trigger_level` when
    `bbg_clo_tranche_export.csv` does not carry a direct trigger

### `bbg_clo_cohort_export.csv`

- Status: preferred when you want calibrated `rho`
- Grain: one row per `deal_id x year x cohort_key`
- Canonical columns:
  - `deal_id`
  - `year`
  - `cohort_key`
  - `cohort_size`
  - `defaults`
  - `annual_pd`
  - `source_family`
- Cohort construction:
  - `cohort_key = rating_bucket__sector`
  - `cohort_size` is the number of obligors at the start of the year
  - `defaults` is the number of obligors defaulting during that year
  - `annual_pd` is the start-of-year average 1Y PD for that cohort
- Raw Bloomberg inputs needed to build this workbook tab:
  - obligor identifier
  - cohort year
  - sector
  - rating bucket
  - start-of-year 1Y PD
  - default flag or default event date during the year
- Use:
  - build `agg_clo_cohort_default.csv`
  - calibrate `rho` from default-rate dispersion in the Chapter 4 runtime

### `bbg_loan_default_export.csv`

- Status: optional but preferred when expected recovery coverage is weak
- Grain: one row per `deal_id x loan_id x default_date`
- Canonical columns:
  - `deal_id`
  - `loan_id`
  - `default_date`
  - `defaulted_balance`
  - `source_family`
- Use:
  - build `fact_clo_default_event.csv`
  - support realized-recovery LGD estimation when paired with recovery rows

### `bbg_loan_recovery_export.csv`

- Status: optional but preferred when expected recovery coverage is weak
- Grain: one row per `deal_id x loan_id x recovery_date`
- Canonical columns:
  - `deal_id`
  - `loan_id`
  - `recovery_date`
  - `recovered_balance`
  - `recovery_rate`
  - `source_family`
- Use:
  - build `fact_clo_recovery_event.csv`
  - support realized-recovery LGD estimation

### `scenario_clo_stress.csv`

- Status: preferred in all air-gap packages
- Canonical columns:
  - `scenario`
  - `rho`
  - `base_rho`
  - `rho_multiplier`
  - `pd_multiplier`
  - `cpr_multiplier`
  - `lgd_addon`
  - `discount_rate`
  - `source_family`
  - `pack_label`
- Two valid modes:
  - calibrated mode: pair this file with `bbg_clo_cohort_export.csv` and use
    low/high `rho_multiplier` rows
  - explicit mode: omit the cohort export and supply explicit `rho` values for
    `low` and `high`

### `field_dictionary.csv`

- Status: required
- Schema:
  - `worksheet`
  - `output_file`
  - `canonical_column`
  - `bloomberg_function`
  - `bloomberg_field`
  - `security_or_screen`
  - `notes`
- Rules:
  - write one row for every exported canonical column
  - validate every mnemonic in `FLDS`
  - record whether a value is facility-level, issuer-level, screen-derived,
    median-filled, or explicit overlay
  - for `bbg_clo_cohort_export.csv`, record whether the universe is deal-only
    or broad proxy

## Parameter Source Rules

### `PD`

Use one 1Y point-in-time Bloomberg default risk field as the primary source for
`annual_pd`.

Source order:

1. Facility-level or obligor-level 1Y PD mapped directly to each active loan
   row.
2. Issuer-level 1Y PD when facility mapping is not complete.
3. Sector x rating-bucket median PD computed from Bloomberg-covered names in the
   same workbook.
4. Explicit workbook-side overlay when Bloomberg coverage is still incomplete.

Documentation rule:

- Every non-primary fill must be identified in `field_dictionary.csv`.

### `LGD`

Use one Bloomberg-backed recovery-style field as the primary source for `lgd`.

Source order:

1. Expected recovery or recovery-rating style input converted to
   `lgd = 1 - expected_recovery`.
2. Realized LGD computed from `bbg_loan_default_export.csv` and
   `bbg_loan_recovery_export.csv`.
3. Seniority x sector median LGD computed from Bloomberg-covered names.
4. Explicit workbook-side overlay when Bloomberg coverage is still incomplete.

Documentation rule:

- Record the exact recovery definition in `field_dictionary.csv`.

### Trigger history

Use Bloomberg CLO trigger or manager-report history as the primary source for
tranche warning thresholds.

Source order:

1. Direct `trigger_level` in `bbg_clo_tranche_export.csv` when Bloomberg exposes
   a static threshold that maps cleanly to the Chapter 4 field.
2. Latest `oc_trigger_level` from `bbg_clo_manager_export.csv`.
3. Explicit deal-doc or trustee value entered manually in the workbook and
   marked clearly in `field_dictionary.csv`.

Do not invent a subordinated-note warning level inside the Bloomberg file. If it
is not observable in Bloomberg, use a documented deal-doc or trustee value. If
no observable or documented value exists, keep the run blocked rather than
silently proxying it.

### `CPR`

Bloomberg does not give Chapter 4 one universally clean forward `CPR` field.
The collateral export must still populate `annual_cpr`, but it remains one of:

- a derived realized-paydown proxy built in the workbook from Bloomberg history
- an explicit analyst overlay

Keep that status disclosed in the `notes` column of `field_dictionary.csv`.

### Collateral valuation fields

Chapter 4 now values collateral before it values tranches. A licensed Bloomberg
run is therefore blocked unless the collateral export contains enough fields to
construct loan-level discounted cash flows.

Required for licensed Bloomberg/Intex/Trepp runs:

- `coupon_spread_bps`
- `maturity_years`
- at least one of `market_price` or `discount_margin_bps`

Recommended:

- `rating`
- `reference_rate`
- `coupon_floor`
- both `market_price` and `discount_margin_bps` so the output can compare model
  DCF price to the observed or evaluated mark

If Bloomberg supplies a maturity date rather than `maturity_years`, convert it
in the workbook before export and document the conversion in `field_dictionary`.
If Bloomberg supplies an all-in coupon instead of spread plus index/floor,
convert it to the closest equivalent `coupon_spread_bps` convention and record
the mapping.

## Rho Calibration Rules

`rho` is not directly observed from Bloomberg. Chapter 4 calibrates it from
cohort default-rate dispersion when `agg_clo_cohort_default.csv` is populated.

Primary calibration universe:

- use the deal's own current and historical collateral names when they are
  available and complete

Completeness test for deal-only history:

- at least 5 annual observation years
- at least 20 cohort rows after grouping
- average cohort size of at least 25 obligors
- at least 10 realized defaults across the full panel

Fallback calibration universe:

- if the deal-only panel fails the completeness test, build a broader Bloomberg
  leveraged-loan proxy universe aligned to the deal's region, seniority, sector
  mix, and rating mix

Historical window:

- trailing 7 full calendar years preferred
- trailing 5 full calendar years minimum

Export rule:

- export only the aggregated annual cohort panel in `bbg_clo_cohort_export.csv`
- keep raw Bloomberg cohort-building logic on the Bloomberg machine

Failure rule:

- if neither the deal-only history nor the broad proxy universe yields a valid
  cohort panel, do not claim calibrated `rho`
- instead, omit `bbg_clo_cohort_export.csv`, supply explicit `low` and `high`
  `rho` values in `scenario_clo_stress.csv`, and disclose that `rho` remains an
  analyst overlay

## Stage Command

Stage the values-only package on the analysis machine with the current Chapter 4
CLI:

```powershell
python stage_actual_clo_contract.py `
  --route bloomberg_market_observed `
  --deal-id <DEAL_ID> `
  --output-dir D:\data\CLO\Chapter4\live_contract `
  --tranche-export D:\data\CLO\Chapter4\raw\bbg_clo_tranche_export.csv `
  --collateral-export D:\data\CLO\Chapter4\raw\bbg_loan_collateral_export.csv `
  --manager-export D:\data\CLO\Chapter4\raw\bbg_clo_manager_export.csv `
  --cohort-export D:\data\CLO\Chapter4\raw\bbg_clo_cohort_export.csv `
  --default-export D:\data\CLO\Chapter4\raw\bbg_loan_default_export.csv `
  --recovery-export D:\data\CLO\Chapter4\raw\bbg_loan_recovery_export.csv `
  --stress-export D:\data\CLO\Chapter4\raw\scenario_clo_stress.csv `
  --field-dictionary-export D:\data\CLO\Chapter4\raw\field_dictionary.csv `
  --as-of-date 2026-03-31 `
  --source-url "Bloomberg Terminal air-gap workbook export"
```

If no valid cohort panel exists, omit `--cohort-export` and keep
`scenario_clo_stress.csv` in explicit-rho mode.

## What Still Remains An Overlay

- `annual_cpr` unless the workbook derives it from a documented Bloomberg
  paydown history
- `annual_pd` for any rows that still require explicit workbook-side fill after
  Bloomberg fallbacks are exhausted
- `lgd` for any rows that still require explicit workbook-side fill after
  Bloomberg fallbacks are exhausted
- `discount_margin_bps` or `market_price` only when Bloomberg coverage is
  incomplete; licensed runs must disclose which valuation anchor is observed and
  which is inferred
- `rho` whenever a valid cohort panel cannot be built
- any subordinated trigger level that is not directly observable in Bloomberg
  and has no documented deal-doc or trustee fallback

## Related Workflow Notes

- [BLOOMBERG_AIRGAP_PLAYBOOK.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter%204/Correlation%20and%20Tail%20Risk%20in%20CLO%20Tranches/BLOOMBERG_AIRGAP_PLAYBOOK.md)
- [DATA_CARD.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter%204/Correlation%20and%20Tail%20Risk%20in%20CLO%20Tranches/DATA_CARD.md)
- [python/stage_actual_clo_contract.py](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter%204/Correlation%20and%20Tail%20Risk%20in%20CLO%20Tranches/python/stage_actual_clo_contract.py)
