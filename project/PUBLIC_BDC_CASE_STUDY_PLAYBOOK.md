# Public BDC Case Study Playbook

The default free-public Chapter 4 fallback is one pinned public BDC-sponsored CLO:

- `Palmer Square BDC CLO 1`

This route is narrower than Bloomberg or Intex/Trepp. It uses real CLO notes and real pledged-loan rows from public SEC filings, but PD, CPR, LGD, and low/high rho remain explicit analyst overlays.

## SEC Retrieval Model

The extractor now resolves the case study through EDGAR directly:

- `data.sec.gov/submissions/CIK##########.json` for filing history
- the filing-directory `index.json` under `/Archives/edgar/data/.../` for document discovery
- the resolved filing documents for the note disclosure, indenture exhibit, and collateral filing

Use a declared SEC user agent. The extractor defaults to a placeholder, but for real pulls you should pass a real contact:

```powershell
--sec-user-agent "Book2Chapter4 your-name@your-domain.com"
```

The extractor also supports `--cache-dir <directory>` so repeated SEC pulls do not redownload the same JSON and HTML responses.

## Build The Raw Public Package

```powershell
python extract_public_bdc_clo_case_study.py `
  --output-dir D:\data\CLO\Chapter4\public_raw `
  --sec-user-agent "Book2Chapter4 your-name@your-domain.com" `
  --cache-dir D:\data\CLO\Chapter4\sec_cache `
  --low-rho 0.12 `
  --high-rho 0.30 `
  --default-annual-pd 0.02 `
  --default-annual-cpr 0.04 `
  --default-lgd 0.60
```

Optional refinement inputs:

- `--assumptions-export <csv>` for loan-level or sector-level PD, CPR, and LGD overlays
- `--senior-trigger-level`, `--mezz-trigger-level`, and `--equity-trigger-level` if you want explicit warning thresholds instead of the extractor's parsed-or-proxy defaults
- `--note-accession`, `--indenture-accession`, and `--collateral-accession` if you want to pin a different filing accession without editing code
- `--note-source`, `--indenture-source`, and `--collateral-source` when testing against local HTML files or explicit document URLs

That command writes:

- `public_tranche_export.csv`
- `public_collateral_export.csv`
- `public_stress_export.csv`
- `public_case_study_metadata.json`

The metadata file records:

- `source_mode: public_sec_case_study`
- `retrieval_method`
- resolved filing accessions and filing dates
- resolved SEC document URLs
- analyst overlay assumptions

## Stage The Normalized Live Contract

Use the resolved SEC URLs from `public_case_study_metadata.json`, not a generic `sec.gov` placeholder:

```powershell
python stage_actual_clo_contract.py `
  --route public_bdc_clo_case_study `
  --deal-id PALMER_SQUARE_BDC_CLO_1 `
  --output-dir D:\data\CLO\Chapter4\live_contract `
  --tranche-export D:\data\CLO\Chapter4\public_raw\public_tranche_export.csv `
  --collateral-export D:\data\CLO\Chapter4\public_raw\public_collateral_export.csv `
  --stress-export D:\data\CLO\Chapter4\public_raw\public_stress_export.csv `
  --as-of-date 2025-12-31 `
  --source-url "https://www.sec.gov/Archives/edgar/data/1794776/000121390024046305/ea0206724-8k_palmersquare.htm" `
  --source-url "https://www.sec.gov/Archives/edgar/data/1794776/000121390024046305/ea020672401ex10-2_palmer.htm" `
  --source-url "https://www.sec.gov/Archives/edgar/data/1794776/000119312526073362/psbd-20251231.htm"
```

## Run The Chapter

```powershell
python CLO.py --mode live --live-root D:\data\CLO\Chapter4\live_contract
```

The resulting run is a real-investment public case study. It should be described as a public SEC-backed case study, not as a vendor-grade surveillance pack.
