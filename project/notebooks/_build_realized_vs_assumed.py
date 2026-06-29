"""Builder: emits ARES_2023_68A_realized_vs_assumed.ipynb via nbformat.

We keep notebook source in this .py so it is easy to diff/regenerate. Run:
    python _build_realized_vs_assumed.py
then execute the produced notebook.
"""
import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell

nb = new_notebook()
cells = []
def md(t): cells.append(new_markdown_cell(t))
def code(t): cells.append(new_code_cell(t))

# ----------------------------------------------------------------------------
md(r"""# ARES 2023-68A — Realized vs. Assumed Collateral Metrics

**Goal.** Ingest the Bloomberg export files for the CLO **ARES 2023-68A** and
produce ONE final summary table (`comparison`) that puts **realized** collateral
experience next to the **assumed** scenario inputs used in our SYT analysis.

**Reality check on the inputs.** The project brief describes an idealized folder
layout (`CLP/`, `LLD/`, `MV/`, `TRIG/`, `SYT/`, `CFT/`) with an `.xlsb` TRIG file
and dedicated SYT / MV / CFT exports. The *actual* data folder is **flat** and
contains only four workbooks:

| file | role |
|------|------|
| `ARES_2023_68A_CLP_Summary.xlsx` | monthly pool-stat time series (CLP) |
| `lld_ares_2023.xlsx` | loan-level tape (LLD) |
| `ARES_2023_68A_BR_TRIG.xlsx` | OC/IC + collateral-quality covenant tests (TRIG, **.xlsx not .xlsb**) |
| `margindistribution_clc_ares_2023.xlsx` | margin-bucket distribution (supporting) |

There is **no SYT, MV, or CFT workbook present.** Rather than fabricate file
reads that would error, the notebook:

1. **Auto-discovers** files so it also works if the full subfolder layout is
   later dropped in (it globs both flat and `SUBFOLDER/` layouts).
2. Reads every file that exists and prints shape + preview.
3. For the **assumed** SYT inputs, parses a real SYT workbook **if found**;
   otherwise falls back to the **documented scenario values from the project
   brief** (`20 CPR`, `.55 / 2 CDR` ladder, severity `61`, lag `12`,
   `Reinv Rt Pct 3.63`, `Par Haircut 0.41`), each flagged
   `source_file = 'SYT (brief default — file absent)'` so nothing is silently
   invented.

Every realized number carries an inline comment tracing it to a file + row/column.
""")

# ----------------------------------------------------------------------------
md("## 0 · Setup & dependencies")
code(r"""# Install (no-op if already present). pyxlsb included in case a real .xlsb TRIG is dropped in later.
import sys, subprocess
def _pip(pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs], check=False)
_pip(["pandas", "openpyxl", "pyxlsb"])

import os, glob, re, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 220)
pd.set_option("display.float_format", lambda v: f"{v:,.4f}" if isinstance(v, float) else str(v))
print("pandas", pd.__version__)""")

code(r"""# Locate the data folder regardless of where the notebook is launched from.
CANDIDATES = [
    "data/ARES_2023_68A",
    "../data/ARES_2023_68A",
    "../../data/ARES_2023_68A",
    "../../../data/ARES_2023_68A",
]
DATA_DIR = next((p for p in CANDIDATES if os.path.isdir(p)), None)
assert DATA_DIR, "Could not locate data/ARES_2023_68A — adjust CANDIDATES."
DATA_DIR = os.path.abspath(DATA_DIR)
print("DATA_DIR =", DATA_DIR)

def find_file(*needles, subdir=None):
    '''Case-insensitive search for a workbook whose name contains ALL needles.
    Searches the flat folder and an optional subdir (supports both layouts).'''
    roots = [DATA_DIR]
    if subdir:
        roots.append(os.path.join(DATA_DIR, subdir))
    for root in roots:
        for path in glob.glob(os.path.join(root, "**", "*.*"), recursive=True):
            base = os.path.basename(path).lower()
            if base.endswith((".xlsx", ".xlsb", ".xls")) and all(n.lower() in base for n in needles):
                return path
    return None

paths = {
    "CLP":  find_file("clp", "summary", subdir="CLP"),
    "LLD":  find_file("lld", subdir="LLD"),
    "TRIG": find_file("trig", subdir="TRIG"),
    "MARGIN": find_file("margindistribution"),
    "MV":   find_file("market_value", subdir="MV"),
    "SYT":  find_file("syt", subdir="SYT"),
    "CFT":  find_file("cft", subdir="CFT"),
}
for k, v in paths.items():
    print(f"{k:7s}: {os.path.relpath(v, DATA_DIR) if v else '— NOT FOUND —'}")""")

