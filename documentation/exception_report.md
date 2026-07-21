# Exception Report — ARES 2023-68A live-contract readiness (v3, 2026-07-03)
Data-quality agent pass per L4 4.1.5. v2 incorporates the student Bloomberg bundle
(ARES_2023-68A-LLM-small-final_20260702). Re-run tools/make_data_readiness_package.py
(with --mv) after any fix; checks must PASS before staging.

## BLOCKING (live run must not start until resolved)
| # | Item | Owner action |
| --- | --- | --- |
| E2 | `annual_pd` empty | Fill via `rating_for_pd` → named S&P default table (cite table + vintage). Never reuse synthetic-run PDs |
| E3 | `annual_cpr` empty | Finish Principal Activity Report calc (method in field_dictionary). Corroborate against CLP monthly Balance / Principal-Acct series (35 months) and the CFT `unsched` column (~1.85%/mo ≈ 20 CPR under Bloomberg's 20-CPR base setting — that is an assumption echo, not realized data) |
| E5 | `lgd` is stress-basis (1−S&P RR, WA 61.3%); `lgd_base` empty | Confirm scenario of the S&P recovery field; fill base-case LGD (~25–35% first-lien) |
| E7 | `scenario_clo_stress.csv` rho values empty | Adopt named-source low/base/high (explicit mode). CLP has 35 months of deal-level default history — useful exhibit, but fails the cohort sufficiency test; still explicit mode |

## RESOLVED / DOWNGRADED since v1
| # | Was | Now |
| --- | --- | --- |
| E1 | as_of_date unknown | **Period pinned to 05/2026**: tape ties CLP 05/2026 column exactly (balance 492,061K, 415 loans, default 0.55%, WA margin 3.011); CFT opens 2026-05-25 at 500,807,340.42 = CLP Total Bal to the cent; TRIG values = CFT trigger start. Bloomberg pull 2026-06-18 (filenames); SYT settle 2026-06-22; payment day = 25th. REMAINING: enter the Monthly report determination date and fill the column |
| E4 | reference_rate unknown | **RESOLVED & FILLED**: 0.03656 decimal in every row (CFT `Index Rates`, TSFR3M @ 2026-05-25). Necessary override: CLO.py silently fills blanks with a stale 5.25% default |
| E8 | Code zip encrypted | **CLOSED** (password received). Package aligned to the real schemas and **verified end-to-end**: `stage_actual_clo_contract.py --route bloomberg_market_observed` stages all 7 contract files from this package; `CLO.py --mode live` then halts with exactly "The live collateral contract needs numeric current_balance, annual_pd, annual_cpr, and lgd inputs" — the do-not-invent gate working as designed (PD/CPR are the blanks). Smoke tests: 7/7 pass. Staging test used TEST rho 0.10/0.30 — staged output NOT shipped; never reuse those values |
| E6 | Tranche export empty | **Filled from MV overview** (balances, %Sub, all-in coupons; attach/detach computed loss-basis; spreads derived vs TSFR3M). Single source — confirm vs Periodic Report note detail (two-source rule); CUSIPs/ratings per class still to add from DES pages |
| V1 | D1R/D2R sequencing unknown | **CLOSED**: Interest & Principal PoP — D1R and D2R are separate sequential steps (D1R first) sharing single Class D coverage tests, exactly as the TRIG panel implied |

## New conventions applied in v3 (documented, verify later)
- **Trigger semantics conversion**: CLO.py fires triggers on cumulative collateral LOSS ≥ trigger_level. OC-ratio triggers converted via L* = 1 − T·D_g/P0 → AB 6.09%, C 5.01%, D 3.78%, E 2.59%, diversion 2.12% (static approximation; F/SUB assigned the diversion level). **Code gap flagged for the rewrite**: CLO.py's fallback fills trigger_level from raw OC ratios (~1.2), which can never fire on a loss fraction — supplying converted values sidesteps it; students should fix the semantics in the rewrite (V10).
- **DM = spread (par-DM approximation)**: model requires numeric discount_margin_bps for pricing; filled equal to coupon_spread_bps with dm_source flag (FXD rows → 0 → base discount rate). Refine if per-loan DMs become available (V9).
- **maturity_years filled** with provisional values (CLO.py int-rounds; determination-date drift immaterial), **coupon_floor converted to decimals** per code units, **manager report emitted per class** (loader validates every dim tranche name appears).

## VERIFY-BEFORE-USE (open)
- V2 Trustee OC/IC tie-out — trustee reports are the "new data not included in the zip"; transcribe + reconcile (>0.5pp deltas investigated)
- V3 Purchases/sales check for the six proxied prices (Monthly report)
- V4 Estimated ratings for the two unrated loans (Monthly report rating detail)
- V5 Reinvestment period end date — Portfolio Statistics.pdf is image-only (no text layer); OCR it or read from the reports. SYT call date 07/25/2027 @100 recorded (likely non-call end, NOT reinvestment end — do not conflate)
- V6 S&P CCC definitional delta (tape 7.56 vs panel 6.9) — document
- V7 Verify derived tranche spreads and per-class index vs DES pages / Periodic Report (all-in minus TSFR3M is an inference)
- V9 Par-DM approximation (dm_source column) — replace if loan-level DMs sourced. RECORD CORRECTION: the loader would otherwise silently fill blank DM with spread+75bps (and blank spreads with 500bps) — our explicit fill preempts silent invention
- V10 Trigger-semantics code gap — **patch proposed & verified** (patches/clo_live_loader_guards.diff): domain guard raises on OC-style trigger_level ≥ 1 with the conversion formula; silent live-contract fills now warn. Smoke tests 7/7 with patch; bug reproduced on original (silent 1.216 backfill). Author to adopt via provenance process; students fix semantics properly in the rewrite
- V8 Collect SYT prices for all classes (only BR = 94.81 captured); price-matrix JPGs (36) remain untranscribed visual benchmarks

## Conventions already applied (audit columns in the CSVs)
Unchanged from v1: 6 price proxies, 2 LGD fallbacks, 1 synthetic ID, 24 issue-rating PD fallbacks,
FXD floor convention (code must branch on coupon_type), LABL recovery = observed price 43.89.
