# (c) 2027, Michael Robbins
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import CLO as mod
import extract_public_bdc_clo_case_study as public_mod
import stage_actual_clo_contract as stage_mod


def test_clo_public_smoke() -> None:
    output_dir = Path(__file__).resolve().parent / "test_smoke_output"
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        result = mod.run_pipeline(
            mod.RunConfig(
                data_mode="public",
                output_root=output_dir,
                num_paths=512,
                seed=11,
            )
        )

        required_files = [
            "clo-observed-cohort-panel.csv",
            "clo-rho-calibration-grid.csv",
            "clo-collateral-valuation-table.csv",
            "clo-collateral-valuation-summary.csv",
            "clo-tranche-summary-metrics.csv",
            "clo-rho-scenarios.csv",
            "clo-run-metadata.json",
        ]
        for filename in required_files:
            assert (output_dir / filename).exists(), filename

        for stem in [
            "clo-payoff-map",
            "clo-rho-calibration-objective",
            "clo-rho-calibration-fit",
            "clo-collateral-model-price-vs-market",
            "clo-collateral-value-by-rating",
            "clo-collateral-nav-distribution-low-vs-high",
            "clo-collateral-loss-cdf-low-vs-high",
            "clo-equity-loss-cdf-low-vs-high",
            "clo-mezzanine-loss-cdf-low-vs-high",
            "clo-senior-loss-cdf-low-vs-high",
            "clo-tranche-tail-metrics-low-vs-high",
            "clo-trigger-frequencies-low-vs-high",
            "clo-loss-compensation-spread-low-vs-high",
        ]:
            assert (output_dir / f"{stem}.png").exists(), stem
            assert (output_dir / f"{stem}.svg").exists(), stem

        metadata = json.loads((output_dir / "clo-run-metadata.json").read_text(encoding="utf-8"))
        assert metadata["data_mode"] == "public"
        assert metadata["num_paths"] == 512
        assert "model_price" in metadata["collateral_valuation_schema"]

        summary = pd.read_csv(output_dir / "clo-tranche-summary-metrics.csv")
        assert {"scenario", "tranche", "expected_loss_pct", "var99_pct", "cvar99_pct"} <= set(summary.columns)
        valuation = pd.read_csv(output_dir / "clo-collateral-valuation-table.csv")
        assert {"market_price", "model_price", "discount_margin_bps"} <= set(valuation.columns)

        assert result["summary"]["scenario"].tolist().count("low") == 3
        assert result["summary"]["scenario"].tolist().count("high") == 3
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def test_clo_live_contract_fails_clearly_when_template_is_unpopulated() -> None:
    template_root = Path(__file__).resolve().parent.parent / "live_contract_template"
    with pytest.raises(mod.ContractError, match="fact_clo_collateral_position.csv"):
        mod.run_pipeline(
            mod.RunConfig(
                data_mode="live",
                live_root=template_root,
                output_root=Path(__file__).resolve().parent / "test_live_failure_output",
                num_paths=64,
                seed=7,
            )
        )


