# 4.1 Correlation & Tail Risk in CLO Tranches

This is a ready-to-extract project distribution rebuilt on 20260605_122811_12544.

## Root Layout

- `project/`: code required to run this example.
- `data/` or `sample_data/`: packaged sample inputs and any approved partner export material.
- `live_contract_template/`: instructions for live or licensed data that is not included.
- `outputs/`: sample and live run outputs.
- `provenance/`: manifests, wrapper metadata, and source-package documentation.
- `requirements.txt`: Python package requirements.
- `run_sample.ps1`: sample-mode execution script.
- `run_live_template.ps1`: live-mode template for licensed or external data.

## First Steps

- Run the sample package to confirm the local Python environment works.
- Download Bloomberg loan-level CLO holdings and bond structure for the selected deal.
- Familiarize yourself with LTV, CPR, WAL, OC/IC tests, tranching, and waterfall terminology.
- Compare the sample output layout with the expected Bloomberg export fields.

## Run Sample Mode

Open PowerShell in this project root and run:

```powershell
.un_sample.ps1
```

## Live Data Contract

Place Bloomberg CLO loan-level holdings, bond/tranche structure, collateral statistics, and exported Bloomberg analytics in one live contract folder. The sample package runs without these licensed files; live mode should point -LiveRoot to that folder.

## Next Steps

- Replace the synthetic sample inputs with Bloomberg contract files.
- Run Bloomberg analytics and save the exported diagnostics in the live contract folder.
- Run live mode and reconcile the Python/MATLAB outputs to Bloomberg results.

## Safety Notes

The sample mode is intended to run immediately after unzip once Python dependencies are available. Live mode is explicit:
it requires the recipient to point the script at a documented contract folder rather than silently searching local drives.
