# Chapter 4.1 Edit Pack — text updates queued per the Narrative Update Rules
Purpose: everything the code+data review implies for the **text**, packaged so the Book2 editor
can apply it in controlled rounds. Manuscript-layer blocks are gated **AT ACCEPTANCE** (live run
passes the plan's reconciliation tolerances); working-layer blocks are safe to **APPLY NOW**.
Nothing here changes public-run claims — those remain correct for the synthetic route.

## Part A — Repair table
| ID | Target note | Observation | Disposition | When |
| --- | --- | --- | --- | --- |
| T1 | L5 4.1.9.2 (Plan) | First Milestone package built and verified end-to-end against the real scripts; blockers reduced to the do-not-invent set | Fixed — paste B1 status addendum | NOW |
| T2 | L4 4.1.9 (Comment) | Provenance for the v1→v3 package work | Fixed — paste HANDOFF_NEXT_MODEL.md §7 block | NOW |
| T3 | L5 4.1.2.6 (Data & Estimation) | Live-route specifics (deal, conventions, fallbacks) now fully known | Drafted — merge B3 with the plan's prescribed post-acceptance paragraph | AT ACCEPTANCE |
| T4 | L5 4.1.2.12 (Model Risk) | New documented approximations: trigger-level static conversion, par-DM fill, stress-basis LGD, silent-default fills (until patch adopted) | Drafted — B4 | AT ACCEPTANCE |
| T5 | L4 4.1.4 (Results) | Live-run section shell with figure/table slots mapped to the engine's outputs | Drafted — B5 | AT ACCEPTANCE |
| T6 | L4 4.1.5 (AI) | The aspirational data-quality agent now exists (exception_report.md) | Drafted — B6 one-liner | AT ACCEPTANCE (low priority) |
| T7 | Manuscript-wide | Checked 4.1.2.3/4.1.2.6/4.1.2.8 against the opened code: descriptions match (annual-step loss-clipping, cumulative-loss triggers, contract fields) | Rebutted — no drift found; no pre-acceptance manuscript edits required | — |
| T8 | Code (not text) | trigger_level OC-ratio backfill bug; silent live-contract default fills | Deferred to author — proposed diff in patches/clo_live_loader_guards.diff (smoke 7/7 with patch; bug demo reproduced) | Author review |

## Part B — Ready-to-paste blocks

### B1 (NOW) — Plan status addendum (append to L5 4.1.9.2)
```
STATUS ADDENDUM 2026-07-03. First Milestone delivered as a local data-readiness package
(collateral 415 rows with documented proxies/fallbacks; dim tranche with loss-basis trigger
conversion; per-class manager rows; scenario/default-event files; field_dictionary; deal memo;
exception report; regeneration script). Verified end-to-end: stage_actual_clo_contract.py
(route bloomberg_market_observed) stages all seven contract files; CLO.py --mode live halts
exactly on the missing numeric annual_pd/annual_cpr — the intended do-not-invent gate; smoke
tests 7/7. Collateral period pinned to 05/2026 (CLP tie); Bloomberg pull 2026-06-18; SYT settle
2026-06-22; payment day 25th. Rho mode: explicit (CLP 35-month deal history fails the cohort
sufficiency test). Remaining blockers: annual_pd (named S&P table), annual_cpr (Principal
Activity calc), lgd_base (scenario check), rho values (named source), determination date.
Reset supplement: downgraded to nice-to-have (MV overview + PoP files + Periodic Report path
satisfy structure sourcing). Course framing recorded: the shipped annual-step engine cannot
reproduce the CFT waterfall — building that fidelity is the student rewrite (Phase 1), with
CFT/SYT/TRIG exports as the reconciliation targets.
```

### B3 (AT ACCEPTANCE) — Data & Estimation, live-route paragraph (merge with the plan's prescribed text)
```
The live route replaces the synthetic tape with the licensed ARES 2023-68A export as of
[DETERMINATION DATE] (415 loans, $492.06M par). Fields carried directly: identifiers, S&P
industry, balances, issue ratings, floating spreads and floors, maturities, and per-loan market
prices (409 rows; the six unpriced positions carry S&P rating-cohort weighted-average proxies,
~1.5% of par, sensitivity ~0.2% of MV). Overlays disclosed in field_dictionary.csv: annual PD
maps the S&P issuer rating (issue fallback on 24 rows) to [S&P DEFAULT STUDY + VINTAGE];
annual CPR is the pool-level realized rate [VALUE] computed from the [PERIOD] Principal
Activity Report (unscheduled principal, quarterly annualization); LGD uses 1 − S&P recovery
rate on its [CONFIRMED SCENARIO] basis with a separate base-case series; the reference rate
(3.656%) and projection curve come from the vendor CFT export to keep the mimicry
assumption-locked; dependence is EXPLICIT at [RHO LOW/BASE/HIGH + SOURCE] — the package
contains no cohort panel, and none can be constructed from a single-date tape, so no
calibrated dependence is claimed. OC trigger ratios are converted to the engine's
cumulative-loss basis (Class E trips first at 2.6% of par, A/B last at 6.1%).
Reconciliation against Bloomberg's TRIG/CFT/SYT outputs met the plan's tolerances with the
following explained deltas: [DELTAS].
```

### B4 (AT ACCEPTANCE) — Model Risk and Limitations, additions
```
Live-route approximations, each visible in the staged contract: (i) trigger levels are static
loss-equivalents of the OC ratios (ignoring paydown and indenture haircuts), so modeled trigger
frequencies are indicative rather than test-exact; (ii) discount margins use the par
approximation DM = spread where loan-level DMs are unobserved; (iii) the S&P recovery field is
a stress-scenario estimate — base-case runs use [BASE LGD SOURCE], and pairing stress LGD with
physical PDs would double-count conservatism; (iv) contract blanks are never invented — the
loader's default fills are surfaced as warnings and recorded in the field dictionary.
```

### B5 (AT ACCEPTANCE) — Results, live-run shell
```
### Live run — ARES 2023-68A (as of [DATE])
[Fig L1] Collateral loss CDF, low vs high dependence · [Fig L2] Tranche loss CDFs (A1R…SUB)
· [Fig L3] Trigger frequencies vs converted thresholds · [Fig L4] Loss-compensation spread vs
market spreads (SYT anchors, BR = 94.81) · [Tbl L1] Tranche summary metrics under
[RHO LOW/BASE/HIGH] · [Tbl L2] Reconciliation vs Bloomberg (tolerance, delta, explanation).
Claims restricted per the do-not-claim list; no current empirical claim about ARES.
```

### B6 (AT ACCEPTANCE, optional) — AI section one-liner
```
(The data-quality agent described here was implemented for the Chapter 4 live package; its
exception report gates the run before the valuation engine starts.)
```
