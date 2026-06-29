# CLO Bloomberg Real Data Download And Calibration Plan

## Purpose

This plan describes how to replace the synthetic Bloomberg-compatible input tape in `4.1 Correlation and Tail Risk in CLO Tranches` with a real Bloomberg-backed CLO case study.

The goal is not to redesign the model. The goal is to:

- identify one real CLO with usable Bloomberg coverage,
- export loan-level collateral, tranche, manager-report, and analytics data,
- run Bloomberg's own CLO and loan analytics on the selected deal,
- normalize the exported files into the Chapter 4 live contract,
- run the existing Python and MATLAB implementations,
- reconcile our outputs against Bloomberg's outputs before updating the manuscript.

Until this workflow is completed, the 4.1 example remains a synthetic Bloomberg-compatible code-path demonstration.

## Existing 4.1 Implementation

The current 4.1 implementation already has a live-data route. This plan should work with that route rather than creating a separate one.

Relevant files:

```text
D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\BLOOMBERG_AIRGAP_PLAYBOOK.md
D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\CLO-Bloomberg-Data-Needed.md
D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\live_contract_template\README.md
D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\python\stage_actual_clo_contract.py
D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\python\CLO.py
D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\Matlab\CLO.m
```

Canonical data staging roots:

```text
D:\data\CLO\Chapter4\raw
D:\data\CLO\Chapter4\live_contract
D:\data\CLO\Chapter4\bloomberg_analytics
D:\data\CLO\Chapter4\reconciliation
```

Do not store licensed Bloomberg data in the public repository. Raw licensed exports, normalized live contracts, and reconciliation workbooks belong under `D:\data\CLO\Chapter4`.

## Workflow Summary

| Step | Owner | Output |
| --- | --- | --- |
| 1. Select a real CLO | Bloomberg operator | `deal_selection_memo.md` |
| 2. Build Bloomberg workbook | Bloomberg operator | values-only workbook with documented fields |
| 3. Export normalized CSVs | Bloomberg operator | `D:\data\CLO\Chapter4\raw\*.csv` |
| 4. Run Bloomberg analytics | Bloomberg operator | `D:\data\CLO\Chapter4\bloomberg_analytics\*.csv` |
| 5. Stage live contract | Analysis machine | `D:\data\CLO\Chapter4\live_contract\*.csv` |
| 6. Run Python model | Analysis machine | Python figure and CSV output pack |
| 7. Run MATLAB model | Analysis machine | MATLAB figure and table output pack |
| 8. Reconcile against Bloomberg | Analysis machine | reconciliation workbook and markdown report |
| 9. Update manuscript only if accepted | Book2 editor | revised 4.1 narrative and comment notes |

## Deal Selection

Choose one representative CLO before pulling detailed data. The deal should be concrete enough that another analyst can reproduce the Bloomberg workflow.

Selection criteria:

| Criterion | Requirement |
| --- | --- |
| Deal type | Broadly syndicated loan CLO, not middle-market or CBO unless intentionally selected |
| Currency | USD preferred |
| Status | Active or recently active with current collateral available |
| Collateral coverage | Loan-level collateral list available in Bloomberg |
| Tranche coverage | Current tranche stack, coupons, balances, ratings, and prices/spreads available |
| Manager-report coverage | OC/IC triggers, CCC bucket, WARF or equivalent diagnostics preferred |
| Analytics availability | Bloomberg can produce tranche price/spread/yield and collateral analytics |
| Data sufficiency | At least `coupon_spread_bps`, maturity, balance, rating, sector, `market_price` or `discount_margin_bps`, and enough PD/LGD/CPR information to populate the live contract |

Avoid deals with sparse collateral coverage, missing tranche terms, unusual bespoke structures, or obvious entitlement gaps unless the purpose is a negative data audit.

Create a short `deal_selection_memo.md` with:

- selected deal name,
- Bloomberg deal identifier or screen path,
- manager,
- vintage,
- currency,
- collateral count,
- tranche count,
- as-of date,
- reason selected,
- known entitlement or coverage gaps.

## Bloomberg Workbook

Use one workbook on the Bloomberg-connected machine. Keep raw Bloomberg formulas and entitlement-dependent logic on that machine. Export only values-only CSVs.

Required tabs:

| Tab | Purpose |
| --- | --- |
| `README` | Deal, as-of date, operator, export timestamp, and instructions |
| `field_dictionary` | Mapping from Bloomberg fields and functions to canonical columns |
| `tranche_export` | Tranche stack and deal terms |
| `collateral_export` | Loan-level collateral tape |
| `manager_export` | Trigger and manager-report diagnostics |
| `bloomberg_analytics` | Bloomberg's own deal/tranche/collateral analytics outputs |

Preferred tabs:

| Tab | Purpose |
| --- | --- |
| `cohort_export` | Cohort default panel for asset-correlation calibration |
| `default_export` | Loan default events |
| `recovery_export` | Loan recovery events |
| `stress_export` | Scenario assumptions for low/high dependence and stress tests |

The workbook may use Bloomberg functions such as `BDP`, `BDH`, `BDS`, `BQL`, and Bloomberg screen exports, but the exported CSVs must contain canonical values, not Bloomberg formulas.

## Required Export Files

Export these values-only CSVs into:

```text
D:\data\CLO\Chapter4\raw
```

Required:

| File | Required | Purpose |
| --- | --- | --- |
| `bbg_clo_tranche_export.csv` | yes | Tranche terms and identifiers |
| `bbg_loan_collateral_export.csv` | yes | Loan-level collateral valuation tape |
| `field_dictionary.csv` | yes | Audit trail for every exported field |
| `bloomberg_analytics_summary.csv` | yes | Bloomberg benchmark outputs for reconciliation |

Preferred:

| File | Required | Purpose |
| --- | --- | --- |
| `bbg_clo_manager_export.csv` | preferred | OC/IC triggers and manager-report diagnostics |
| `bbg_clo_cohort_export.csv` | preferred | Rho calibration from default-rate dispersion |
| `scenario_clo_stress.csv` | preferred | Low/high and stress scenario definitions |

Optional:

| File | Required | Purpose |
| --- | --- | --- |
| `bbg_loan_default_export.csv` | optional | Realized default event support |
| `bbg_loan_recovery_export.csv` | optional | Realized recovery and LGD support |
| `bloomberg_tranche_cashflow_export.csv` | optional | Bloomberg tranche cash-flow benchmark |
| `bloomberg_collateral_cashflow_export.csv` | optional | Bloomberg collateral cash-flow benchmark |

## Core Data Dictionary

### Deal Metadata

| Canonical field | Required | Notes |
| --- | --- | --- |
| `deal_id` | yes | Stable local identifier used across every export |
| `deal_name` | yes | Bloomberg-visible deal name |
| `manager_name` | yes | CLO collateral manager |
| `vintage_year` | preferred | Deal vintage |
| `currency` | yes | USD preferred |
| `as_of_date` | yes | Date of collateral and analytics pull |
| `bloomberg_deal_identifier` | yes | Bloomberg identifier or screen reference |
| `source_family` | yes | Use `bloomberg_clo` or more specific Bloomberg source family |

### Tranche Export

Target file:

```text
bbg_clo_tranche_export.csv
```

Grain: one row per `deal_id x tranche`.

| Canonical field | Required | Notes |
| --- | --- | --- |
| `deal_id` | yes | Must match collateral export |
| `tranche` | yes | Class or note name |
| `attach` | yes | Attachment point as decimal share of collateral par |
| `detach` | yes | Detachment point as decimal share of collateral par |
| `coupon_bps` | preferred | Tranche coupon or spread |
| `cusip` | preferred | Security identifier |
| `figi` | preferred | Bloomberg global identifier when available |
| `manager_name` | preferred | Useful for audit |
| `trigger_level` | preferred | Direct static threshold only if observable |
| `source_family` | yes | Usually `bloomberg_clo` |

### Loan-Level Collateral Export

Target file:

```text
bbg_loan_collateral_export.csv
```

Grain: one row per active collateral position as of the run date.