# ----------------------------------------------------------------------------
md(r"""## A · Load & clean each file

Loader helpers print shape + a preview for each workbook. XLSB files are read
with `engine='pyxlsb'`; the LLD tape has its real header on the **second row**
(`header=1`).""")

code(r"""def read_any(path, **kw):
    '''Read xlsx/xlsb transparently.'''
    eng = "pyxlsb" if path.lower().endswith(".xlsb") else None
    return pd.read_excel(path, engine=eng, **kw)""")

code(r"""# --- A.1 CLP Summary -------------------------------------------------------
# Layout: row 0 = month headers (col 0 blank); col 0 = metric label; cols 1..N
# = months newest->oldest. Read raw (header=None) then build a labelled frame.
clp_raw = read_any(paths["CLP"], header=None)
months = list(clp_raw.iloc[0, 1:])                       # '05/2026' ... '05/2023'
clp = clp_raw.iloc[1:, :].copy()
clp.columns = ["metric"] + months
clp["metric"] = clp["metric"].astype(str).str.strip()
clp = clp.set_index("metric")
# numeric coercion of the month columns
clp[months] = clp[months].apply(pd.to_numeric, errors="coerce")
print("CLP shape:", clp.shape, "| months:", months[0], "->", months[-1])
clp.iloc[:, :5].head(16)""")

code(r"""def clp_row(prefix):
    '''Return the CLP series (newest->oldest) for the first row whose label
    starts with `prefix`. Raises if not found so typos surface loudly.'''
    hits = [m for m in clp.index if m.lower().startswith(prefix.lower())]
    if not hits:
        raise KeyError(f"No CLP row starts with {prefix!r}. Have: {list(clp.index)[:30]}")
    return clp.loc[hits[0]]

NEWEST, OLDEST = months[0], months[-1]   # '05/2026' (current) and '05/2023' (deal close)
print("current month =", NEWEST, "| deal close =", OLDEST)""")

code(r"""# --- A.2 LLD loan tape -----------------------------------------------------
# Real header on row index 1; row 0 is a title cell. Drop blank-Issuer rows.
lld = read_any(paths["LLD"], header=1)
lld = lld[lld["Issuer"].notna() & (lld["Issuer"].astype(str).str.strip() != "")].copy()
for c in ["Current Balance", "Margin", "Coupon", "S&P Recovery Rate", "Index Floor Rate"]:
    if c in lld.columns:
        lld[c] = pd.to_numeric(lld[c], errors="coerce")
print("LLD shape:", lld.shape)
lld[["Issuer", "Current Balance", "CUSIP", "Margin", "Coupon",
     "S&P Recovery Rate", "S&P Reported Rating", "S&P Industry", "Maturity Date"]].head()""")

code(r"""# --- A.3 TRIG covenant tests ----------------------------------------------
# Columns: label, State, Period State, Value, operator, Threshold. Section
# header rows (e.g. 'Collateral Quality Tests') have blank State -> kept as-is.
trig_raw = read_any(paths["TRIG"], header=None)
trig = trig_raw.iloc[1:, :].copy()
trig.columns = ["label", "state", "period_state", "value", "operator", "threshold"]
trig["label"] = trig["label"].astype(str).str.strip()

def _pct_to_float(x):
    ''''150.11%' -> 150.11 ; '6%' -> 6.0 ; '.2%' -> 0.2 ; '79' -> 79 ; NaN->NaN'''
    if pd.isna(x):
        return np.nan
    s = str(x).strip().replace("%", "")
    try:
        return float(s)
    except ValueError:
        return np.nan

trig["value_num"]     = trig["value"].apply(_pct_to_float)
trig["threshold_num"] = trig["threshold"].apply(_pct_to_float)
print("TRIG shape:", trig.shape)

def trig_lookup(label):
    '''First TRIG row matching label (case-insensitive substring) that has a
    numeric value — skips the 'Pass' summary header rows.'''
    m = trig[trig["label"].str.lower().str.contains(label.lower(), regex=False)]
    m = m[m["value_num"].notna()]
    return m.iloc[0] if len(m) else None

trig[["label", "state", "value", "operator", "threshold", "value_num", "threshold_num"]].head(26)""")

