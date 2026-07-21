# HANDOFF — ARES 2023-68A live run for Chapter 4.1 (CATRICLOT) — v3, 2026-07-03
**Read this first.** Lets any assistant — or the author alone — continue without the conversation
that produced it. **Verified facts** are computed from source files and reproducible via
`tools/make_data_readiness_package.py --mv <market_value_overview path>`. **Handling: LOCAL ONLY**
(licensed Bloomberg derivatives + restricted trustee documents; nothing to the public repo).

## 1. State of play
**The pipeline is proven end-to-end.** With the code distribution opened (password received), this
package was aligned to the real schemas and tested against the author's own scripts:
`stage_actual_clo_contract.py --route bloomberg_market_observed` stages all seven live-contract
files from `raw/`, and `CLO.py --mode live` then halts with exactly *"The live collateral contract
needs numeric current_balance, annual_pd, annual_cpr, and lgd inputs"* — i.e., only the
do-not-invent blanks remain (annual_pd, annual_cpr; plus lgd_base, rho values, determination
date). Smoke tests 7/7. Course framing: students **mimic Bloomberg's analyses first, then
extend** — see STUDENT_WORKFLOW.md, including the key architectural fact below (§3a).

## 2. Package contents
As v1 (memo, exception report, raw/ CSVs, field dictionary, script) **plus** STUDENT_WORKFLOW.md, **chapter_edit_pack.md** (repair table + gated paste blocks: manuscript untouched pre-acceptance per Narrative Update Rules), and **patches/clo_live_loader_guards.diff** (proposed guards: trigger-domain error + loud default fills; verified 7/7);
tranche export now FILLED; analytics summary extended (tranche rows, SYT/CFT constants).
Source bundle inventory: see deal_selection_memo.md §Student bundle. Trustee reports, TRIG CSV,
and the trustee OC/IC screenshot are the "new data not included in the zip."

## 3. Verified facts (additions in v2)
| Fact | Value |
| --- | --- |
| Date web | Tape period = **05/2026** (ties CLP 05/2026: bal 492,061K, 415 loans, dflt 0.55, WAM 3.011); CFT opens 2026-05-25 @ **500,807,340.42** = CLP Total Bal to the cent; CFT opening triggers = TRIG panel (AB IC 1.5011); pull 2026-06-18; SYT settle 2026-06-22; payment day 25th (⇒ Periodic_Report_05_25_26 = 5/25/26 payment date); SYT call assumption 07/25/2027 @100 |
| Tranche stack (MV) | A1R 307.5M @4.977 · A2R 20M @5.267 · BR 52.5M @5.367 · CR 30M @5.617 · D1R 27.5M @6.667 · D2R 7.5M @7.817 · ER 15M @9.667 · F 0.5M @13.747 · SUB 35.9M @0; total $496.4M; Orig=Curr (no amortization → reinvestment ongoing); derived spreads vs TSFR3M 3.656: 132/161/171/196/301/416/601/1009 bps (V7 verify) |
| Waterfall (PoP files) | Interest: 34 steps (fees → A1R → A2R → BR → **AB tests** → C int → C tests → C deferred → **D1R then D2R** int → **shared D tests** → D deferreds → E int/tests/deferred → F → sub-mgmt fee → **Interest Diversion (step 27)** → equity IRR/incentive → SUB). Principal: 36 steps incl. senior interest make-whole, test cures, **reinvest-during / reinvest-after / Note Payment Sequence**. EoD: fully sequential by class |
| Bloomberg curve | CFT Index Rates: TSFR3M 3.65621 → ~3.696 (flat); SOFRRATE 3.63 (= SYT reinv rate); PRIME 6.75 |
| CLP panel | 35 monthly columns 05/2023–05/2026: WA margin 3.517→3.011; WAC 8.55→6.61; S&P CCC 0.35→6.93; cov-lite 73→53; deal-level default spikes (1.01 06/2025 etc.). Exhibit-grade history; NOT a rho cohort panel |
| Tranche mark | BR SYT price 94.81 (settle 6/22/26); other classes to collect (V8) |
| Krish notes | CDR↔WAL parabolic (OC-test acceleration past trip); CDR↔yield ≈ 0 pre-trigger — Phase-2 teaching hooks |

v1 facts (tape stats, cohort prices, TRIG values, tie-outs, LABL, hazard illustration) unchanged — see analytics CSV.

## 3a. Code facts (from the opened distribution — decisive for the rewrite)
- **Engine shape**: CLO.py is an ANNUAL-step, 5-year, Vasicek one-factor, attach/detach
  loss-clipping engine (no cash waterfall, no reinvestment). It therefore **cannot reproduce the
  CFT monthly waterfall outputs — building that fidelity IS the student rewrite**; the current
  engine is the scaffold and the dependence-experiment vehicle, not the mimic tool.