| Canonical field | Required | Notes |
| --- | --- | --- |
| `deal_id` | yes | Must match tranche export |
| `as_of_date` | yes | Collateral snapshot date |
| `loan_id` | yes | Stable loan/facility/obligor identifier |
| `loan_identifier` | yes | Issuer or facility name |
| `sector` | yes | Industry/sector bucket |
| `current_balance` | yes | Current par or principal balance |
| `rating` | preferred | Facility, issuer, or composite rating |
| `market_price` | one of price or DM required | Current mid, evaluated, or BVAL-style price |
| `discount_margin_bps` | one of price or DM required | Discount margin or yield spread |
| `coupon_spread_bps` | yes | Margin over floating index |
| `reference_rate` | preferred | Current base rate used for coupon calculation |
| `coupon_floor` | preferred | Contractual floor, if any |
| `maturity_years` | yes | Remaining maturity converted to years |
| `annual_pd` | yes | One-year point-in-time default probability or documented fallback |
| `annual_cpr` | yes | Forward CPR, realized paydown proxy, or documented overlay |
| `lgd` | yes | Loss-given-default as decimal |
| `source_family` | yes | Usually `bloomberg_clo` or `bloomberg_syndicated_loans` |

Licensed runs are blocked unless `coupon_spread_bps`, `maturity_years`, and at least one valuation anchor, `market_price` or `discount_margin_bps`, are present.

### Manager And Trigger Export

Target file:

```text
bbg_clo_manager_export.csv
```

Grain: one row per `deal_id x report_date x tranche`.

| Canonical field | Required | Notes |
| --- | --- | --- |
| `deal_id` | yes | Must match tranche export |
| `report_date` | yes | Manager report date |
| `tranche` | yes | Tranche name |
| `oc_ratio` | preferred | Overcollateralization ratio |
| `oc_trigger_level` | preferred | OC threshold |
| `ic_ratio` | preferred | Interest coverage ratio |
| `ccc_bucket_pct` | preferred | CCC concentration |
| `source_family` | yes | Usually `bloomberg_clo` |

Use at least 24 months of manager-report history if available; 36 months is preferred.

### Cohort Default Export

Target file:

```text
bbg_clo_cohort_export.csv
```

Grain: one row per `deal_id x year x cohort_key`.

| Canonical field | Required | Notes |
| --- | --- | --- |
| `deal_id` | yes | Must match deal |
| `year` | yes | Calendar year |
| `cohort_key` | yes | Recommended format: `rating_bucket__sector` |
| `cohort_size` | yes | Start-of-year obligor count |
| `defaults` | yes | Defaults during year |
| `annual_pd` | yes | Start-of-year average one-year PD |
| `source_family` | yes | Usually `bloomberg_clo` or `bloomberg_syndicated_loans` |

Use this file only if it passes the rho calibration sufficiency test:

- at least 5 annual observation years,
- at least 20 cohort rows,
- average cohort size of at least 25 obligors,
- at least 10 realized defaults across the panel.

If the selected deal does not have enough history, build a broader Bloomberg leveraged-loan proxy universe aligned to the deal's rating, sector, seniority, and region mix.

### Bloomberg Analytics Summary

Target file:

```text
bloomberg_analytics_summary.csv
```

Grain: one row per benchmark metric, or one row per `deal_id x tranche x metric` for tranche-level outputs.

Required columns:

| Field | Required | Notes |
| --- | --- | --- |
| `deal_id` | yes | Must match other exports |
| `as_of_date` | yes | Analytics date |
| `object_type` | yes | `deal`, `collateral`, `tranche`, or `scenario` |
| `object_id` | yes | Deal ID, loan ID, or tranche name |
| `metric` | yes | Bloomberg output name |
| `value` | yes | Numeric or text value |
| `unit` | preferred | Price, bps, percent, years, dollars, etc. |
| `bloomberg_function` | yes | Screen/function used |
| `bloomberg_field` | preferred | Field mnemonic when applicable |
| `notes` | preferred | Assumptions, screen path, or caveat |

Minimum Bloomberg benchmark metrics:

| Area | Metrics |
| --- | --- |
| Collateral | collateral par, average price, weighted average spread, weighted average maturity, rating mix, sector mix |
| Loan valuation | market/evaluated price, discount margin, spread, floor, maturity, PD, LGD/recovery |
| Tranches | price, spread/yield, WAL/duration if available, rating, balance, coupon |
| Deal tests | OC ratio, OC trigger, IC ratio, CCC bucket |
| Stress analytics | Bloomberg stressed price/spread/loss outputs if the terminal workflow supports them |

## Field Dictionary Rules

