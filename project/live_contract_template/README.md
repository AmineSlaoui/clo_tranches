# Live Contract Template

Populate these header-only CSVs outside the public repo and point `python/CLO.py --mode live --live-root <directory>` at that local directory.

Required core tables:

- `fact_clo_collateral_position.csv`: actual collateral rows with current balance, annual PD, annual CPR, LGD, rating/sector, coupon spread, reference-rate/floor assumptions, maturity, and at least one valuation anchor (`market_price` or `discount_margin_bps`) for licensed Bloomberg/Intex/Trepp runs.
- `dim_clo_tranche.csv`: tranche terms for one representative deal, with direct trigger levels or enough manager-report data to supply them.
- `scenario_clo_stress.csv`: named `low` and `high` comparison rows with explicit `rho` values or a shared `base_rho` plus low/high `rho_multiplier` values.

Optional enrichment tables:

- `agg_clo_cohort_default.csv`: repeated cohort default history for true rho calibration.
- `fact_clo_tranche_cashflow.csv`: tranche cash-flow rows by payment date.
- `fact_clo_manager_report.csv`: tranche-level manager diagnostics and trigger levels.
- `fact_clo_default_event.csv`: loan default events.
- `fact_clo_recovery_event.csv`: loan recovery events.

Actual-data sources may include Bloomberg CLO and syndicated-loan exports staged across an air gap, Intex/Trepp bundles, or a free-public BDC-sponsored case study built from SEC EDGAR filings and public deal documents. Use `python/stage_actual_clo_contract.py` to normalize exported CSVs into this contract.

Recommended workflows:

- Bloomberg route: `../BLOOMBERG_AIRGAP_PLAYBOOK.md`
- Public case-study route: `../PUBLIC_BDC_CASE_STUDY_PLAYBOOK.md`
