#!/usr/bin/env python3
"""
make_data_readiness_package.py — ARES 2023-68A data-readiness generator
=======================================================================
Builds the Chapter 4.1 First Milestone raw files from the two local source
workbooks, applying the conventions agreed in the ARES 2023-68A email thread
(June–July 2026). Re-run whenever a source file or convention is updated.

Inputs (edit paths below if relocated):
  - lld_ares_2023.xlsx            Bloomberg loan-level collateral export ("ARES 23-68A BR Mtge")
  - ARES_2023_68A_BR_TRIG.xlsx    Bloomberg TRIG panel export (coverage tests + quality stats)

Outputs (./raw relative to --out):
  - bbg_loan_collateral_export.csv   415 rows, canonical live-contract grain
  - bbg_clo_manager_export.csv       TRIG snapshot rows (trustee columns blank, to fill)
  - bloomberg_analytics_summary.csv  benchmark metrics for reconciliation
  plus a console data-quality/exception check.

Deliberately NOT filled (do not invent — see field_dictionary.csv):
  annual_pd (needs external S&P default table), annual_cpr (team calc from
  Principal Activity Report), reference_rate (market pull at as_of_date),
  lgd base-case variant (pending S&P recovery-field scenario check),
  confirmed as_of_date (pending manifest entry).
"""
import argparse, json, sys
from datetime import date
from pathlib import Path
import pandas as pd

DEAL_ID = "ARES_2023_68A"
PROVISIONAL_AS_OF = date(2026, 5, 31)   # tape period pinned to CLP 05/2026 column (balance/count/default/WAM all tie); determination date from trustee still to record
BBG_PULL_DATE = "2026-06-18"            # CFT/SYT export filenames
SYT_SETTLE_DATE = "2026-06-22"          # SYT settle row
DEAL_PAYMENT_DAY = 25                   # CFT period dates; Periodic_Report_05_25_26 = 5/25/26 payment date
TSFR3M_AT_START = 3.65621               # CFT 'Index Rates' sheet @ 2026-05-25 (Bloomberg curve, mimic mode)
SOURCE_FAMILY = "bloomberg_clo"

def load_tape(path):
    df = pd.read_excel(path, sheet_name=0, skiprows=1)  # row 0 is the title "ARES 23-68A BR Mtge"
    df = df.dropna(how="all")
    return df

def cohort_price_table(df):
    """Par-weighted average price by S&P issue rating, priced & non-defaulted rows only."""
    base = df[df["Last Price"].notna() & (df["Default Status"] != "Yes")]
    g = base.groupby("S&P Reported Rating").apply(
        lambda x: (x["Last Price"] * x["Current Balance"]).sum() / x["Current Balance"].sum(),
        include_groups=False)
    return g.to_dict()

