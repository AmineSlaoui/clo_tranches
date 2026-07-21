# Deal Selection Memo — ARES 2023-68A

**Status:** selected and substantially validated. **Handling: LOCAL ONLY** — derived from
licensed Bloomberg exports and restricted-distribution trustee documents; do not commit
to the public repository (per BLOOMBERG_AIRGAP_PLAYBOOK and the bundle-review handling rules).

| Field | Value |
| --- | --- |
| Selected deal | ARES 2023-68A (post-reset structure) |
| Bloomberg reference | Collateral tape and TRIG panel pulled via the Class BR security pages ("ARES 23-68A BR Mtge" / "ARES 23-68A BR TRIG") |
| Manager | Ares CLO Management LLC |
| Deal type | Broadly syndicated loan CLO (USD) — meets selection criteria |
| Vintage | Original close April 2023 (classes A-1…F, Sub); reset/refinanced to A1R, A2R, BR, CR, D1R, D2R, ER, F, SUB |
| Status | Active; reinvestment period believed ongoing (WAL test "starts 08/2029" on TRIG panel — confirm reinvestment end date from trustee report) |
| Collateral count | 415 active positions, $492,060,794 current par |
| Tranche count | 9 classes (see bbg_clo_tranche_export.csv template) |
| As-of date | Collateral period **pinned to 05/2026** (tape ties CLP 05/2026 column exactly); Bloomberg pull 2026-06-18; SYT settle 2026-06-22; payment day 25th. Determination date from Monthly report still to record. |

## Reason selected
Loan-level collateral coverage on Bloomberg is near-complete and internally consistent:
per-loan price on 409/415 rows (98.5% of par), three industry schemes, dual-agency ratings
(~99.5%), per-loan S&P recovery rates, coupon/spread/floor/maturity complete. Tape-derived
statistics tie to the Bloomberg TRIG panel to the decimal on fixed-rate share (2.70/2.7),
non-US share (3.9/3.9), WAS (3.01/3.0), and weighted recovery (38.73/38.74), confirming a
single coherent snapshot. Trustee coverage exists: U.S. Bank Monthly_Report_05_26
(portfolio, OC/IC, principal activity, rating detail) and Periodic_Report_05_25_26
(Schedule of Payments Pursuant to the Indenture — the operative waterfall — plus expected
note payment detail).

## Known entitlement / coverage gaps
1. **No as-of date recorded** on any Bloomberg export — blocking; must be entered in the manifest.
2. **6 unpriced loans** (~1.5% of par) — proxied at rating-cohort WA; first check
   purchases/sales in the Monthly report (Clarios TLB 01/25 likely an identifier-mapping gap).
3. **2 loans unrated by both agencies** (University Support Services, Entrata) — rating rule
   required; check the Monthly report rating-detail section for estimated ratings.
4. **No per-loan PD/CPR** from Bloomberg — populated by documented overlays per
   field_dictionary.csv (DRSK confirmed non-functional at deal level; works per obligor).
5. **No cohort default panel** — rho sufficiency test cannot be attempted; run is
   **explicit-rho mode**. This is structural (single-snapshot data), not an entitlement gap.
6. **Reset offering supplement not located** (144A/Reg S restricted). Downgraded from
   blocking to nice-to-have: the trustee Periodic Report supplies the operative structure;
   two-source rule met via the market_value_overview CSV. Breach-contingent waterfall
   mechanics remain flagged assumptions.
7. **Manager-report history**: only the current Monthly report is in hand; the plan prefers
   24–36 months — open pull task.


## Student bundle inventory (ARES_2023-68A-LLM-small-final, 73 files)
CFT AdvExports at 2/4/8/12 CDR (full projected deal: per-class cash flows, triggers, PoP dollars,
index curve) · SYT per class + Krish notes · CLP Summary/Moody/S&P (35-month history) · CLC margin
distribution · DES per-class screenshots + **Interest/Principal/EoD PoP spreadsheets** (waterfall) ·
MV overview (tranche stack) + Portfolio Statistics.pdf (image-only) · PRICE MATRIX 36 JPGs ·
LLD tape · TRIG workbooks · OM (restricted). **Not included ("new data")**: trustee
Monthly_Report_05_26 and Periodic_Report_05_25_26, TRIG CSV, trustee OC/IC screenshot.
Nit: folder name typo "AREA 2023-68A" in PRICE MATRIX — fix in manifest.
