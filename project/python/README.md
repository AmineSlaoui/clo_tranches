# Collateralized Loan Obligation

This Python surface is the canonical implementation for both the public fallback and the actual-data live contract.

Public mode keeps the chapter intentionally small:

- build a Bloomberg-compatible synthetic collateral tape
- value each collateral loan from coupon, floor, maturity, PD, CPR, LGD, and discount margin
- compare model DCF prices with synthetic market-style marks
- calibrate a one-factor asset correlation from repeated cohort default-rate dispersion
- hold marginals fixed and run a low-rho versus high-rho experiment
- map collateral loss into true tranche-by-tranche principal loss
- track simple pathwise OC trigger frequencies by tranche
- summarize tranche expected loss, tail loss, and break-even loss-compensation spread

The canonical teaching code is [CLO.py](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/python/CLO.py).

Run the public fallback with:

- `python CLO.py --mode public`

Run the actual-data live contract with:

- `python CLO.py --mode live --live-root <directory>`

The live root must contain the normalized CSV contract described in [../DATA_CARD.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/DATA_CARD.md) and templated under `../live_contract_template/`. Licensed Bloomberg/Intex/Trepp runs must include a valuation anchor for the collateral, either `market_price` or `discount_margin_bps`, plus coupon spread and maturity fields.

Supported actual-data routes:

- Bloomberg market-observed CLO and loan exports staged across an air gap
- Intex or Trepp-style richer local bundles
- free-public BDC-sponsored CLO case studies extracted from SEC EDGAR filings and deal documents

Use `python stage_actual_clo_contract.py --route bloomberg_market_observed ...` or `--route public_bdc_clo_case_study ...` to map exported CSVs into the normalized Chapter 4 contract.

For Bloomberg, follow [../BLOOMBERG_AIRGAP_PLAYBOOK.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter%204/Correlation%20and%20Tail%20Risk%20in%20CLO%20Tranches/BLOOMBERG_AIRGAP_PLAYBOOK.md).

For the pinned free-public fallback, first run:

- `python extract_public_bdc_clo_case_study.py --output-dir <raw_dir> --sec-user-agent "<name> <email>" --low-rho <value> --high-rho <value>`

Then stage the resulting raw exports with:

- `python stage_actual_clo_contract.py --route public_bdc_clo_case_study --deal-id PALMER_SQUARE_BDC_CLO_1 --output-dir <live_root> --tranche-export <raw_dir>\\public_tranche_export.csv --collateral-export <raw_dir>\\public_collateral_export.csv --stress-export <raw_dir>\\public_stress_export.csv`

The extractor resolves the case study through EDGAR submissions JSON plus filing-directory `index.json`, and writes resolved accessions and URLs into `public_case_study_metadata.json`.

This example still uses synthetic Bloomberg-compatible data in `--mode public`, but `--mode live` now means actual investment data rather than synthetic fallback.