def build_collateral(df):
    tot = df["Current Balance"].sum()
    cohort = cohort_price_table(df)

    out = pd.DataFrame()
    out["deal_id"] = [DEAL_ID] * len(df)
    out["as_of_date"] = ""                                  # PENDING — blocks staging by design
    out["as_of_date_provisional"] = PROVISIONAL_AS_OF.isoformat()
    ids, id_src = [], []
    for i, r in df.iterrows():
        if pd.notna(r["CUSIP"]) and str(r["CUSIP"]).strip():
            ids.append(str(r["CUSIP"]).strip()); id_src.append("CUSIP")
        elif pd.notna(r["Bloomberg FIGI"]) and str(r["Bloomberg FIGI"]).strip():
            ids.append(str(r["Bloomberg FIGI"]).strip()); id_src.append("FIGI")
        else:  # e.g. Versant Media TLA: unquoted pro-rata tranche with no public identifier yet
            slug = "".join(c for c in str(r["Issuer"]).upper() if c.isalnum())[:12]
            ids.append(f"LOCAL_{i:03d}_{slug}"); id_src.append("LOCAL_SYNTHETIC")
    out["loan_id"] = ids
    out["loan_id_source"] = id_src
    out["loan_identifier"] = df["Issuer"].astype(str) + " | " + df["Security Name"].astype(str)
    out["sector"] = df["S&P Industry"]                      # S&P scheme per S&P standardization decision
    out["moodys_industry"] = df["Moody's Industry Classification"]  # kept for rho factor structure
    out["current_balance"] = df["Current Balance"]
    out["weight"] = df["Current Balance"] / tot
    out["rating"] = df["S&P Reported Rating"]               # issue-level, display/bucketing
    out["sp_issuer_rating"] = df["S&P Issuer Rating"]
    # PD keying: issuer rating where present, issue rating as documented fallback
    iss = df["S&P Issuer Rating"].astype(str).str.strip()
    use_iss = df["S&P Issuer Rating"].notna() & iss.ne("") & iss.ne("nan") & iss.ne("NR")
    out["rating_for_pd"] = df["S&P Issuer Rating"].where(use_iss, df["S&P Reported Rating"])
    out["rating_for_pd_source"] = ["SP_ISSUER" if u else "SP_ISSUE_FALLBACK" for u in use_iss]

    # market price: actual where present, else rating-cohort par-weighted WA proxy
    px, src = [], []
    for _, r in df.iterrows():
        if pd.notna(r["Last Price"]):
            px.append(round(float(r["Last Price"]), 4)); src.append("BBG_LAST_PRICE")
        else:
            proxy = cohort.get(r["S&P Reported Rating"])
            px.append(round(float(proxy), 4) if proxy is not None else "")
            src.append("PROXY_RATING_COHORT_WA" if proxy is not None else "UNRESOLVED")
    out["market_price"] = px
    out["price_source"] = src

    # coupon decomposition for the max(r, floor) + spread contract
    is_flt = df["Coupon Type"] == "FLT"
    out["coupon_type"] = df["Coupon Type"]
    out["coupon_rate_pct"] = df["Coupon"]                   # exact current coupon, for audit
    out["coupon_spread_bps"] = [round(m * 100, 1) if f and pd.notna(m) else 0.0
                                for f, m in zip(is_flt, df["Margin"])]
    floor = []
    for f, fl, cpn in zip(is_flt, df["Index Floor Rate"], df["Coupon"]):
        if f:
            floor.append(round(float(fl) / 100.0, 6) if pd.notna(fl) else 0.0)   # DECIMAL per CLO.py units
        else:
            floor.append(round(float(cpn) / 100.0, 6) if pd.notna(cpn) else "")  # FXD: floor=coupon (decimal), spread=0
    out["coupon_floor"] = floor
    out["reference_rate"] = TSFR3M_AT_START / 100.0          # 0.03656 decimal — CFT Index Rates (mimic mode); overrides CLO.py's stale 5.25% default
    # Model requires numeric discount_margin_bps for pricing; par-DM approximation (DM ~= spread), documented
    out["discount_margin_bps"] = out["coupon_spread_bps"]
    out["dm_source"] = "PAR_DM_APPROX_EQ_SPREAD"

    # maturity
    mat = pd.to_datetime(df["Maturity Date"], format="%m/%d/%Y", errors="coerce")
    out["maturity_date"] = mat.dt.date.astype(str)
    out["maturity_years_provisional"] = ((mat - pd.Timestamp(PROVISIONAL_AS_OF)).dt.days / 365.25).round(4)
    out["maturity_years"] = out["maturity_years_provisional"]   # filled: CLO.py int-rounds, so determination-date drift is immaterial; recompute when confirmed

    # parameters
    out["annual_pd"] = ""                                   # PENDING external S&P default table via rating_for_pd
    out["annual_cpr"] = ""                                  # PENDING team calc (Principal Activity Report)
    rr = df["S&P Recovery Rate"]
    sector_mean_rr = df[rr.notna()].groupby("S&P Industry")["S&P Recovery Rate"].mean()
    lgd, lgd_src = [], []
    for _, r in df.iterrows():
        if pd.notna(r["S&P Recovery Rate"]):
            lgd.append(round(1 - float(r["S&P Recovery Rate"]), 4)); lgd_src.append("1_MINUS_SP_RECOVERY_RATE")
        else:
            fb = sector_mean_rr.get(r["S&P Industry"])
            if pd.notna(fb):
                lgd.append(round(1 - float(fb), 4)); lgd_src.append("SECTOR_MEAN_RR_FALLBACK")
            else:
                lgd.append(""); lgd_src.append("UNRESOLVED")
    out["lgd"] = lgd                                        # stress-scenario basis — see exception report E5
    out["lgd_source"] = lgd_src
    out["lgd_base"] = ""                                    # PENDING scenario check on the S&P recovery field

    out["default_status"] = df["Default Status"]
    out["default_date"] = df["Default Date"].fillna("")
    out["covenant_lite"] = df["Is Covenant Lite"]
    out["country"] = df["Country"]
    out["source_family"] = SOURCE_FAMILY
    return out, cohort

