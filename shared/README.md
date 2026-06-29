# Book2 Public Repo

This repo is the publication-facing educational repo for Book2.

## Core Rule

`repo\` does not contain raw licensed data, downloaded vendor snapshots, or machine-readable outputs derived from licensed data.

The repo may contain two kinds of publication-facing assets:

- fake teaching data bundled under `packs/`
- final static rendered research figures generated from a private live run outside the repo

## What Is In This Repo

- `examples/`
  - notebook-style educational examples organized as `Chapter N/<Public Note Title>/...`
  - optional static rendered figures from private live runs
- `packages/`
  - small helper code used by the examples
- `packs/`
  - fake pseudo/scenario teaching data only
- `docs/`
  - short policy and implementation notes
- `registry/`
  - control-plane metadata, including `registry/example_paths.yml` for public example roots

## What Is Not In This Repo

- copyrighted market datasets
- downloaded licensed extracts
- local archive copies of vendor outputs
- machine-readable live result tables copied from private runs
- rebuild pipelines for internal production workflows

## Working Model

Each example may have two clear paths:

1. `sample`
   - runs on the fake data included in this repo
2. `live`
   - reads private external inputs or live runtime sources outside the repo
   - may save final static figures into `repo\` for readers to inspect

The default public notebook path should remain the bundled fake data.

## Rendered Live Outputs

A live run may commit static rendered figures to the repo only if all of the following are true:

- the inputs stay outside `repo\`
- no machine-readable live tables are committed
- the figures are labeled as non-reproducible without equivalent access
- the example still runs on bundled fake data by default

## Current Example Layout

The canonical example layout is chapter-based and synced to the current L3 note titles in `D:\dev\ObsidianVault2026\Book2\Book2\Index.md`.

Examples currently live under:

- `examples/Chapter 4/Correlation and Tail Risk in CLO Tranches/`
- `examples/Chapter 8/Implied Ceasefire Timing from USO Options/`
- `examples/Chapter 8/Options Momentum & Gamma Imbalance/`
- `examples/Chapter 9/VC & PE Exit Prediction/`
- `examples/Chapter 12/Strategy and Asset Class Clustering with UMAP and HDBSCAN/`
- `examples/Chapter 15/Estimating Market Impact with Bar Data OHLCV Impact/`
- `examples/Chapter 15/Estimating Market Impact with Bar Data Efficient VWAP/`
- `examples/Chapter 18/Copulas and GANs for Synthetic Financial Time Series Data/`

The sync rules live in:

- `docs/EXAMPLE_INDEX_SYNC_INSTRUCTIONS.md`
- `registry/example_paths.yml`

## Design Bias

This repo should stay simple and readable:

- examples first
- fake data included
- helpers small
- no raw licensed data in repo
- no machine-readable live outputs in repo
