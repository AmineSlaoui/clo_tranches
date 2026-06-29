---

## 1. Top-level layout

```
correlation_and_tail_risk_in_clo_tranches/
├── README_FIRST.md            Project intro & quickstart (sample vs. live mode)
├── requirements.txt           numpy, pandas, matplotlib, scipy — that's it
├── run_sample.ps1             PowerShell: runs the synthetic public demo
├── run_live_template.ps1      PowerShell: runs against private Bloomberg/SEC data
│
├── project/                   ← all the actual code lives here
├── data/                      empty stub (README only)
├── sample_data/               empty stub (README only)
├── outputs/                   empty stub (sample/live runs land here)
├── live_contract_template/    empty stub (README only)
├── provenance/                manifests describing what was packaged
└── shared/                    cross-chapter helpers & metadata
```

The empty `data/`, `outputs/`, etc. directories exist because the "live" path expects you to drop Bloomberg exports outside the repo. The public/sample path generates everything synthetically.

---

## 2. `project/` — the heart of the work

```
project/
├── README.md, DATA_CARD.md           What the example does + data contract
├── run_example.py                    Thin wrapper → calls python/CLO.py
├── BLOOMBERG_AIRGAP_PLAYBOOK.md      How to ferry Bloomberg data over an air gap
├── CLO-Bloomberg-Data-Needed.md      Exact Bloomberg fields you'd need
├── PUBLIC_BDC_CASE_STUDY_PLAYBOOK.md SEC EDGAR fallback workflow
│
├── python/                           ← canonical implementation
├── r/                                R mirror (legacy / older surface)
├── Matlab/                           MATLAB mirror (legacy / older surface)
├── notebooks/                        Jupyter notebook for the same workflow
└── live_contract_template/           Header-only CSVs defining the live schema
```

### `project/python/` — the canonical surface

| File | Lines | Purpose |
|------|------:|---------|
| `CLO.py` | 1931 | The whole pipeline: data, calibration, Monte Carlo, plots, CLI |
| `extract_public_bdc_clo_case_study.py` | 1046 | Pulls Palmer Square BDC CLO 1 filings from SEC EDGAR |
| `stage_actual_clo_contract.py` | 498 | Maps Bloomberg / SEC raw CSVs into the normalized contract |
| `test_clo_smoke.py` | 772 | pytest smoke tests for public + live paths |
| `rendered-sample/` | — | Pre-rendered PNG/SVG/CSV outputs from a sample run |
| `rendered-public-sec-case-study/` | — | Pre-rendered outputs from the SEC case study |

---

## 3. What `CLO.py` actually computes

This is the file that matters. It runs in either **`--mode public`** (synthetic Bloomberg-compatible tape, no external data) or **`--mode live`** (reads a normalized CSV contract from `--live-root`).

### Pipeline (one run)

1. **Build inputs** (`build_public_inputs` or `build_live_inputs`)
   - **Loan pool** of ~400 loans with: `current_balance`, `annual_pd`, `annual_cpr` (prepayment), `lgd`, sector, rating, coupon spread, reference rate, floor, maturity, discount margin. Synthetic version draws from beta/lognormal distributions calibrated to look like a B/BB rated CLO collateral tape.
   - **Tranches** (`Equity 0–6%`, `Mezzanine 6–14%`, `Senior 14–30%`) with OC trigger levels.
   - **Cohort panel** — synthetic historical sector-year default-rate table used to calibrate rho.
   - **Scenario defs** — `low` and `high` versions of rho, plus PD/CPR/LGD shocks.

2. **Calibrate asset correlation** (`calibrate_asset_correlation`)
   - Vasicek one-factor model: defaults driven by a single common factor + idiosyncratic noise.
   - Match the **cross-cohort variance of default rates** against the model's implied variance over a grid of rho ∈ [0.01, 0.35]. Minimum-distance fit ⇒ `rho_hat`.

3. **Value the collateral** (`value_collateral_pool`, `loan_expected_price`)
   - For each loan, do a 5-year DCF: discounted coupon + recovery + prepay + maturity cash flows under expected PD/CPR/LGD. Produces `model_price` per 100 par.
   - Compares against synthetic "market" marks → price gap diagnostics.

4. **Monte Carlo tranche engine** (`run_tranche_engine`) — the core
   - 25,000 paths × 5 years × ~400 loans, fully vectorized.
   - Each year: draw one systemic Normal + per-loan idiosyncratic Normals → latent asset values `√ρ·Z + √(1-ρ)·ε`. Default if below `Φ⁻¹(PD)`.
   - Apply prepayment draw, maturity, accumulate losses, discount cash flows.
   - Map cumulative collateral loss → tranche principal loss via `tranche_loss_on_par` (the kinked attach/detach payoff).
   - Track pathwise OC-trigger breaches and a "break-even spread" for each tranche (protection leg ÷ premium leg, in bps).

5. **Same-marginals low-ρ vs high-ρ experiment**
   - Two scenarios with identical PD/CPR/LGD/horizon — only ρ differs.
   - This isolates the *dependence* effect, which is the chapter's whole point: equity tail risk decreases with ρ (idiosyncratic losses always hit equity); senior tail risk increases sharply with ρ (you need correlated mass defaults to ever touch senior).

