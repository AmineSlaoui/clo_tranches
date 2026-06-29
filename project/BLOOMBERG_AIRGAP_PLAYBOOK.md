# Bloomberg Air-Gap Playbook

This Chapter 4 live route is intentionally split across two machines:

- Bloomberg-connected machine: Terminal plus Excel Add-In or Desktop API
- analysis machine: this repo, Python staging, and the chapter runtime

For the file-by-file export contract for collateral valuation fields, `PD`,
`LGD`, trigger history, and `rho` calibration inputs, see
`CLO-Bloomberg-Data-Needed.md`.

## What Bloomberg Covers

Bloomberg is the preferred source for:

- `bbg_clo_tranche_export.csv`
- `bbg_loan_collateral_export.csv`
- `bbg_clo_manager_export.csv`
- optional `bbg_clo_cohort_export.csv`
- optional `bbg_loan_default_export.csv`
- optional `bbg_loan_recovery_export.csv`
- optional `scenario_clo_stress.csv`
- `field_dictionary.csv`

Bloomberg does not replace:

- the chapter runtime on this machine
- the normalized Chapter 4 contract
- the manuscript refresh workflow

## Workbook Layout On The Bloomberg Machine

Use one workbook with these tabs:

- `README`
- `field_dictionary`
- `tranche_export`
- `collateral_export`
- `manager_export`
- optional `default_export`
- optional `recovery_export`
- optional `cohort_export`
- optional `stress_export`

Recommended Bloomberg workflow:

1. Use `PREL`, `CPR`, `TRIG`, `BVAL`, and leveraged-loan screening workflows
   to define the representative deal and collateral universe.
2. Populate the collateral tape with coupon spread, reference rate, floor,
   maturity, rating, and at least one valuation anchor: `market_price` or
   `discount_margin_bps`.
3. Validate every field mnemonic in `FLDS` before putting it into the workbook.
4. Use Excel Add-In or Desktop API pulls such as `BDP`, `BDH`, `BDS`, or `BQL`
   to populate the final values-only tables.
5. Record the field mnemonics and worksheet purpose in `field_dictionary.csv`.

## Export Files From The Bloomberg Machine

Export values-only CSVs with these names:

- `bbg_clo_tranche_export.csv`
- `bbg_loan_collateral_export.csv`
- `bbg_clo_manager_export.csv`
- optional `bbg_clo_cohort_export.csv`
- optional `bbg_loan_default_export.csv`
- optional `bbg_loan_recovery_export.csv`
- optional `scenario_clo_stress.csv`
- `field_dictionary.csv`

The workbook should already map Bloomberg-specific labels into the chapter's
canonical columns before export.

## Stage The Live Contract On This Machine

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

If no cohort panel exists, omit `--cohort-export` and keep
`scenario_clo_stress.csv` in explicit-rho mode, or pass explicit `--low-rho`
and `--high-rho` values to the staging script.

## Run The Chapter

```powershell
python CLO.py --mode live --live-root D:\data\CLO\Chapter4\live_contract
```

This writes the rendered figures, CSV summaries, and `clo-run-metadata.json`
for the actual-data run.