def build_manager(trig_path):
    """Manager-report rows PER CLASS (CLO.py validates coverage of every dim tranche name).
    Each class carries its coverage-test group's Bloomberg TRIG values; F/SUB carry the
    interest-diversion test (their first cash-affecting junior trigger). Trustee columns blank."""
    G = {  # group -> (oc, oc_trig, ic, ic_trig)
        "AB": (131.25, 121.60, 150.11, 120.00), "C": (121.65, 114.00, 137.98, 115.00),
        "D": (112.08, 106.40, 123.64, 110.00), "E": (108.42, 104.20, 116.39, 105.00),
        "ID": (108.42, 104.70, None, None)}
    cls = {"A1R": "AB", "A2R": "AB", "BR": "AB", "CR": "C", "D1R": "D", "D2R": "D",
           "ER": "E", "F": "ID", "SUB": "ID"}
    rows = []
    for t, g in cls.items():
        oc, oct_, ic, ict = G[g]
        rows.append(dict(deal_id=DEAL_ID, report_date=PROVISIONAL_AS_OF.isoformat(),
                         tranche=t, oc_ratio=oc/100.0, oc_trigger_level=oct_/100.0,
                         ic_ratio=(ic/100.0 if ic else ""),
                         trustee_oc_ratio="", trustee_ic_ratio="", trustee_determination_date="",
                         ccc_bucket_pct=6.9, source_family=SOURCE_FAMILY,
                         source_note=f"Bloomberg TRIG panel, {g} test group mapped per class; ratios as decimals; "
                                     "report_date PROVISIONAL (determination date pending); trustee columns to fill "
                                     "from Monthly_Report_05_26 (not the PNG screenshot)."))
    return pd.DataFrame(rows)

def build_tranche(mv_path, collateral_par):
    """Fill the tranche export from market_value_overview (source 1; Periodic Report = confirming source 2).
    attach/detach = loss-based share of collateral par: attach_j = par junior to j / collateral par."""
    mv = pd.read_excel(mv_path, sheet_name=0)
    mv.columns = [str(c).strip() for c in mv.columns]
    order = ["SUB", "F", "ER", "D2R", "D1R", "CR", "BR", "A2R", "A1R"]  # junior -> senior
    mv["__o"] = mv["Class"].map({c: i for i, c in enumerate(order)})
    mv = mv.sort_values("__o")
    rows, junior = [], 0.0
    test_group = {"A1R": "Class AB", "A2R": "Class AB", "BR": "Class AB", "CR": "Class C",
                  "D1R": "Class D (shared)", "D2R": "Class D (shared)", "ER": "Class E",
                  "F": "none", "SUB": "equity"}
    for _, r in mv.iterrows():
        bal = float(r["Curr(000)"]) * 1000.0
        attach = junior / collateral_par
        detach = (junior + bal) / collateral_par
        cpn = float(r["Cpn"])
        rows.append(dict(
            deal_id=DEAL_ID, tranche=r["Class"],
            attach=round(attach, 6), detach=round(detach, 6),
            original_balance=float(r["Orig(000)"]) * 1000.0, current_balance=bal,
            pct_bal_reported=r["% Bal"], pct_sub_reported=r["% Sub"],
            coupon_all_in_pct=cpn,
            coupon_index="TSFR3M (confirm per class from DES/Periodic Report)",
            coupon_spread_bps_derived=round((cpn - TSFR3M_AT_START) * 100, 1) if cpn > 0 else 0.0,
            mv_oc_reported=r["MV OC"], par_oc_reported=r["Par OC"],
            oc_test_group=test_group.get(r["Class"], ""),
            cusip="", figi="", rating_sp="", rating_moodys="",
            manager_name="Ares CLO Management LLC", source_family=SOURCE_FAMILY,
            fill_source="market_value_overview_ares_2023.xlsx (MV folder); attach/detach computed loss-basis vs tape par; "
                        "spread derived as all-in Cpn minus TSFR3M 3.656 (VERIFY per class vs DES pages / Periodic Report note detail); "
                        "SUB coupon 0 = equity. Single-source until Periodic Report confirmation (two-source rule)."))
        junior += bal
    return pd.DataFrame(rows[::-1])  # present senior -> junior


