# Data Card: CLO Tail Risk

## Label

- Public runnable path: `scenario`
- Local actual-data path: `licensed` for Bloomberg/Intex/Trepp bundles or `public` for free-public case studies, always mapped outside repo into one normalized contract

## What This Example Supports

- one-factor rho calibration from repeated cohort default-rate dispersion
- loan-level collateral DCF valuation before tranche allocation
- deterministic collateral-to-tranche waterfall mapping
- low-rho versus high-rho tail comparison under fixed marginals
- tranche trigger frequencies and loss-compensation spreads
- actual-investment market-observed CLO runs without synthetic collateral generation

## Public Path

- Run `python python/CLO.py --mode public`
- The public runtime is self-contained and uses a Bloomberg-compatible synthetic collateral tape that preserves workflow semantics rather than any one vendor deal history.
- Public outputs remain limited to figures, CSV summaries, and run metadata under `python/rendered-sample/`.

## Live Path

- Run `python python/CLO.py --mode live --live-root <directory>`
- The canonical live adapter is the Python surface. MATLAB and R remain public mirrors until the same contract is needed there.
- "Live" means actual investment data for real CLO tranches, loans, and deal structures. It does not mean the public synthetic fallback.
- The live root contains normalized CSVs named after the shared table IDs and can be staged from Bloomberg air-gap exports or free-public case-study files by using `python/stage_actual_clo_contract.py`.
- Supported source families now include `Bloomberg CLO`, `Bloomberg Syndicated Loans`, `Intex CLO`, `TreppCLO`, `Trepp SRA`, `public CLO ETF holdings`, `SEC ABS filings`, and public deal documents.
- The public SEC route is EDGAR-first: submissions JSON identifies the filing, filing-directory `index.json` resolves the correct document, and the extractor records resolved accessions and URLs in `public_case_study_metadata.json`.
- The live adapter supports two honest fidelity levels:
  - `market_observed`: real tranche and loan inputs plus explicit low/high rho values, without full deal reconstruction
  - `case_study_reconstruction`: richer actual-data runs with cohort history, default/recovery events, or tranche cash flows

## Normalized Contract

- Required core tables:
- `fact_clo_collateral_position.csv`: actual collateral rows with `deal_id`, `as_of_date`, `loan_id`, `sector`, `current_balance`, `annual_pd`, `annual_cpr`, `lgd`, `rating`, `market_price`, `coupon_spread_bps`, `reference_rate`, `coupon_floor`, `maturity_years`, `discount_margin_bps`, and provenance fields
  - `dim_clo_tranche.csv`: tranche stack with `deal_id`, `tranche`, `attach`, `detach`, and either direct `trigger_level` values or a manager-report fallback
  - `scenario_clo_stress.csv`: named `low` and `high` rows with either explicit `rho` values or low/high `rho_multiplier` values; the file may also declare `base_rho`, `source_family`, and `pack_label`
- Optional enrichment tables:
  - `agg_clo_cohort_default.csv`: repeated cohort default history for true rho calibration when actual cohort data exists
  - `fact_clo_manager_report.csv`: report diagnostics with `deal_id`, `report_date`, `tranche`, `oc_ratio`, `oc_trigger_level`, plus optional coverage or collateral-quality fields
  - `fact_clo_default_event.csv`: loan default history with `deal_id`, `loan_id`, `default_date`, `defaulted_balance`
  - `fact_clo_recovery_event.csv`: recovery history with `deal_id`, `loan_id`, `recovery_date`, `recovered_balance`, and optional `recovery_rate`
  - `fact_clo_tranche_cashflow.csv`: tranche cash-flow rows with `deal_id`, `tranche`, `payment_date`, `interest_cash`, `principal_cash`, `outstanding_balance`

## Actual-Data Route Examples

- Bloomberg primary route:
  - actual tranche terms and prices from Bloomberg CLO exports staged across an air gap
  - actual loan balances, ratings, market marks, coupon terms, maturity, and valuation spread fields from Bloomberg syndicated-loan exports
  - values-only CSV exports plus `field_dictionary.csv`, then `python/stage_actual_clo_contract.py --route bloomberg_market_observed`
  - explicit low/high rho rows entered in `scenario_clo_stress.csv` when no cohort panel is available
- Free-public fallback route:
  - one representative public BDC-sponsored CLO case study, currently `Palmer Square BDC CLO 1`
  - actual note terms from the public 8-K and indenture plus actual pledged collateral rows from the public 10-K schedule of investments
  - direct EDGAR retrieval through SEC submissions and filing-index endpoints, with a declared SEC user agent
  - `python/extract_public_bdc_clo_case_study.py` builds raw public CSVs which are then normalized through `python/stage_actual_clo_contract.py --route public_bdc_clo_case_study`
  - explicit low/high rho rows and PD/CPR/LGD overlays remain judgmental analyst inputs and must be disclosed as such

## Workflow Playbooks

- Bloomberg air-gap workflow: `BLOOMBERG_AIRGAP_PLAYBOOK.md`
- Bloomberg export contract: `CLO-Bloomberg-Data-Needed.md`
- Public BDC case-study workflow: `PUBLIC_BDC_CASE_STUDY_PLAYBOOK.md`

## Preserved Properties

- explicit deal, loan, and tranche identities inside one representative live run
- auditable rho calibration inputs rather than a hard-coded dependence scalar
- pathwise tranche loss, trigger, and spread objects derived from one shared waterfall
- loan-level model prices, market-style price comparison, and collateral NAV distributions produced before the waterfall
- a clear distinction between real actual-investment inputs and the synthetic public fallback

## Intentionally Not Preserved

- raw vendor rows or machine-readable vendor extracts in the public repo
- any claim that the public synthetic path uses Bloomberg data or replicates one real deal exactly
- vendor-specific extraction logic beyond the normalized shared contract

## Current Blocker

- The repo now includes a rendered public SEC case-study output pack, but the normalized live contract and cached SEC pulls remain local scratch artifacts rather than committed repo data. Bloomberg, Intex, and Trepp routes still require external data outside the public repo.