def test_clo_live_market_observed_bundle_runs_from_bloomberg_style_exports() -> None:
    root = Path(__file__).resolve().parent / "test_live_market_observed_bundle"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        raw_tranche = root / "raw_tranche.csv"
        raw_collateral = root / "raw_collateral.csv"
        field_dictionary = root / "field_dictionary.csv"
        live_root = root / "live_contract"
        output_root = root / "rendered"

        pd.DataFrame(
            [
                {
                    "transaction_name": "DEAL_A",
                    "class": "Equity",
                    "attachment_point": 0.00,
                    "detachment_point": 0.06,
                    "oc_test_level": 0.03,
                    "margin_bps": 0.0,
                },
                {
                    "transaction_name": "DEAL_A",
                    "class": "Mezzanine",
                    "attachment_point": 0.06,
                    "detachment_point": 0.14,
                    "oc_test_level": 0.10,
                    "margin_bps": 350.0,
                },
                {
                    "transaction_name": "DEAL_A",
                    "class": "Senior",
                    "attachment_point": 0.14,
                    "detachment_point": 0.30,
                    "oc_test_level": 0.18,
                    "margin_bps": 190.0,
                },
            ]
        ).to_csv(raw_tranche, index=False)
        pd.DataFrame(
            [
                {
                    "transaction_name": "DEAL_A",
                    "position_date": "2026-03-31",
                    "asset_id": "LN1",
                    "industry": "Software",
                    "par_amount": 45.0,
                    "pd_1y": 0.018,
                    "cpr_1y": 0.05,
                    "loss_given_default": 0.55,
                    "rating": "B",
                    "market_price": 98.5,
                    "spread_bps": 475.0,
                    "reference_rate": 0.0525,
                    "rate_floor": 0.01,
                    "years_to_maturity": 5.0,
                    "discount_margin_bps": 540.0,
                },
                {
                    "transaction_name": "DEAL_A",
                    "position_date": "2026-03-31",
                    "asset_id": "LN2",
                    "industry": "Retail",
                    "par_amount": 35.0,
                    "pd_1y": 0.022,
                    "cpr_1y": 0.04,
                    "loss_given_default": 0.60,
                    "rating": "B-",
                    "market_price": 96.25,
                    "spread_bps": 625.0,
                    "reference_rate": 0.0525,
                    "rate_floor": 0.01,
                    "years_to_maturity": 6.0,
                    "discount_margin_bps": 710.0,
                },
                {
                    "transaction_name": "DEAL_A",
                    "position_date": "2026-03-31",
                    "asset_id": "LN3",
                    "industry": "Healthcare",
                    "par_amount": 20.0,
                    "pd_1y": 0.016,
                    "cpr_1y": 0.03,
                    "loss_given_default": 0.50,
                    "rating": "BB",
                    "market_price": 100.1,
                    "spread_bps": 350.0,
                    "reference_rate": 0.0525,
                    "rate_floor": 0.01,
                    "years_to_maturity": 4.0,
                    "discount_margin_bps": 420.0,
                },
            ]
        ).to_csv(raw_collateral, index=False)
        pd.DataFrame(
            [
                {
                    "worksheet": "tranche_export",
                    "output_file": "bbg_clo_tranche_export.csv",
                    "canonical_column": "coupon_bps",
                    "bloomberg_function": "BDP",
                    "bloomberg_field": "SPREAD_BPS",
                    "security_or_screen": "Representative tranche universe",
                    "notes": "Fixture field dictionary entry",
                }
            ]
        ).to_csv(field_dictionary, index=False)

        stage_mod.stage_actual_contract(
            SimpleNamespace(
                route="bloomberg_market_observed",
                deal_id="DEAL_A",
                output_dir=live_root,
                tranche_export=raw_tranche,
                collateral_export=raw_collateral,
                cohort_export=None,
                manager_export=None,
                default_export=None,
                recovery_export=None,
                cashflow_export=None,
                stress_export=None,
                field_dictionary_export=field_dictionary,
                as_of_date="2026-03-31",
                source_url=["https://example.com/bloomberg-airgap"],
                base_rho=None,
                low_rho=0.12,
                high_rho=0.28,
                low_pd_multiplier=1.0,
                high_pd_multiplier=1.0,
                low_cpr_multiplier=1.0,
                high_cpr_multiplier=1.0,
                low_lgd_addon=0.0,
                high_lgd_addon=0.0,
                discount_rate=0.04,
            )
        )

        result = mod.run_pipeline(
            mod.RunConfig(
                data_mode="live",
                live_root=live_root,
                output_root=output_root,
                num_paths=512,
                seed=23,
            )
        )
        metadata = json.loads((output_root / "clo-run-metadata.json").read_text(encoding="utf-8"))
        stage_metadata = json.loads((live_root / "stage_metadata.json").read_text(encoding="utf-8"))
        observed_panel = pd.read_csv(output_root / "clo-observed-cohort-panel.csv")

        assert metadata["data_mode"] == "live"
        assert metadata["calibration_mode"] == "scenario_explicit_rho"
        assert metadata["source_metadata"]["pack_label"] == "licensed"
        assert metadata["source_metadata"]["fidelity_mode"] == "market_observed"
        assert metadata["source_metadata"]["source_families"] == ["bloomberg_clo"]
        assert "model_price" in metadata["collateral_valuation_schema"]
        assert stage_metadata["route"] == "bloomberg_terminal_excel_airgap"
        assert stage_metadata["field_dictionary_path"] is not None
        assert (live_root / "field_dictionary.csv").exists()
        assert observed_panel.empty
        assert sorted(result["summary"]["scenario"].unique().tolist()) == ["high", "low"]

        scenario_table = pd.read_csv(output_root / "clo-rho-scenarios.csv")
        assert scenario_table.loc[scenario_table["scenario"] == "base", "rho"].iloc[0] == pytest.approx(0.20)
        assert scenario_table.loc[scenario_table["scenario"] == "low", "rho"].iloc[0] == pytest.approx(0.12)
        assert scenario_table.loc[scenario_table["scenario"] == "high", "rho"].iloc[0] == pytest.approx(0.28)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_public_bdc_case_study_extractor_stages_and_runs_live() -> None:
    root = Path(__file__).resolve().parent / "test_public_bdc_case_study"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        note_source = root / "note_source.html"
        indenture_source = root / "indenture_source.html"
        collateral_source = root / "collateral_source.html"
        raw_dir = root / "public_raw"
        live_root = root / "live_contract"
        output_root = root / "rendered"

        note_source.write_text(
            """
            <html><body>
            <p>
            The notes offered in the CLO Transaction were issued by Palmer Square BDC CLO 1, Ltd. and consist of
            (i) $232 million of AAA Class A Notes, which will bear interest at Term SOFR plus 1.60%;
            (ii) $58 million of AA Class B-1 Notes, which will bear interest at Term SOFR plus 2.15%;
            and (iii) $10 million of AA Class B-2 Notes, which will bear interest at a fixed rate of 6.33%.
            Additionally, the Issuer issued $100.5 million of Subordinated Notes.
            The Palmer Square BDC CLO 1 Notes will be scheduled to mature on July 15, 2037.
            </p>
            </body></html>
            """,
            encoding="utf-8",
        )
        indenture_source.write_text(
            """
            <html><body>
            <p>Class A Overcollateralization Ratio 121.0%</p>
            <p>Class B Overcollateralization Ratio 109.0%</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        collateral_source.write_text(
            """
            <html><body>
            <table>
              <tr>
                <th>Portfolio Company</th>
                <th>Industry</th>
                <th>Interest Rate</th>
                <th>Maturity Date</th>
                <th>Principal / Par</th>
              </tr>
              <tr>
                <td>Acme Software (8)</td>
                <td>Software</td>
                <td>10.50%</td>
                <td>07/15/2030</td>
                <td>12,500,000</td>
              </tr>
              <tr>
                <td>Bravo Retail (8)(9)</td>
                <td>Retail</td>
                <td>11.25%</td>
                <td>01/15/2031</td>
                <td>8,000,000</td>
              </tr>
              <tr>
                <td>Ignored Loan (6)</td>
                <td>Healthcare</td>
                <td>9.10%</td>
                <td>01/15/2031</td>
                <td>4,000,000</td>
              </tr>
            </table>
            </body></html>
            """,
            encoding="utf-8",
        )

        extracted = public_mod.extract_public_case_study(
            public_mod._apply_case_study_defaults(
                SimpleNamespace(
                    case_study="palmer_square_bdc_clo_1",
                    output_dir=raw_dir,
                    note_source=str(note_source),
                    indenture_source=str(indenture_source),
                    collateral_source=str(collateral_source),
                    assumptions_export=None,
                    as_of_date=None,
                    collateral_footnote_marker=None,
                    senior_trigger_level=None,
                    mezz_trigger_level=None,
                    equity_trigger_level=None,
                    default_annual_pd=0.02,
                    default_annual_cpr=0.04,
                    default_lgd=0.60,
                    base_rho=None,
                    low_rho=0.12,
                    high_rho=0.30,
                    low_pd_multiplier=1.0,
                    high_pd_multiplier=1.0,
                    low_cpr_multiplier=1.0,
                    high_cpr_multiplier=1.0,
                    low_lgd_addon=0.0,
                    high_lgd_addon=0.0,
                    discount_rate=0.04,
                )
            )
        )

        tranche_export = pd.read_csv(extracted["tranche_export"])
        collateral_export = pd.read_csv(extracted["collateral_export"])
        extracted_metadata = json.loads((raw_dir / "public_case_study_metadata.json").read_text(encoding="utf-8"))
        assert tranche_export["tranche"].tolist() == [
            "Subordinated Notes",
            "Class B-2 Notes",
            "Class B-1 Notes",
            "Class A Notes",
        ]
        assert collateral_export["loan_identifier"].tolist() == ["Acme Software", "Bravo Retail"]
        assert extracted_metadata["source_mode"] == "public_sec_case_study"
        assert extracted_metadata["retrieval_method"] == "mixed_override"

        stage_mod.stage_actual_contract(
            SimpleNamespace(
                route="public_bdc_clo_case_study",
                deal_id="PALMER_SQUARE_BDC_CLO_1",
                output_dir=live_root,
                tranche_export=extracted["tranche_export"],
                collateral_export=extracted["collateral_export"],
                cohort_export=None,
                manager_export=None,
                default_export=None,
                recovery_export=None,
                cashflow_export=None,
                stress_export=extracted["stress_export"],
                field_dictionary_export=None,
                as_of_date="2025-12-31",
                source_url=["https://www.sec.gov/"],
                base_rho=None,
                low_rho=0.12,
                high_rho=0.30,
                low_pd_multiplier=1.0,
                high_pd_multiplier=1.0,
                low_cpr_multiplier=1.0,
                high_cpr_multiplier=1.0,
                low_lgd_addon=0.0,
                high_lgd_addon=0.0,
                discount_rate=0.04,
            )
        )

        result = mod.run_pipeline(
            mod.RunConfig(
                data_mode="live",
                live_root=live_root,
                output_root=output_root,
                num_paths=384,
                seed=19,
            )
        )
        metadata = json.loads((output_root / "clo-run-metadata.json").read_text(encoding="utf-8"))
        assert metadata["data_mode"] == "live"
        assert metadata["calibration_mode"] == "scenario_explicit_rho"
        assert metadata["source_metadata"]["pack_label"] == "public"
        assert metadata["source_metadata"]["source_mode"] == "public_sec_case_study"
        assert metadata["source_metadata"]["source_families"] == ["public_deal_docs"]
        assert sorted(result["summary"]["scenario"].unique().tolist()) == ["high", "low"]
        assert sorted(result["summary"]["tranche"].unique().tolist()) == [
            "Class A Notes",
            "Class B-1 Notes",
            "Class B-2 Notes",
            "Subordinated Notes",
        ]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_public_bdc_case_study_edgar_resolution_stages_and_runs_live(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(__file__).resolve().parent / "test_public_bdc_case_study_edgar"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        raw_dir = root / "public_raw"
        live_root = root / "live_contract"
        output_root = root / "rendered"
        cache_dir = root / "cache"
        seen_user_agents: list[str | None] = []

        submissions_url = "https://data.sec.gov/submissions/CIK0001794776.json"
        note_index_url = "https://www.sec.gov/Archives/edgar/data/1794776/000121390024046305/index.json"
        note_url = "https://www.sec.gov/Archives/edgar/data/1794776/000121390024046305/ea0206724-8k_palmersquare.htm"
        indenture_url = "https://www.sec.gov/Archives/edgar/data/1794776/000121390024046305/ea020672401ex10-2_palmer.htm"
        collateral_index_url = "https://www.sec.gov/Archives/edgar/data/1794776/000119312526073362/index.json"
        collateral_url = "https://www.sec.gov/Archives/edgar/data/1794776/000119312526073362/psbd-20251231.htm"

        responses = {
            submissions_url: json.dumps(
                {
                    "filings": {
                        "recent": {
                            "accessionNumber": ["0001213900-24-046305", "0001193125-26-073362"],
                            "filingDate": ["2024-05-23", "2026-03-16"],
                            "form": ["8-K", "10-K"],
                            "primaryDocument": ["ea0206724-8k_palmersquare.htm", "psbd-20251231.htm"],
                        },
                        "files": [],
                    }
                }
            ).encode("utf-8"),
            note_index_url: json.dumps(
                {
                    "directory": {
                        "item": [
                            {"name": "ea0206724-8k_palmersquare.htm"},
                            {"name": "ea020672401ex10-2_palmer.htm"},
                        ]
                    }
                }
            ).encode("utf-8"),
            collateral_index_url: json.dumps(
                {
                    "directory": {
                        "item": [
                            {"name": "psbd-20251231.htm"},
                        ]
                    }
                }
            ).encode("utf-8"),
            note_url: b"""
            <html><body>
            <p>
            The notes offered in the CLO Transaction were issued by Palmer Square BDC CLO 1, Ltd. and consist of
            (i) $232 million of AAA Class A Notes, which will bear interest at Term SOFR plus 1.60%;
            (ii) $58 million of AA Class B-1 Notes, which will bear interest at Term SOFR plus 2.15%;
            and (iii) $10 million of AA Class B-2 Notes, which will bear interest at a fixed rate of 6.33%.
            Additionally, the Issuer issued $100.5 million of Subordinated Notes.
            </p>
            </body></html>
            """,
            indenture_url: b"""
            <html><body>
            <p>Class A Overcollateralization Ratio 121.0%</p>
            <p>Class B Overcollateralization Ratio 109.0%</p>
            </body></html>
            """,
            collateral_url: b"""
            <html><body>
            <h2>Schedule of Investments</h2>
            <table>
              <tr>
                <th colspan=\"5\">Schedule of Investments as of December 31, 2025</th>
              </tr>
              <tr>
                <th>Portfolio Company</th>
                <th>Industry</th>
                <th>Interest Rate</th>
                <th>Maturity Date</th>
                <th>Principal / Par</th>
              </tr>
              <tr>
                <td>Acme Software (8)</td>
                <td>Software</td>
                <td>10.50%</td>
                <td>07/15/2030</td>
                <td>12,500,000</td>
              </tr>
              <tr>
                <td>Bravo Retail (8)(9)</td>
                <td>Retail</td>
                <td>11.25%</td>
                <td>01/15/2031</td>
                <td>8,000,000</td>
              </tr>
              <tr>
                <td>Ignored Loan (6)</td>
                <td>Healthcare</td>
                <td>9.10%</td>
                <td>01/15/2031</td>
                <td>4,000,000</td>
              </tr>
            </table>
            </body></html>
            """,
        }

        class FakeResponse:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload

            def read(self) -> bytes:
                return self.payload

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        def fake_urlopen(request):
            url = request.full_url
            seen_user_agents.append(request.headers.get("User-agent"))
            assert url in responses, url
            return FakeResponse(responses[url])

        monkeypatch.setattr(public_mod, "urlopen", fake_urlopen)
        monkeypatch.setattr(public_mod, "SEC_MIN_REQUEST_INTERVAL_SECONDS", 0.0)

        extracted = public_mod.extract_public_case_study(
            public_mod._apply_case_study_defaults(
                SimpleNamespace(
                    case_study="palmer_square_bdc_clo_1",
                    output_dir=raw_dir,
                    note_source=None,
                    indenture_source=None,
                    collateral_source=None,
                    note_accession=None,
                    indenture_accession=None,
                    collateral_accession=None,
                    sec_user_agent="Book2Chapter4Test test@example.com",
                    cache_dir=cache_dir,
                    assumptions_export=None,
                    as_of_date=None,
                    collateral_footnote_marker=None,
                    senior_trigger_level=None,
                    mezz_trigger_level=None,
                    equity_trigger_level=None,
                    default_annual_pd=0.02,
                    default_annual_cpr=0.04,
                    default_lgd=0.60,
                    base_rho=None,
                    low_rho=0.12,
                    high_rho=0.30,
                    low_pd_multiplier=1.0,
                    high_pd_multiplier=1.0,
                    low_cpr_multiplier=1.0,
                    high_cpr_multiplier=1.0,
                    low_lgd_addon=0.0,
                    high_lgd_addon=0.0,
                    discount_rate=0.04,
                )
            )
        )

        extracted_metadata = json.loads((raw_dir / "public_case_study_metadata.json").read_text(encoding="utf-8"))
        assert extracted_metadata["source_mode"] == "public_sec_case_study"
        assert extracted_metadata["retrieval_method"] == "edgar_direct"
        assert extracted_metadata["resolved_documents"]["note"]["accession"] == "0001213900-24-046305"
        assert extracted_metadata["resolved_documents"]["indenture"]["accession"] == "0001213900-24-046305"
        assert extracted_metadata["resolved_documents"]["collateral"]["accession"] == "0001193125-26-073362"
        assert extracted_metadata["sources"]["source_urls"] == [note_url, indenture_url, collateral_url]
        assert all(agent == "Book2Chapter4Test test@example.com" for agent in seen_user_agents if agent is not None)

        stage_mod.stage_actual_contract(
            SimpleNamespace(
                route="public_bdc_clo_case_study",
                deal_id="PALMER_SQUARE_BDC_CLO_1",
                output_dir=live_root,
                tranche_export=extracted["tranche_export"],
                collateral_export=extracted["collateral_export"],
                cohort_export=None,
                manager_export=None,
                default_export=None,
                recovery_export=None,
                cashflow_export=None,
                stress_export=extracted["stress_export"],
                field_dictionary_export=None,
                as_of_date="2025-12-31",
                source_url=extracted_metadata["sources"]["source_urls"],
                base_rho=None,
                low_rho=0.12,
                high_rho=0.30,
                low_pd_multiplier=1.0,
                high_pd_multiplier=1.0,
                low_cpr_multiplier=1.0,
                high_cpr_multiplier=1.0,
                low_lgd_addon=0.0,
                high_lgd_addon=0.0,
                discount_rate=0.04,
            )
        )

        result = mod.run_pipeline(
            mod.RunConfig(
                data_mode="live",
                live_root=live_root,
                output_root=output_root,
                num_paths=384,
                seed=29,
            )
        )
        run_metadata = json.loads((output_root / "clo-run-metadata.json").read_text(encoding="utf-8"))
        assert run_metadata["source_metadata"]["pack_label"] == "public"
        assert run_metadata["source_metadata"]["source_mode"] == "public_sec_case_study"
        assert run_metadata["source_metadata"]["source_families"] == ["public_deal_docs"]
        assert sorted(result["summary"]["scenario"].unique().tolist()) == ["high", "low"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_clo_live_market_observed_bundle_requires_explicit_rho_without_cohort_panel() -> None:
    root = Path(__file__).resolve().parent / "test_live_missing_rho_bundle"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        live_root = root / "live_contract_missing_rho"
        live_root.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(
            [
                {
                    "deal_id": "DEAL_A",
                    "as_of_date": "2026-03-31",
                    "loan_id": "LN1",
                    "sector": "Software",
                    "current_balance": 100.0,
                    "annual_pd": 0.02,
                    "annual_cpr": 0.04,
                    "lgd": 0.60,
                    "loan_identifier": "LN1",
                    "rating": "B",
                    "market_price": 97.5,
                    "coupon_spread_bps": 500.0,
                    "reference_rate": 0.0525,
                    "coupon_floor": 0.01,
                    "maturity_years": 5.0,
                    "discount_margin_bps": 575.0,
                    "source_family": "bloomberg_clo",
                }
            ]
        ).to_csv(live_root / "fact_clo_collateral_position.csv", index=False)
        pd.DataFrame(
            [
                {"deal_id": "DEAL_A", "tranche": "Equity", "attach": 0.00, "detach": 0.06, "trigger_level": 0.03},
                {"deal_id": "DEAL_A", "tranche": "Mezzanine", "attach": 0.06, "detach": 0.14, "trigger_level": 0.10},
                {"deal_id": "DEAL_A", "tranche": "Senior", "attach": 0.14, "detach": 0.30, "trigger_level": 0.18},
            ]
        ).to_csv(live_root / "dim_clo_tranche.csv", index=False)
        pd.DataFrame(
            [
                {"scenario": "low", "pd_multiplier": 1.0, "cpr_multiplier": 1.0, "lgd_addon": 0.0},
                {"scenario": "high", "pd_multiplier": 1.0, "cpr_multiplier": 1.0, "lgd_addon": 0.0},
            ]
        ).to_csv(live_root / "scenario_clo_stress.csv", index=False)

        with pytest.raises(mod.ContractError, match="Explicit-rho live runs need"):
            mod.run_pipeline(
                mod.RunConfig(
                    data_mode="live",
                    live_root=live_root,
                    output_root=root / "rendered",
                    num_paths=128,
                    seed=31,
                )
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_clo_live_market_observed_bundle_requires_collateral_valuation_anchor() -> None:
    root = Path(__file__).resolve().parent / "test_live_missing_valuation_anchor"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    try:
        live_root = root / "live_contract_missing_anchor"
        live_root.mkdir(parents=True, exist_ok=True)

        pd.DataFrame(
            [
                {
                    "deal_id": "DEAL_A",
                    "as_of_date": "2026-03-31",
                    "loan_id": "LN1",
                    "sector": "Software",
                    "current_balance": 100.0,
                    "annual_pd": 0.02,
                    "annual_cpr": 0.04,
                    "lgd": 0.60,
                    "loan_identifier": "LN1",
                    "rating": "B",
                    "market_price": pd.NA,
                    "coupon_spread_bps": 500.0,
                    "reference_rate": 0.0525,
                    "coupon_floor": 0.01,
                    "maturity_years": 5.0,
                    "discount_margin_bps": pd.NA,
                    "source_family": "bloomberg_clo",
                }
            ]
        ).to_csv(live_root / "fact_clo_collateral_position.csv", index=False)
        pd.DataFrame(
            [
                {"deal_id": "DEAL_A", "tranche": "Equity", "attach": 0.00, "detach": 0.06, "trigger_level": 0.03},
                {"deal_id": "DEAL_A", "tranche": "Mezzanine", "attach": 0.06, "detach": 0.14, "trigger_level": 0.10},
                {"deal_id": "DEAL_A", "tranche": "Senior", "attach": 0.14, "detach": 0.30, "trigger_level": 0.18},
            ]
        ).to_csv(live_root / "dim_clo_tranche.csv", index=False)
        pd.DataFrame(
            [
                {"scenario": "low", "rho": 0.12, "pd_multiplier": 1.0, "cpr_multiplier": 1.0, "lgd_addon": 0.0},
                {"scenario": "high", "rho": 0.28, "pd_multiplier": 1.0, "cpr_multiplier": 1.0, "lgd_addon": 0.0},
            ]
        ).to_csv(live_root / "scenario_clo_stress.csv", index=False)

        with pytest.raises(mod.ContractError, match="valuation anchor"):
            mod.run_pipeline(
                mod.RunConfig(
                    data_mode="live",
                    live_root=live_root,
                    output_root=root / "rendered",
                    num_paths=128,
                    seed=37,
                )
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)
