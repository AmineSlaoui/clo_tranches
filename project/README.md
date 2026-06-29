# Collateralized Loan Obligation

This example now exposes two explicit paths:

- [python/CLO.py](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/python/CLO.py)
- [Matlab/CLO.mlx](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/Matlab/CLO.mlx)
- [r/CLO.Rmd](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/r/CLO.Rmd)

- Public scenario path: the canonical Python surface uses a Bloomberg-compatible synthetic collateral tape to teach the full collateral-valuation-then-tranche workflow.
- Local actual-data path: the canonical adapter is the Python surface, which reads a normalized CLO contract for actual CLO tranches and loans from a local directory outside the repo.

The shared live contract is documented in [DATA_CARD.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/DATA_CARD.md) and templated under `live_contract_template/`.

Actual-data runs may be staged from:

- Bloomberg CLO and syndicated-loan exports staged across an air gap
- Intex or Trepp exports
- a pinned free-public BDC-sponsored CLO case study built from SEC EDGAR filings and public deal documents

Use [python/stage_actual_clo_contract.py](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/python/stage_actual_clo_contract.py) to map exported CSVs into the normalized Chapter 4 contract, and [python/extract_public_bdc_clo_case_study.py](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/python/extract_public_bdc_clo_case_study.py) to build the raw public case-study package from EDGAR submissions and filing-index endpoints.

Workflow references:

- [BLOOMBERG_AIRGAP_PLAYBOOK.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/BLOOMBERG_AIRGAP_PLAYBOOK.md)
- [CLO-Bloomberg-Data-Needed.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/CLO-Bloomberg-Data-Needed.md)
- [PUBLIC_BDC_CASE_STUDY_PLAYBOOK.md](D:/dev/ECR%20Capital%20Management/Book2/repo/examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/PUBLIC_BDC_CASE_STUDY_PLAYBOOK.md)

All three versions preserve the same public workflow:

- loan-level collateral DCF valuation using coupon, floor, maturity, PD, CPR, LGD, discount margin, and market-style marks
- deterministic tranche payoff map
- cohort-dispersion rho calibration when actual cohort data exists, or explicit low/high rho scenario runs when it does not
- low-rho versus high-rho same-marginals experiment
- true tranche-by-tranche loss distributions
- pathwise tranche warning-trigger frequencies
- pathwise loss-compensation spreads

The MATLAB and R files remain public mirrors for the older tranche-risk surface.
Use the Python path for the current Bloomberg-ready collateral valuation
contract.

Rendered sample figures and tables are written to each language folder's
`rendered-sample/` directory.