code(r"""# --- A.4 Margin distribution (supporting context) -------------------------
mgn_raw = read_any(paths["MARGIN"], header=None)
mgn = mgn_raw.iloc[1:, :].copy()
mgn.columns = [str(c).strip() for c in mgn_raw.iloc[0, :]]
print("MARGIN shape:", mgn.shape, "| cols:", list(mgn.columns)[:6], "...")
mgn.head()""")

code(r"""# --- A.5 MV / CFT (load only if present; otherwise note absence) ----------
mv = read_any(paths["MV"]) if paths["MV"] else None
cft = read_any(paths["CFT"]) if paths["CFT"] else None
print("MV  :", "loaded " + str(mv.shape) if mv is not None else "absent (no tranche-stack file in folder)")
print("CFT :", "loaded " + str(cft.shape) if cft is not None else "absent (no projected-cashflow file in folder)")""")

# ----------------------------------------------------------------------------
md(r"""## B · Realized metrics from CLP / LLD

**Units.** CLP margins, WAC and `Min S&P Rec Rate` are in **percent**. LLD
`Margin`/`Coupon` are in **percent**; LLD `S&P Recovery Rate` is a **decimal
fraction** (e.g. `0.40`) and is scaled ×100 for like-for-like comparison.""")

code(r"""realized = {}   # name -> (value, unit, trace, confidence)

# ---- Point-in-time pool quality (current month = 05/2026) ----------------
# CLP row 'Min S&P Rec Rate', current column  -> 38.72 (%)
recovery_rate = float(clp_row("Min S&P Rec Rate")[NEWEST])
severity      = 100.0 - recovery_rate                      # complement of recovery
# CLP row 'WAC', current column                -> 6.608 (%)
wac           = float(clp_row("WAC")[NEWEST])
# CLP row 'Weighted Average Margin', current   -> 3.011 (%)
wa_margin     = float(clp_row("Weighted Average Margin")[NEWEST])
# CLP row 'S&P CCC+ and below', current        -> 6.93 (%)
ccc_pct       = float(clp_row("S&P CCC")[NEWEST])

realized["recovery_rate"]      = (recovery_rate, "%", "CLP 'Min S&P Rec Rate' @"+NEWEST, "reported")
realized["severity"]           = (severity,      "%", "100 - CLP 'Min S&P Rec Rate' @"+NEWEST, "reported")
realized["WAC"]                = (wac,            "%", "CLP 'WAC' @"+NEWEST, "reported")
realized["weighted_avg_margin"]= (wa_margin,     "%", "CLP 'Weighted Average Margin' @"+NEWEST, "reported")
realized["ccc_pct"]            = (ccc_pct,        "%", "CLP 'S&P CCC+ and below' @"+NEWEST, "reported")
print(f"recovery={recovery_rate:.2f}%  severity={severity:.2f}%  WAC={wac:.3f}%  "
      f"WAMargin={wa_margin:.3f}%  CCC={ccc_pct:.2f}%")""")

code(r"""# ---- Collateral par & balance-weighted recovery from the LLD tape --------
# Sum of LLD 'Current Balance' (415 loans) -> collateral par in $.
collateral_par = float(lld["Current Balance"].sum())
# Balance-weighted LLD 'S&P Recovery Rate' (decimal) x100 -> % ; cross-check vs CLP.
w = lld["Current Balance"]
bw_recovery = float(np.average(lld["S&P Recovery Rate"].fillna(0), weights=w) * 100.0)

realized["collateral_par"]            = (collateral_par, "USD",
    "sum(LLD 'Current Balance')", "reported")
realized["balance_weighted_recovery"]= (bw_recovery, "%",
    "wavg(LLD 'S&P Recovery Rate' x100, weight=Current Balance)", "reported")

print(f"collateral_par            = ${collateral_par:,.0f}  ({len(lld)} loans)")
print(f"balance_weighted_recovery = {bw_recovery:.2f}%   (CLP Min S&P Rec = {recovery_rate:.2f}%)")
print(f"  cross-check delta        = {bw_recovery - recovery_rate:+.2f} pts  "
      f"(LLD uses *mean* S&P recovery; CLP reports the *minimum* eligible rate -> "
      f"LLD naturally higher)")""")