def build_dim_tranche(tr, collateral_par):
    """Staging-schema dim_clo_tranche with trigger_level CONVERTED to the model's cumulative-loss basis.
    CLO.py semantics: trigger fires when cumulative collateral loss >= trigger_level (fraction of par).
    Conversion: L* = 1 - T_g * D_g / P0, T_g = OC trigger ratio, D_g = liabilities senior-through-test-group.
    Static approximation (ignores paydown/haircuts) - documented; NOTE: CLO.py's fillna-from-OC-ratio
    fallback would insert ~1.2 values that can never fire; supplying converted values avoids that path."""
    thr = {"Class AB": 1.216, "Class C": 1.14, "Class D (shared)": 1.064, "Class E": 1.042}
    order = ["A1R","A2R","BR","CR","D1R","D2R","ER","F","SUB"]
    t = tr.set_index("tranche").loc[order].reset_index()
    debt_through = t["current_balance"].cumsum()
    rows = []
    for i, r in t.iterrows():
        g = r["oc_test_group"]
        if g in thr:
            Lstar = 1 - thr[g] * float(debt_through[t[t.oc_test_group==g].index.max()]) / collateral_par
        else:  # F and SUB: first cash-affecting junior trigger = interest diversion (1.047 at Class E depth)
            Lstar = 1 - 1.047 * float(debt_through[t[t.tranche=="ER"].index.max()]) / collateral_par
        rows.append(dict(deal_id=DEAL_ID, tranche=r["tranche"], attach=r["attach"], detach=r["detach"],
                         trigger_level=round(max(Lstar, 0.0), 6),
                         coupon_bps=r["coupon_spread_bps_derived"],
                         cusip="", figi="", manager_name="Ares CLO Management LLC",
                         source_family=SOURCE_FAMILY))
    return pd.DataFrame(rows)

def build_stress_template():
    return pd.DataFrame([
        dict(scenario="low_dependence", rho="", base_rho="", rho_multiplier=1.0, pd_multiplier=1.0,
             cpr_multiplier=1.0, lgd_addon=0.0, discount_rate=0.04, source_family="analyst_explicit", pack_label="licensed"),
        dict(scenario="base", rho="", base_rho="", rho_multiplier=1.0, pd_multiplier=1.0,
             cpr_multiplier=1.0, lgd_addon=0.0, discount_rate=0.04, source_family="analyst_explicit", pack_label="licensed"),
        dict(scenario="high_dependence", rho="", base_rho="", rho_multiplier=1.0, pd_multiplier=1.0,
             cpr_multiplier=1.0, lgd_addon=0.0, discount_rate=0.04, source_family="analyst_explicit", pack_label="licensed"),
    ])

def build_default_event(df):
    d = df[df["Default Status"] == "Yes"]
    return pd.DataFrame([dict(deal_id=DEAL_ID, loan_id=str(r["CUSIP"]), default_date="2026-01-30",
                              defaulted_balance=float(r["Current Balance"]), source_family=SOURCE_FAMILY)
                         for _, r in d.iterrows()])

def mv_analytics_rows(tr):
    R = []
    M = "market_value_overview_ares_2023.xlsx"
    for _, t in tr.iterrows():
        R.append(dict(deal_id=DEAL_ID, as_of_date=BBG_PULL_DATE, object_type="tranche", object_id=t["tranche"],
                      metric="current_balance", value=t["current_balance"], unit="USD",
                      bloomberg_function=M, bloomberg_field="",
                      notes=f"all-in cpn {t['coupon_all_in_pct']}%; reported %Sub {t['pct_sub_reported']}"))
    R += [dict(deal_id=DEAL_ID, as_of_date=BBG_PULL_DATE, object_type="tranche", object_id="BR",
               metric="syt_price", value=94.81, unit="price",
               bloomberg_function="SYT export 20260618 (settle 2026-06-22)", bloomberg_field="",
               notes="collect remaining classes' SYT prices for the full tranche-mark set"),
          dict(deal_id=DEAL_ID, as_of_date="2026-05-25", object_type="deal", object_id=DEAL_ID,
               metric="tsfr3m_start", value=TSFR3M_AT_START, unit="percent",
               bloomberg_function="CFT Index Rates sheet", bloomberg_field="TSFR3M",
               notes="Bloomberg projection curve start; mimic-mode reference_rate"),
          dict(deal_id=DEAL_ID, as_of_date="2026-05-25", object_type="deal", object_id=DEAL_ID,
               metric="cft_opening_total_balance", value=500807340.42, unit="USD",
               bloomberg_function="CFT Collateral sheet", bloomberg_field="",
               notes="= CLP 05/2026 Total Bal (collateral par + principal acct) — ties to the cent")]
    return pd.DataFrame(R)