Every exported canonical column must have one row in:

```text
field_dictionary.csv
```

Required columns:

| Column | Meaning |
| --- | --- |
| `worksheet` | Workbook tab |
| `output_file` | Exported CSV file |
| `canonical_column` | Column consumed by Chapter 4 code |
| `bloomberg_function` | Bloomberg function, screen, BQL query, or manual workbook rule |
| `bloomberg_field` | Bloomberg field mnemonic when applicable |
| `security_or_screen` | Security, deal, screen, or universe used |
| `transformation` | Direct pull, conversion, median fill, explicit overlay, or manual entry |
| `notes` | Caveat, entitlement issue, fallback, or unit conversion |

Rules:

- Validate Bloomberg mnemonics in `FLDS` or the relevant Bloomberg help screen.
- Record every explicit analyst overlay.
- Record every conversion, including maturity date to `maturity_years` and recovery to `lgd`.
- Record whether PD, LGD, CPR, market price, and discount margin are facility-level, issuer-level, screen-derived, median-filled, or manually overlaid.
- Do not leave `field_dictionary.csv` incomplete just because the values are obvious to the Bloomberg operator.

## Parameter Rules

### PD

Use a one-year point-in-time default probability as `annual_pd`.

Source order:

1. Facility-level or obligor-level one-year PD.
2. Issuer-level one-year PD.
3. Sector x rating-bucket median PD from Bloomberg-covered names.
4. Explicit workbook-side overlay.

Every non-primary fill must be disclosed in `field_dictionary.csv`.

### LGD

Use a Bloomberg-backed expected recovery or recovery-style field when possible.

Source order:

1. Expected recovery converted to `lgd = 1 - expected_recovery`.
2. Realized LGD from default and recovery exports.
3. Seniority x sector median LGD from Bloomberg-covered names.
4. Explicit workbook-side overlay.

Record the recovery definition and timing.

### CPR

Bloomberg may not provide one clean forward CPR field for every loan. Populate `annual_cpr` using one of:

- Bloomberg-derived realized paydown history,
- a documented prepayment model in the workbook,
- an explicit analyst overlay.

Record the method in `field_dictionary.csv`.

### Rho

`rho` is not directly observed. Use one of two modes:

| Mode | Requirement | Manuscript claim |
| --- | --- | --- |
| Calibrated rho | Valid `bbg_clo_cohort_export.csv` | Rho is calibrated from observed default dispersion |
| Explicit rho | No valid cohort panel; `scenario_clo_stress.csv` supplies low/high rho | Rho remains an analyst stress assumption |

Do not claim calibrated dependence unless the cohort panel passes the sufficiency test.

## Bloomberg Analytics To Run

The Bloomberg run should produce both input data and benchmark outputs.

Run or export the closest available Bloomberg analytics for:

| Analytics area | Benchmark target |
| --- | --- |
| Collateral composition | balance, rating mix, sector mix, weighted average spread, weighted average maturity |
| Loan valuation | price or evaluated mark, discount margin, spread, maturity, floor |
| Deal tests | OC, IC, CCC bucket, trigger status |
| Tranche valuation | price, yield/spread, WAL/duration, rating, balance |
| Cash-flow analytics | projected interest/principal distributions if available |
| Stress analytics | price/spread/loss movement under default, recovery, spread, or correlation stress if available |

The Bloomberg analytics do not need to match the chapter model exactly. They provide an external calibration and reasonableness benchmark.

## Stage The Live Contract

After the values-only CSV package is staged under `D:\data\CLO\Chapter4\raw`, run:

```powershell
cd "D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\python"

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
  --as-of-date <AS_OF_DATE> `
  --source-url "Bloomberg Terminal air-gap workbook export"