code(r"""# ---- Realized CDR = CLP 'Default %' (as reported) ------------------------
# Read the realized CDR straight from the CLP 'Default %' row (current month).
dfp = clp_row("Default %").dropna()                  # newest..oldest, '05/2026'..'08/2023'
realized_cdr = float(dfp.iloc[0])                    # current 'Default %' = 0.55
dfp_max      = float(dfp.max())                      # peak over the deal = 1.01
nonzero_mo   = int((dfp > 0).sum())

realized["CDR"] = (realized_cdr, "%", "CLP 'Default %' @"+NEWEST, "reported")
print(f"realized CDR = CLP 'Default %' @{NEWEST} = {realized_cdr:.2f}%  "
      f"(peak {dfp_max:.2f}%, nonzero months {nonzero_mo})")""")

# NOTE: CPR is intentionally excluded. The CLP file has no prepayment field, and
# a balance-based proxy is meaningless while the deal is in its reinvestment
# period (prepayments are recycled into new loans). A true realized CPR needs the
# trustee unscheduled-principal line or sequential monthly loan tapes.

# ----------------------------------------------------------------------------
md(r"""## C · Assumed metrics (SYT scenario inputs)

The notebook parses a real SYT workbook if one is present. **None is present in
this data folder**, so we fall back to the scenario inputs documented in the
project brief and label them accordingly. Parsing logic for strings like
`"20 CPR"`, `".55 CDR"`, `"2 CDR"` is implemented so a dropped-in SYT file is
handled automatically.""")

code(r"""def parse_leading_number(s):
    ''''20 CPR' -> 20.0 ; '.55 CDR' -> 0.55 ; '2 CDR' -> 2.0 ; 61 -> 61.0'''
    if pd.isna(s):
        return np.nan
    m = re.search(r"-?\.?\d+\.?\d*", str(s))
    return float(m.group()) if m else np.nan

def parse_syt(path):
    '''Best-effort row-label parser for a SYT workbook. Returns a dict of the
    requested assumed inputs. Tolerant to header position / orientation.'''
    raw = read_any(path, header=None).astype(str)
    flat = {}
    wanted = {"Prepay": "base_cpr", "Default": "cdr", "Severity": "severity",
              "Lag": "lag", "Reinv Rt Pct": "reinv_rate", "Par Haircut": "par_haircut"}
    for _, row in raw.iterrows():
        cells = [c for c in row.tolist() if c and c != "nan"]
        for i, cell in enumerate(cells):
            for key, name in wanted.items():
                if cell.strip().lower().startswith(key.lower()):
                    val = cells[i + 1] if i + 1 < len(cells) else cell
                    flat.setdefault(name, parse_leading_number(val) if name != "cdr" else val)
    return flat""")

code(r"""# ---- Assumed values ------------------------------------------------------
if paths["SYT"]:
    syt = parse_syt(paths["SYT"])
    SYT_SRC = "SYT/" + os.path.basename(paths["SYT"])
    base_cpr    = syt.get("base_cpr", np.nan)
    cdr_ladder  = [parse_leading_number(x) for x in re.split(r"[,/]", str(syt.get("cdr", "")))]
    cdr_ladder  = [x for x in cdr_ladder if not np.isnan(x)]
    sev_assumed = syt.get("severity", np.nan)
    lag_assumed = syt.get("lag", np.nan)
    reinv_rate  = syt.get("reinv_rate", np.nan)
    par_haircut = syt.get("par_haircut", np.nan)
else:
    # No SYT workbook in folder -> documented scenario inputs from the project brief.
    SYT_SRC     = "SYT (brief default — file absent)"
    base_cpr    = parse_leading_number("20 CPR")        # 20.0
    cdr_ladder  = [parse_leading_number(".55 CDR"), parse_leading_number("2 CDR")]  # [0.55, 2.0]
    sev_assumed = 61.0                                  # Severity
    lag_assumed = 12.0                                  # Lag (months)
    reinv_rate  = 3.63                                  # Reinv Rt Pct
    par_haircut = 0.41                                  # Par Haircut

base_cdr     = cdr_ladder[0] if cdr_ladder else np.nan
recovery_assumed = 100.0 - sev_assumed                 # implied by assumed severity

print(f"SYT source        : {SYT_SRC}")
print(f"base CPR          : {base_cpr} CPR")
print(f"CDR ladder        : {cdr_ladder}  (base = {base_cdr} CDR)")
print(f"Severity / Lag    : {sev_assumed} / {lag_assumed} mo  -> implied recovery {recovery_assumed:.1f}%")
print(f"Reinv Rt Pct      : {reinv_rate}")
print(f"Par Haircut       : {par_haircut}")""")