6. **Outputs** (written to `--output-dir`)
   - CSVs: `clo-tranche-summary-metrics.csv`, `clo-rho-scenarios.csv`, `clo-collateral-valuation-table.csv`, `clo-rho-calibration-grid.csv`, `clo-monte-carlo-diagnostics.csv`, `clo-validation-checks.csv`, `clo-run-metadata.json`.
   - Plots (PNG + SVG): payoff map, rho calibration objective + fit, collateral loss CDF, per-tranche loss CDFs, tail metrics bar chart (EL/VaR99/CVaR99), trigger frequencies, break-even spreads.

7. **Validation** (`build_validation_checks`)
   - Asserts: path count ≥ 10k, high-ρ > low-ρ, B-2 spread sensitivity is positive, Class A expected loss stays trace, MC standard error reported.

### Live mode contract

`build_live_inputs` reads 8 CSV tables from `--live-root`:

| Table | Required? | What it holds |
|---|---|---|
| `fact_clo_collateral_position.csv` | ✅ | Per-loan balances, PD, CPR, LGD, ratings, market price, coupon, DM |
| `dim_clo_tranche.csv` | ✅ | Attach/detach/trigger levels per tranche |
| `scenario_clo_stress.csv` | ✅ | Named `low`/`high` rows with rho overrides or multipliers |
| `agg_clo_cohort_default.csv` | optional | Historical cohort defaults → enables true rho calibration |
| `fact_clo_manager_report.csv` | optional | OC/IC trigger levels, CCC bucket % |
| `fact_clo_default_event.csv` | optional | Used to back out empirical LGD |
| `fact_clo_recovery_event.csv` | optional | Used to back out empirical LGD |
| `fact_clo_tranche_cashflow.csv` | optional | Tranche cash-flow history |

`stage_actual_clo_contract.py` is the **column-name normalizer** — it has `ALIAS_MAPS` mapping Bloomberg/Intex/Trepp field names (`par_amount`, `bval_price`, `id_bb_global`, …) to the canonical contract.

`extract_public_bdc_clo_case_study.py` is the **SEC EDGAR fetcher** — it hits `data.sec.gov/submissions` for Palmer Square BDC CLO 1 (CIK 1794776), resolves the 8-K/10-K filings, scrapes the indenture + collateral schedule via BeautifulSoup, and writes raw CSVs that then get fed to `stage_actual_clo_contract.py --route public_bdc_clo_case_study`.

---

## 4. R and MATLAB mirrors

`project/r/CLO.R`, `CLO.Rmd` (347 + 69 lines) and `project/Matlab/CLO.m`, `CLO.mlx` (381 lines) are **legacy public mirrors** of the same workflow — they don't have the live-contract or DCF-valuation features. The README explicitly says: *"Use the Python path for the current Bloomberg-ready collateral valuation contract."*

The `.mlx` files are MATLAB Live Scripts (binary); the `_CLO_extracted_review.txt`, `_CLO_document.xml`, and `CLO.zip` are MATLAB internals.

---

## 5. `shared/` — cross-chapter scaffolding

This isn't really part of *this* example — it's leftover scaffolding from the larger Book2 repo.

- `shared/README.md`: states the repo policy (*no licensed data, no machine-readable live outputs*).
- `shared/registry/*.yml`: metadata describing **all chapters** of the book (CLO is one of ~12). Includes `chapters.yml`, `modules.yml`, `tables.yml`, `dependencies.yml`, etc.
- `shared/packages/python/book2_public/`: contains `options_implied_ceasefire.py` — this is for a **different chapter** (Chapter 8: "Implied Ceasefire Timing from USO Options"). It looks like dead weight that got bundled in.
- `shared/adapters/`: README-only stubs (canonical / vendor_compatible).

The file `shared/packages/python/book2_public/__init__.py` is **not relevant** to CLOs — it exports helpers for an unrelated options chapter.

---

## 6. `provenance/` — packaging metadata

Manifests proving what was bundled into this zip distribution:

- `READY_PACKAGE_MANIFEST.txt`, `wrapper/ZIP_CONTENT_MANIFEST.json`
- `internal_package_manifests/file_manifest.csv`, `validation_report.md`
- `wrapper/CLO_Bloomberg_real_data_download_plan.md`

Useful as audit trail; not needed to run anything.

---

## 7. How to actually run it

The PowerShell scripts assume Windows. On macOS/Linux:

```bash
pip install -r requirements.txt
python project/run_example.py --output-dir ./outputs/sample
# → runs CLO.py --mode public --output-dir ./outputs/sample
```

For a quick smoke test: `python project/python/CLO.py --smoke` (uses 768 paths instead of 25k).

For live mode: stage a Bloomberg or SEC export through `stage_actual_clo_contract.py`, then:

```bash
python project/run_example.py --output-dir ./outputs/live --live-root /path/to/contract
```

---

## 8. Key conceptual takeaways the example teaches

- **Vasicek one-factor**: a single common factor + per-name noise produces correlated defaults; ρ is the loading on the common factor.
- **Rho calibration via cross-cohort dispersion**: if you have historical year-by-sector default rates, the *variance* of those rates pins down ρ. No cohort panel ⇒ you must input low/high ρ directly.
- **Same-marginals experiment**: the workflow's headline result. Keeps PD/CPR/LGD/horizon identical, varies only ρ, and shows the tail asymmetry across tranches.
- **Tranche math**: `tranche_loss = clip(pool_loss − attach, 0, detach − attach)`. Equity gets hit first; senior only takes losses if pool loss exceeds 14%.
- **Loss-compensation spread**: the bps coupon that would make expected protection payouts equal expected premium — a model "fair spread" that's directly comparable across ρ scenarios.