```

If no valid cohort panel exists, omit `--cohort-export` and keep `scenario_clo_stress.csv` in explicit-rho mode.

The staged live contract must contain:

```text
fact_clo_collateral_position.csv
dim_clo_tranche.csv
scenario_clo_stress.csv
field_dictionary.csv
stage_metadata.json
```

Preferred staged files:

```text
fact_clo_manager_report.csv
agg_clo_cohort_default.csv
fact_clo_default_event.csv
fact_clo_recovery_event.csv
fact_clo_tranche_cashflow.csv
```

## Run Python And MATLAB

Python run:

```powershell
cd "D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\python"
python CLO.py --mode live --live-root D:\data\CLO\Chapter4\live_contract --output-dir D:\data\CLO\Chapter4\python_output
```

MATLAB run should use the same normalized live contract:

```powershell
matlab -batch "cd('D:\dev\ECR Capital Management\Book2\repo\examples\Chapter 4\Correlation and Tail Risk in CLO Tranches\Matlab'); CLO"
```

If MATLAB does not yet accept an explicit live root, update the MATLAB script only after confirming the Python live contract is valid. The MATLAB result should not use a different raw Bloomberg extraction.

## Reconciliation Against Bloomberg

Create:

```text
D:\data\CLO\Chapter4\reconciliation\clo_bloomberg_reconciliation.md
D:\data\CLO\Chapter4\reconciliation\clo_bloomberg_reconciliation.csv
```

Compare Bloomberg, Python, and MATLAB outputs.

Required reconciliation checks:

| Area | Check |
| --- | --- |
| Collateral balance | Total par and row count match Bloomberg export |
| Rating/sector mix | Weighted mix matches Bloomberg within rounding |
| Collateral mark | Weighted average model price versus Bloomberg/evaluated mark |
| Tranche stack | Attachment, detachment, balances, coupon/spread, and identifiers match |
| OC/IC diagnostics | Trigger inputs match Bloomberg manager-report values |
| Rho mode | Calibrated or explicit mode is documented |
| Python vs MATLAB | Same live contract produces consistent tranche metrics |
| Bloomberg vs internal model | Price/spread/loss differences are explained, not ignored |

Suggested tolerance defaults:

| Metric | Tolerance |
| --- | --- |
| Total collateral par | exact or less than 0.1% difference due to rounding |
| Loan count | exact |
| Weighted average spread | less than 5 bps difference |
| Weighted average maturity | less than 0.05 years difference |
| Weighted average collateral price | less than 0.25 price points difference before model calibration |
| Tranche attachment/detachment | exact |
| Python vs MATLAB expected tranche loss | less than 0.05 percentage points with same seed/path setup |
| Bloomberg vs internal tranche price/spread | no fixed pass threshold; must be explained by model convention, assumptions, or missing Bloomberg details |

Do not force Python/MATLAB to match Bloomberg by hidden parameter tuning. Calibration changes must be visible in the run metadata and reconciliation report.

## Acceptance Criteria

The real Bloomberg 4.1 run is accepted only if:

1. The selected CLO and as-of date are documented.
2. `field_dictionary.csv` maps every exported canonical column.
3. The collateral export contains enough data to value each loan before tranche allocation.
4. Bloomberg analytics outputs are exported and saved separately from input files.
5. The live contract stages successfully.
6. Python runs on the live contract.
7. MATLAB either runs on the same live contract or is explicitly marked not yet live-compatible.
8. Reconciliation explains Bloomberg-versus-internal differences.
9. The manuscript clearly distinguishes the accepted Bloomberg run from the old synthetic demonstration.

## Narrative Update Rules

After acceptance, update 4.1 to say:

```text
The public repository keeps a synthetic Bloomberg-compatible tape so readers can run the example without a Bloomberg license. The accepted live run uses one real Bloomberg CLO export staged outside the repository. The same code path values the loan collateral first, then maps the collateral distribution through the tranche stack.
```

Do not claim:

- the model is a full production CLO engine,
- Bloomberg and the internal model use identical assumptions,
- the single selected CLO represents all CLOs,
- rho is calibrated if it is supplied as an analyst stress assumption,
- synthetic public data reproduces the real Bloomberg result,
- licensed data can be redistributed in the public repo.

## First Milestone

The first milestone is a data-readiness package, not a model rerun.

Milestone output:

```text
D:\data\CLO\Chapter4\raw\deal_selection_memo.md
D:\data\CLO\Chapter4\raw\field_dictionary.csv
D:\data\CLO\Chapter4\raw\bbg_clo_tranche_export.csv
D:\data\CLO\Chapter4\raw\bbg_loan_collateral_export.csv
D:\data\CLO\Chapter4\raw\bloomberg_analytics_summary.csv
```

The model should not be rerun or promoted until the first milestone passes a basic completeness audit.