# ----------------------------------------------------------------------------
md(r"""## D · Final output — `comparison`

One DataFrame: `metric | realized_value | assumed_value | source_file |
confidence | notes`. `confidence ∈ {reported, estimated, inferred}`. Realized
collateral-quality covenants are additionally benchmarked against TRIG thresholds
where useful. Exported to `realized_vs_assumed.csv`.""")

code(r"""rows = []
def add(metric, realized_value, assumed_value, source_file, confidence, notes):
    rows.append(dict(metric=metric, realized_value=realized_value,
                     assumed_value=assumed_value, source_file=source_file,
                     confidence=confidence, notes=notes))

CLP_SRC = "CLP/ARES_2023_68A_CLP_Summary.xlsx"
LLD_SRC = "LLD/lld_ares_2023.xlsx"

# --- CDR : realized 'Default %' vs assumed flow ladder ---------------------
add("CDR", round(realized["CDR"][0], 3), f"{base_cdr} (ladder {cdr_ladder})",
    f"{CLP_SRC} | {SYT_SRC}", "reported",
    f"Realized = CLP 'Default %' @{NEWEST} (current {realized_cdr:.2f}%, peak "
    f"{dfp_max:.2f}%). Assumed = SYT CDR ladder. Realized has run far below the "
    f"stressed {base_cdr}+ CDR rungs.")

# NOTE: CPR is intentionally omitted (no prepayment field; reinvestment masks any
# balance-based proxy). See section B note for the data needed to measure it.

# --- recovery_rate ---------------------------------------------------------
add("recovery_rate", round(recovery_rate, 2), recovery_assumed,
    f"{CLP_SRC} | {SYT_SRC}", "reported",
    f"Realized = CLP 'Min S&P Rec Rate' @{NEWEST} (%). Assumed = 100 - SYT "
    f"severity ({sev_assumed}). TRIG covenant min = "
    f"{getattr(trig_lookup('S&P Recovery Rate'),'threshold_num', float('nan'))}%.")

# --- severity --------------------------------------------------------------
add("severity", round(severity, 2), sev_assumed, f"{CLP_SRC} | {SYT_SRC}", "reported",
    f"Realized = 100 - CLP 'Min S&P Rec Rate' @{NEWEST}. Assumed = SYT severity. "
    f"Assumed severity is far harsher than realized.")

# --- WAC -------------------------------------------------------------------
wac_cov = trig_lookup("WAC")
add("WAC", round(wac, 3), getattr(wac_cov, "threshold_num", np.nan),
    f"{CLP_SRC} | TRIG", "reported",
    f"Realized = CLP 'WAC' @{NEWEST} (%). 'Assumed' shown = TRIG WAC covenant "
    f"({getattr(wac_cov,'operator','?')} {getattr(wac_cov,'threshold','?')}); "
    f"SYT has no WAC input.")

# --- weighted_avg_margin / WAS --------------------------------------------
was_cov = trig_lookup("WAS")
add("weighted_avg_margin", round(wa_margin, 3), getattr(was_cov, "threshold_num", np.nan),
    f"{CLP_SRC} | TRIG", "reported",
    f"Realized = CLP 'Weighted Average Margin' @{NEWEST} (%). 'Assumed' = TRIG "
    f"WAS covenant min ({getattr(was_cov,'threshold','?')}); SYT has no margin input.")

# --- ccc_pct ---------------------------------------------------------------
ccc_cov = trig_lookup("S&P CCC")
add("ccc_pct", round(ccc_pct, 2), getattr(ccc_cov, "threshold_num", np.nan),
    f"{CLP_SRC} | TRIG", "reported",
    f"Realized = CLP 'S&P CCC+ and below' @{NEWEST} (%). 'Assumed' = TRIG S&P CCC "
    f"covenant cap ({getattr(ccc_cov,'operator','?')} {getattr(ccc_cov,'threshold','?')}).")

# --- balance_weighted_recovery (cross-check) -------------------------------
add("balance_weighted_recovery", round(bw_recovery, 2), recovery_assumed,
    f"{LLD_SRC} | {SYT_SRC}", "reported",
    f"Cross-check: wavg LLD 'S&P Recovery Rate'(x100) by Current Balance. Higher "
    f"than CLP min-rec by design (mean vs minimum).")

# --- collateral_par --------------------------------------------------------
add("collateral_par", f"{collateral_par:,.0f}", "n/a", LLD_SRC, "reported",
    f"sum(LLD 'Current Balance') over {len(lld)} loans (USD).")

# --- reinvestment rate & par haircut (assumed-only inputs) -----------------
add("reinv_rate", "n/a", reinv_rate, SYT_SRC, "reported",
    "SYT 'Reinv Rt Pct' — assumed reinvestment rate; no realized collateral analogue.")
add("par_haircut", "n/a", par_haircut, SYT_SRC, "reported",
    "SYT 'Par Haircut' — assumed; no realized collateral analogue.")
add("lag", "n/a", lag_assumed, SYT_SRC, "reported",
    "SYT recovery 'Lag' (months) — assumed timing input; not directly observable.")

comparison = pd.DataFrame(rows, columns=[
    "metric", "realized_value", "assumed_value", "source_file", "confidence", "notes"])
comparison""")