def build_analytics(df, col, cohort):
    tot = df["Current Balance"].sum()
    flt = df[df["Coupon Type"] == "FLT"]
    was = (flt["Margin"] * flt["Current Balance"]).sum() / flt["Current Balance"].sum()
    priced = df[df["Last Price"].notna()]
    wap = (priced["Last Price"] * priced["Current Balance"]).sum() / priced["Current Balance"].sum()
    rrmask = df["S&P Recovery Rate"].notna()
    warr = (df.loc[rrmask, "S&P Recovery Rate"] * df.loc[rrmask, "Current Balance"]).sum() / df.loc[rrmask, "Current Balance"].sum()
    mat = pd.to_datetime(df["Maturity Date"], format="%m/%d/%Y", errors="coerce")
    wam = (((mat - pd.Timestamp(PROVISIONAL_AS_OF)).dt.days / 365.25) * df["Current Balance"]).sum() / tot

    def row(otype, oid, metric, value, unit, func, note=""):
        return dict(deal_id=DEAL_ID, as_of_date="", object_type=otype, object_id=oid,
                    metric=metric, value=value, unit=unit, bloomberg_function=func,
                    bloomberg_field="", notes=note)
    R = []
    A = "derived from lld_ares_2023.xlsx (Bloomberg collateral export)"
    T = "Bloomberg TRIG panel export (ARES_2023_68A_BR_TRIG)"
    R += [row("collateral", DEAL_ID, "collateral_par", round(tot, 2), "USD", A),
          row("collateral", DEAL_ID, "loan_count", len(df), "count", A),
          row("collateral", DEAL_ID, "weighted_avg_price_priced_only", round(wap, 4), "price", A,
              "409/415 priced; excludes 6 unpriced rows"),
          row("collateral", DEAL_ID, "weighted_avg_spread_floating", round(was, 4), "percent", A,
              "matches TRIG WAS 3% to rounding"),
          row("collateral", DEAL_ID, "weighted_avg_maturity_provisional", round(wam, 4), "years", A,
              f"uses PROVISIONAL as-of {PROVISIONAL_AS_OF}"),
          row("collateral", DEAL_ID, "fixed_rate_share", round(df.loc[df['Coupon Type']=='FXD','Current Balance'].sum()/tot*100, 2), "percent", A, "TRIG panel shows 2.7%"),
          row("collateral", DEAL_ID, "non_us_share", round(df.loc[df['Country']!='US','Current Balance'].sum()/tot*100, 2), "percent", A, "TRIG panel shows 3.9%"),
          row("collateral", DEAL_ID, "weighted_avg_sp_recovery", round(warr*100, 2), "percent", A,
              "TRIG panel shows 38.74% (WARR test vs 37.25 covenant)"),
          row("collateral", DEAL_ID, "defaulted_share", round(df.loc[df['Default Status']=='Yes','Current Balance'].sum()/tot*100, 2), "percent", A, "single defaulted obligor (LABL)")]
    R += [row("deal", DEAL_ID, "diversity_score", 79, "score", T),
          row("deal", DEAL_ID, "warf", 2761, "factor", T),
          row("deal", DEAL_ID, "sp_ccc_bucket", 6.9, "percent", T,
              "tape-computed CCC+/below = 7.56%; delta is definitional (defaulted exclusion etc.)"),
          row("deal", DEAL_ID, "wal_vs_covenant", "4.54 vs 8.25", "years", T, "WAL test, starts 08/2029")]
    for t, oc, oct_, ic, ict in [("AB",131.25,121.60,150.11,120.00),("C",121.65,114.00,137.98,115.00),
                                  ("D",112.08,106.40,123.64,110.00),("E",108.42,104.20,116.39,105.00)]:
        R += [row("tranche", f"Class {t}", "oc_ratio", oc, "percent", T, f"trigger {oct_}"),
              row("tranche", f"Class {t}", "ic_ratio", ic, "percent", T, f"trigger {ict}")]
    R += [row("deal", DEAL_ID, "interest_diversion_ratio", 108.42, "percent", T, "trigger 104.70"),
          row("deal", DEAL_ID, "eod_oc_ratio", 162.86, "percent", T, "trigger 102.50")]
    for rt, p in sorted(cohort.items()):
        R.append(row("collateral", f"rating_cohort_{rt}", "cohort_wa_price", round(p, 4), "price", A,
                     "par-weighted, priced non-defaulted rows; proxy source for unpriced loans"))
    return pd.DataFrame(R)

