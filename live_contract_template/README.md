# Live Contract Template

Project: 4.1 Correlation & Tail Risk in CLO Tranches

Place Bloomberg CLO loan-level holdings, bond/tranche structure, collateral statistics, and exported Bloomberg analytics in one live contract folder. The sample package runs without these licensed files; live mode should point -LiveRoot to that folder.

Use this folder as the place to document live or licensed inputs. If the data are too large or restricted for the zip,
put only a manifest, schema, and field mapping here. The `run_live_template.ps1` script requires an explicit path
argument so the code does not guess where licensed data live.
