# Student Workflow — Mimic Bloomberg, then Extend
Course goal: download and process Bloomberg data, rewrite the code so it **reproduces
Bloomberg's own analyses**, and only then extend the analysis. Nothing is publishable as a
current empirical claim about ARES; all licensed material stays local.

## Read first — what the current code can and cannot do
The shipped CLO.py is an annual-step, 5-year, one-factor **loss-clipping** engine: no cash
waterfall, no reinvestment, no monthly periods. It **cannot** reproduce the CFT sheets as-is.
That is the point of the course: Phase 1 means **rewriting/extending the engine** (monthly
periods, the PoP step lists, test-cure and diversion mechanics, reinvestment toggle) until it
reproduces Bloomberg's outputs. Use the existing engine as the scaffold and as the Phase-2
dependence-experiment vehicle. Known code gap to fix on the way: the live loader can fill
`trigger_level` from raw OC ratios (~1.2) that can never fire on a loss fraction (V10).

## Phase 1 — Mimic (prove the rewritten code against Bloomberg)
Reproduce, in this order (each target is a file already in the bundle):

1. **Static composition** — collateral par $492,060,794, 415 loans, WAS 3.01, WA price 95.07,
   fixed 2.70%, non-US 3.9%, WARR 38.73 → `bloomberg_analytics_summary.csv`.
   Tolerances (plan §Reconciliation): par exact/<0.1%, count exact, WAS <5bps, price <0.25pt.
2. **Tranche stack** — balances, attach/detach (exact), coupons → `raw/bbg_clo_tranche_export.csv`
   vs MV overview; verify derived spreads per class (V7).
3. **Waterfall engine** — implement the PoP step lists (Interest 34 / Principal 36 / EoD);
   validate per-step dollar flows against the CFT "Interest/Principal Priority of Payments"
   sheets, period by period.
4. **Deal projection under Bloomberg's settings** — for each CDR scenario (2/4/8/12):
   reproduce per-class cash flows (CFT `Bond *` sheets) and trigger paths (`Triggers` sheet:
   Result/Threshold/Value per period). Lock the assumption set to Bloomberg's: curve = CFT
   `Index Rates` (TSFR3M 3.656 start), base 20 CPR, severity/lag as shown, call 07/25/2027 @100,
   settle 2026-06-22, payment day 25. The opening trigger row must equal the TRIG panel.
5. **Tranche pricing** — reproduce SYT price/yield/DM per class under the recorded ladder
   (BR = 94.81 reference); price-matrix JPGs are visual spot checks.

Acceptance = plan §Acceptance Criteria. Differences must be explained, never tuned away
(no hidden parameters; changes visible in run metadata).

## Phase 2 — Extend (only after Phase 1 passes)
- The chapter's dependence experiment on the **real tape**: explicit-rho low/base/high
  (never "calibrated"); tranche EL/VaR/CVaR/trigger frequency/loss-compensation spread.
- Stress vs base LGD runs once `lgd_base` is filled (E5) — quantify the double-counting error.
- Severity/lag and CPR sensitivities beyond Bloomberg's grid; realized-CPR overlay (E3).
- Trustee benchmark reconciliation when the reports arrive (V2).
- Exhibits from the CLP 35-month panel: WA-margin compression 3.517→3.011, CCC-bucket drift,
  the deal's own realized default spikes.
- Krish's SYT observations as motivating questions: the CDR↔WAL parabola (OC-test
  acceleration past the trip point) and why yield is CDR-insensitive pre-trigger for floaters.

## Standing rules
Never invent PD/CPR/LGD/rho/marks/dates (empty + documented beats filled + fabricated);
every number traces to a file/page or named external table; two-source rule for structure;
repair-table workflow for review rounds.