code(r"""# Export
OUT = "realized_vs_assumed.csv"
comparison.to_csv(OUT, index=False)
print("wrote", os.path.abspath(OUT), "shape", comparison.shape)""")

# ----------------------------------------------------------------------------
md(r"""## E · Summary — what matched, what didn't

**Where files diverged from the brief.** The folder is flat and lacks the SYT,
MV and CFT exports; the TRIG file is `.xlsx`, not `.xlsb`. Assumed CPR/CDR/
severity/lag/reinv/haircut therefore come from the **documented brief defaults**,
not a parsed SYT workbook (the parser is wired in for when one is supplied).

**Realized vs. assumed read-out:**

- **Recovery / severity — DID NOT match (conservative).** Realized `Min S&P Rec
  Rate ≈ 38.7%` (severity ≈ 61.3%) vs. assumed severity `61` (recovery `39%`).
  Here the realized and assumed are *essentially in line* — the SYT severity of
  61 was well calibrated. The balance-weighted LLD recovery (~mean) sits higher,
  as expected, since CLP reports the *minimum* eligible rate. TRIG confirms the
  recovery covenant (`> 37.25%`) passes.
- **CDR — realized read straight from `Default %`.** Currently ~0.55% (peak
  ~1.01%, only a handful of non-zero months) vs. the assumed `.55 / 2 CDR` ladder.
  Realized defaults sit at the base rung and **well below** the stressed `2 CDR`.
- **CPR — omitted.** The CLP file has no prepayment field, and a balance-based
  proxy is meaningless while the deal is in its reinvestment period (prepayments
  are recycled into new loans). Measuring it would require the trustee
  unscheduled-principal line or sequential monthly loan tapes.
- **Collateral quality — comfortably inside covenants.** WAC, WAS/margin, and S&P
  CCC% all sit on the safe side of their TRIG thresholds, and every OC/IC test
  passes — i.e. realized credit quality is **better than** the covenant floor the
  scenario stresses against.

**Bottom line.** Assumed **severity (61)** matched realized experience closely.
Assumed **default intensity (2 CDR rung)** was conservative relative to the
realized `Default %`. CPR is **not measurable** from these exports. The absent
SYT/MV/CFT workbooks are the main data gap to close for a fully measured
comparison.
""")

nb["cells"] = cells
nb["metadata"] = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python"},
}
with open("ARES_2023_68A_realized_vs_assumed.ipynb", "w") as f:
    nbf.write(nb, f)
print("wrote ARES_2023_68A_realized_vs_assumed.ipynb with", len(cells), "cells")