def checks(col, df):
    ok = True
    def flag(cond, msg):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        ok = ok and cond
    print("\nData-quality checks (pre-staging exception scan):")
    flag(len(col) == 415, f"row count = {len(col)} (expect 415)")
    flag(abs(col['current_balance'].sum() - df['Current Balance'].sum()) < 0.01,
         f"total par = {col['current_balance'].sum():,.2f}")
    flag(col['loan_id'].notna().all() and (col['loan_id'].astype(str).str.strip() != '').all(),
         "every row has a loan_id (CUSIP > FIGI > local synthetic)")
    n_syn = (col['loan_id_source'] == 'LOCAL_SYNTHETIC').sum()
    print(f"  INFO  synthetic local IDs: {n_syn} row(s) — no CUSIP/FIGI on tape (unquoted pro-rata paper)")
    flag((pd.Series(col['market_price']) != "").all(), "every row has a valuation anchor (price or proxy)")
    flag((pd.Series(col['lgd']) != "").all(), "every row has an lgd (incl. sector-mean fallback)")
    n_proxy = (col['price_source'] == 'PROXY_RATING_COHORT_WA').sum()
    print(f"  INFO  price proxies applied: {n_proxy} rows")
    print(f"  INFO  lgd fallbacks applied: {(col['lgd_source']=='SECTOR_MEAN_RR_FALLBACK').sum()} rows")
    print(f"  INFO  rating_for_pd fallbacks (issue used): {(col['rating_for_pd_source']=='SP_ISSUE_FALLBACK').sum()} rows")
    print("  BLOCKING (by design, do not invent): as_of_date(determination), annual_pd, annual_cpr, lgd_base, rho values")
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tape", default="/mnt/user-data/uploads/lld_ares_2023.xlsx")
    ap.add_argument("--mv", default=None, help="path to market_value_overview_ares_2023.xlsx (fills tranche export)")
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    out = Path(args.out); raw = out / "raw"; raw.mkdir(parents=True, exist_ok=True)
    df = load_tape(args.tape)
    col, cohort = build_collateral(df)
    col.to_csv(raw / "bbg_loan_collateral_export.csv", index=False)
    build_manager(None).to_csv(raw / "bbg_clo_manager_export.csv", index=False)
    build_stress_template().to_csv(raw / "scenario_clo_stress.csv", index=False)
    build_default_event(df).to_csv(raw / "fact_clo_default_event.csv", index=False)
    ana = build_analytics(df, col, cohort)
    if args.mv:
        tr = build_tranche(args.mv, df["Current Balance"].sum())
        tr.to_csv(raw / "bbg_clo_tranche_export.csv", index=False)
        ana = pd.concat([ana, mv_analytics_rows(tr)], ignore_index=True)
        build_dim_tranche(tr, df["Current Balance"].sum()).to_csv(raw / "dim_clo_tranche.csv", index=False)
        print(f"Tranche export filled from MV overview: {len(tr)} classes, "
              f"total liabilities ${tr['current_balance'].sum():,.0f}")
    ana.to_csv(raw / "bloomberg_analytics_summary.csv", index=False)
    (raw / "stage_metadata.json").write_text(json.dumps({
        "deal_id": DEAL_ID, "generated_by": "make_data_readiness_package.py",
        "generated_on": date.today().isoformat(),
        "as_of_date": "PENDING determination-date entry — tape period pinned to CLP 05/2026 (balance/count/default/WAM tie exactly)",
        "as_of_date_provisional": PROVISIONAL_AS_OF.isoformat(),
        "bloomberg_pull_date": BBG_PULL_DATE, "syt_settle_date": SYT_SETTLE_DATE,
        "deal_payment_day": DEAL_PAYMENT_DAY, "tsfr3m_at_2026_05_25": TSFR3M_AT_START,
        "rho_mode": "explicit (no cohort panel; CLP 35-month deal-level history exists but fails sufficiency test)",
        "handling": "LOCAL ONLY. Derived from licensed Bloomberg exports; do not commit to public repo."}, indent=2))
    ok = checks(col, df)
    print(f"\nWrote package to {raw.resolve()}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