- **Trigger semantics**: fires on cumulative collateral LOSS ≥ `trigger_level` (fraction of par).
  OC-ratio triggers were converted (L* = 1 − T·D_g/P0: AB 6.09%, C 5.01%, D 3.78%, E 2.59%,
  diversion 2.12%). The live loader's fallback fills trigger_level from raw OC ratios (~1.2 —
  can never fire): flagged V10 for the rewrite.
- **Unit traps handled**: reference_rate/coupon_floor are DECIMALS (stale 5.25% default silently
  fills blanks — overridden with 0.03656 from the CFT curve); spreads/DM in bps; DM is required
  numerically for pricing (par-DM approximation applied, dm_source flag, V9); maturity int-rounded.
- **Validation chain**: staging normalizes via generous alias maps and enforces required columns;
  the live loader validates that manager-report tranches cover every dim tranche name (hence
  per-class manager rows) and that attach/detach/trigger_level are numeric.
- **Third route exists**: `public_bdc_clo_case_study` (SEC-filing BDC CLO with an observed cohort
  panel and calibrated rho) — the public demonstration of the calibrated path; ARES stays
  explicit-rho. Distribution also contains provenance manifests, the air-gap playbook,
  RECIPIENT_BLOOMBERG_INPUTS_REQUIRED.md, R/MATLAB ports, and a notebook.

## 4. Decision log (additions in v2)
10. **Reference rate (mimic mode)** = Bloomberg's own CFT curve (TSFR3M 3.656 start), not an external pull — mimicry requires their assumptions.
11. **Waterfall source** = PoP spreadsheets (Bloomberg DES/CFT) transcribed to the model config; Periodic Report remains confirming source 2. D1R→D2R sequential; shared Class D tests (V1 closed).
12. **Tranche stack** = MV overview (single source, filled); attach/detach loss-basis vs collateral par (A1R detach 1.0088 correctly >1); per-class spread/index inference flagged V7.
13. **CFT setting echoes are not data**: the 20 CPR / severity 0 visible in exports are the students' terminal settings; never treat as realized inputs.
14. **Phase gate**: no extension results into the manuscript until Phase-1 mimicry passes plan tolerances (STUDENT_WORKFLOW.md).
15. **Trigger conversion** to loss basis per §3a (static approximation, documented).
16. **DM = spread par approximation** (required numerically; refine via V9).
17. **reference_rate filled** = 0.03656 (CFT curve) — mimic mode; never leave blank (silent 5.25% default).
18. **maturity_years filled** with provisional values (int-rounding makes date drift immaterial).
Decisions 1–9 (S&P standardization, cohort proxies, PD/rho/LGD/CPR conventions, two-source, OC/IC-as-benchmark, hygiene) unchanged.

## 5. Open items
exception_report.md v2 is authoritative: BLOCKING E2/E3/E5/E7/**E8 (zip password)**; VERIFY V2–V8.

## 6. Standards for the next assistant
Unchanged from v1 (never invent parameters; provenance; two-source; repair-table; plan's
do-not-claim list; verify sums before citing). Add: keep licensed derivatives out of the public
repo even in "small" form (screenshots included); treat CFT/SYT setting echoes per decision 13.

## 7. Ready-to-paste Comment-file block
```
Data-readiness update v2 2026-07-02.

Student Bloomberg bundle ingested (73 files). Tranche export filled from MV overview
(9 classes, $496.4M, attach/detach loss-basis, derived spreads pending per-class
verification). Waterfall step lists transcribed source: Interest/Principal/EoD PoP
spreadsheets (D1R before D2R, shared Class D tests — confirmed). Collateral period
pinned to 05/2026 via CLP panel tie; Bloomberg pull 2026-06-18; SYT settle 2026-06-22;
payment day 25th. Mimic targets catalogued: CFT AdvExports 2/4/8/12 CDR (per-class
cash flows, trigger paths, per-step PoP dollars, index curve TSFR3M 3.656), SYT per
class (BR 94.81), price-matrix JPGs. CLP 35-month history = exhibits, not a rho panel;
rho stays explicit. v3: code zip opened; package aligned to real schemas
(dim_clo_tranche with loss-basis trigger conversion, per-class manager rows,
scenario in model schema, default-event file, units fixed, reference_rate 0.03656,
DM par-approximation). Verified: staging writes all 7 contract files; live run
gates exactly on annual_pd/annual_cpr; smoke tests 7/7. Remaining blockers:
annual_pd, annual_cpr, lgd_base, rho values, determination date. Key rewrite
facts: annual-step loss-clipping engine cannot reproduce CFT waterfall (that is
the student task); trigger-semantics fillna gap flagged V10.
```

## 8. Thread digest (v2 delta)
v1 digest stands. New: student bundle revealed the full Bloomberg analytics layer (CFT/SYT/
price matrices) — reframing the live run as reproduce-then-extend; MV filled the stack; PoP
files settled the waterfall; CLP pinned the as-of period; trustee documents remain the only
outstanding source family; code zip arrived encrypted (password requested).
