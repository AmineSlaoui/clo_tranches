# (c) 2027, Michael Robbins
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from CLO import DEFAULT_DISCOUNT_RATE, DEFAULT_REFERENCE_RATE, LIVE_CONTRACT_COLUMNS


FIELD_DICTIONARY_NAME = "field_dictionary.csv"
STAGE_METADATA_NAME = "stage_metadata.json"
FALLBACK_DATE_COLUMNS = {"as_of_date", "report_date"}
ROUTE_DEFAULTS = {
    "bloomberg_market_observed": {
        "source_family": "bloomberg_clo",
        "pack_label": "licensed",
        "route_label": "bloomberg_terminal_excel_airgap",
    },
    "public_bdc_clo_case_study": {
        "source_family": "public_deal_docs",
        "pack_label": "public",
        "route_label": "public_bdc_clo_case_study",
    },
    "free_public_case_study": {
        "source_family": "public_deal_docs",
        "pack_label": "public",
        "route_label": "public_bdc_clo_case_study",
    },
}

ALIAS_MAPS: dict[str, dict[str, tuple[str, ...]]] = {
    "fact_clo_collateral_position": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "as_of_date": ("as_of_date", "date", "position_date", "pricing_date"),
        "loan_id": ("loan_id", "asset_id", "loan_identifier", "cusip", "id_bb_global"),
        "sector": ("sector", "industry", "loan_sector", "issuer_industry"),
        "current_balance": ("current_balance", "balance", "par_amount", "position", "exposure", "principal_par"),
        "annual_pd": ("annual_pd", "pd_1y", "prob_default_1y", "default_probability_1y"),
        "annual_cpr": ("annual_cpr", "cpr_1y", "prepay_rate_1y", "annual_prepay_rate"),
        "lgd": ("lgd", "loss_given_default"),
        "loan_identifier": ("loan_identifier", "issuer", "asset_name", "portfolio_company"),
        "rating": ("rating", "composite_rating", "loan_rating", "facility_rating"),
        "market_price": ("market_price", "price", "mid_price", "bval_price", "evaluated_price"),
        "coupon_spread_bps": ("coupon_spread_bps", "coupon", "margin_bps", "spread_bps"),
        "reference_rate": ("reference_rate", "base_rate", "index_rate", "reference_index_rate"),
        "coupon_floor": ("coupon_floor", "floor", "rate_floor"),
        "maturity_years": ("maturity_years", "years_to_maturity", "remaining_term_years"),
        "discount_margin_bps": ("discount_margin_bps", "discount_margin", "dm_bps", "yield_spread_bps"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "dim_clo_tranche": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "tranche": ("tranche", "class", "bond_class", "tranche_name", "security_name"),
        "attach": ("attach", "attachment", "attachment_point"),
        "detach": ("detach", "detachment", "detachment_point"),
        "trigger_level": ("trigger_level", "oc_trigger_level", "trigger", "oc_test_level"),
        "coupon_bps": ("coupon_bps", "coupon", "margin_bps", "spread_bps"),
        "cusip": ("cusip", "security_cusip", "security_id"),
        "figi": ("figi", "id_bb_global", "bbg_figi"),
        "manager_name": ("manager_name", "manager", "collateral_manager"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "agg_clo_cohort_default": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "year": ("year", "vintage_year", "calendar_year"),
        "cohort_key": ("cohort_key", "sector", "industry", "rating_bucket", "cohort"),
        "cohort_size": ("cohort_size", "loan_count", "obligor_count", "count"),
        "defaults": ("defaults", "default_count"),
        "annual_pd": ("annual_pd", "pd_1y", "default_probability_1y"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "fact_clo_manager_report": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "report_date": ("report_date", "date", "as_of_date"),
        "tranche": ("tranche", "class", "bond_class", "tranche_name"),
        "oc_ratio": ("oc_ratio", "oc", "overcollateralization_ratio"),
        "oc_trigger_level": ("oc_trigger_level", "trigger_level", "oc_trigger"),
        "ic_ratio": ("ic_ratio", "interest_coverage_ratio"),
        "ccc_bucket_pct": ("ccc_bucket_pct", "ccc_pct", "ccc_bucket"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "fact_clo_default_event": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "loan_id": ("loan_id", "asset_id", "loan_identifier", "cusip"),
        "default_date": ("default_date", "event_date", "date"),
        "defaulted_balance": ("defaulted_balance", "default_balance", "balance"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "fact_clo_recovery_event": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "loan_id": ("loan_id", "asset_id", "loan_identifier", "cusip"),
        "recovery_date": ("recovery_date", "event_date", "date"),
        "recovered_balance": ("recovered_balance", "recovery_balance", "balance"),
        "recovery_rate": ("recovery_rate", "recovery_pct"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "fact_clo_tranche_cashflow": {
        "deal_id": ("deal_id", "deal", "deal_name", "transaction_name"),
        "tranche": ("tranche", "class", "bond_class", "tranche_name"),
        "payment_date": ("payment_date", "date", "distribution_date"),
        "interest_cash": ("interest_cash", "interest_distribution", "interest"),
        "principal_cash": ("principal_cash", "principal_distribution", "principal"),
        "outstanding_balance": ("outstanding_balance", "balance", "ending_balance"),
        "source_family": ("source_family", "data_source", "source"),
    },
    "scenario_clo_stress": {
        "scenario": ("scenario", "stress_name", "label"),
        "rho": ("rho", "asset_correlation", "correlation"),
        "base_rho": ("base_rho", "base_asset_correlation"),
        "rho_multiplier": ("rho_multiplier", "correlation_multiplier"),
        "pd_multiplier": ("pd_multiplier", "default_multiplier"),
        "cpr_multiplier": ("cpr_multiplier", "prepay_multiplier"),
        "lgd_addon": ("lgd_addon", "lgd_stress", "lgd_shift"),
        "discount_rate": ("discount_rate", "disc_rate"),
        "source_family": ("source_family", "data_source", "source"),
        "pack_label": ("pack_label",),
    },
}

OUTPUT_COLUMNS: dict[str, list[str]] = {
    "fact_clo_collateral_position": [
        "deal_id",
        "as_of_date",
        "loan_id",
        "sector",
        "current_balance",
        "annual_pd",
        "annual_cpr",
        "lgd",
        "loan_identifier",
        "rating",
        "market_price",
        "coupon_spread_bps",
        "reference_rate",
        "coupon_floor",
        "maturity_years",
        "discount_margin_bps",
        "source_family",
    ],
    "dim_clo_tranche": [
        "deal_id",
        "tranche",
        "attach",
        "detach",
        "trigger_level",
        "coupon_bps",
        "cusip",
        "figi",
        "manager_name",
        "source_family",
    ],
    "agg_clo_cohort_default": [
        "deal_id",
        "year",
        "cohort_key",
        "cohort_size",
        "defaults",
        "annual_pd",
        "source_family",
    ],
    "fact_clo_manager_report": [
        "deal_id",
        "report_date",
        "tranche",
        "oc_ratio",
        "oc_trigger_level",
        "ic_ratio",
        "ccc_bucket_pct",
        "source_family",
    ],
    "fact_clo_default_event": [
        "deal_id",
        "loan_id",
        "default_date",
        "defaulted_balance",
        "source_family",
    ],
    "fact_clo_recovery_event": [
        "deal_id",
        "loan_id",
        "recovery_date",
        "recovered_balance",
        "recovery_rate",
        "source_family",
    ],
    "fact_clo_tranche_cashflow": [
        "deal_id",
        "tranche",
        "payment_date",
        "interest_cash",
        "principal_cash",
        "outstanding_balance",
        "source_family",
    ],
    "scenario_clo_stress": [
        "scenario",
        "rho",
        "base_rho",
        "rho_multiplier",
        "pd_multiplier",
        "cpr_multiplier",
        "lgd_addon",
        "discount_rate",
        "source_family",
        "pack_label",
    ],
}


def _normalized_column_lookup(frame: pd.DataFrame) -> dict[str, str]:
    return {str(column).strip().lower(): str(column) for column in frame.columns}


def _pick_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> pd.Series | None:
    lookup = _normalized_column_lookup(frame)
    for alias in aliases:
        if alias in lookup:
            return frame[lookup[alias]]
    return None


def _normalize_frame(
    frame: pd.DataFrame,
    table_id: str,
    deal_id: str,
    default_source_family: str,
    as_of_date: str | None = None,
) -> pd.DataFrame:
    output: dict[str, pd.Series] = {}
    for column in OUTPUT_COLUMNS[table_id]:
        series = _pick_column(frame, ALIAS_MAPS[table_id].get(column, (column,)))
        if series is not None:
            output[column] = series
            continue
        if column == "deal_id":
            output[column] = pd.Series([deal_id] * len(frame))
        elif column == "source_family":
            output[column] = pd.Series([default_source_family] * len(frame))
        elif table_id == "fact_clo_collateral_position" and column == "loan_identifier":
            loan_series = _pick_column(frame, ALIAS_MAPS[table_id].get("loan_id", ("loan_id",)))
            output[column] = loan_series.astype(str) if loan_series is not None else pd.Series([pd.NA] * len(frame))
        elif table_id == "fact_clo_collateral_position" and column == "rating":
            output[column] = pd.Series(["B"] * len(frame))
        elif table_id == "fact_clo_collateral_position" and column == "reference_rate":
            output[column] = pd.Series([DEFAULT_REFERENCE_RATE] * len(frame))
        elif table_id == "fact_clo_collateral_position" and column == "coupon_floor":
            output[column] = pd.Series([0.01] * len(frame))
        elif table_id == "fact_clo_collateral_position" and column in {
            "market_price",
            "coupon_spread_bps",
            "maturity_years",
            "discount_margin_bps",
        }:
            output[column] = pd.Series([pd.NA] * len(frame))
        elif column in FALLBACK_DATE_COLUMNS and as_of_date is not None:
            output[column] = pd.Series([as_of_date] * len(frame))
    normalized = pd.DataFrame(output)
    missing_required = sorted(set(LIVE_CONTRACT_COLUMNS[table_id]) - set(normalized.columns))
    if missing_required:
        raise ValueError(
            f"Could not normalize '{table_id}' because the raw export did not expose: {', '.join(missing_required)}."
        )
    return normalized[[column for column in OUTPUT_COLUMNS[table_id] if column in normalized.columns]]


def _build_stress_frame(
    args: argparse.Namespace,
    default_source_family: str,
    default_pack_label: str,
) -> pd.DataFrame:
    if args.stress_export is not None:
        frame = pd.read_csv(args.stress_export)
        normalized = _normalize_frame(
            frame,
            "scenario_clo_stress",
            args.deal_id,
            default_source_family,
            getattr(args, "as_of_date", None),
        )
        if "pack_label" not in normalized.columns:
            normalized["pack_label"] = default_pack_label
        return normalized

    if args.low_rho is None or args.high_rho is None:
        raise ValueError("Provide --stress-export or explicit --low-rho and --high-rho values.")

    base_rho = args.base_rho if args.base_rho is not None else 0.5 * (args.low_rho + args.high_rho)
    rows = [
        {
            "scenario": "low",
            "rho": args.low_rho,
            "base_rho": base_rho,
            "pd_multiplier": args.low_pd_multiplier,
            "cpr_multiplier": args.low_cpr_multiplier,
            "lgd_addon": args.low_lgd_addon,
            "discount_rate": args.discount_rate,
            "source_family": default_source_family,
            "pack_label": default_pack_label,
        },
        {
            "scenario": "high",
            "rho": args.high_rho,
            "base_rho": base_rho,
            "pd_multiplier": args.high_pd_multiplier,
            "cpr_multiplier": args.high_cpr_multiplier,
            "lgd_addon": args.high_lgd_addon,
            "discount_rate": args.discount_rate,
            "source_family": default_source_family,
            "pack_label": default_pack_label,
        },
    ]
    return pd.DataFrame(rows)


def _write_if_supplied(
    output_dir: Path,
    table_id: str,
    source_path: Path | None,
    deal_id: str,
    default_source_family: str,
    as_of_date: str | None,
) -> Path | None:
    if source_path is None:
        return None
    frame = pd.read_csv(source_path)
    normalized = _normalize_frame(frame, table_id, deal_id, default_source_family, as_of_date)
    output_path = output_dir / f"{table_id}.csv"
    normalized.to_csv(output_path, index=False)
    return output_path


def _copy_field_dictionary(output_dir: Path, source_path: Path | None) -> Path | None:
    if source_path is None:
        return None
    destination = output_dir / FIELD_DICTIONARY_NAME
    shutil.copyfile(source_path, destination)
    return destination


def _resolved_path_string(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path.resolve())


def _write_stage_metadata(
    output_dir: Path,
    args: argparse.Namespace,
    route_defaults: dict[str, str],
    written_paths: list[Path],
    field_dictionary_path: Path | None,
) -> Path:
    metadata = {
        "route": route_defaults["route_label"],
        "route_argument": args.route,
        "deal_id": args.deal_id,
        "pack_label": route_defaults["pack_label"],
        "default_source_family": route_defaults["source_family"],
        "as_of_date": getattr(args, "as_of_date", None),
        "source_urls": list(getattr(args, "source_url", []) or []),
        "raw_inputs": {
            "tranche_export": _resolved_path_string(args.tranche_export),
            "collateral_export": _resolved_path_string(args.collateral_export),
            "cohort_export": _resolved_path_string(args.cohort_export),
            "manager_export": _resolved_path_string(args.manager_export),
            "default_export": _resolved_path_string(args.default_export),
            "recovery_export": _resolved_path_string(args.recovery_export),
            "cashflow_export": _resolved_path_string(args.cashflow_export),
            "stress_export": _resolved_path_string(args.stress_export),
            "field_dictionary_export": _resolved_path_string(getattr(args, "field_dictionary_export", None)),
        },
        "rho_inputs": {
            "base_rho": args.base_rho,
            "low_rho": args.low_rho,
            "high_rho": args.high_rho,
            "low_pd_multiplier": args.low_pd_multiplier,
            "high_pd_multiplier": args.high_pd_multiplier,
            "low_cpr_multiplier": args.low_cpr_multiplier,
            "high_cpr_multiplier": args.high_cpr_multiplier,
            "low_lgd_addon": args.low_lgd_addon,
            "high_lgd_addon": args.high_lgd_addon,
            "discount_rate": args.discount_rate,
        },
        "output_files": [str(path.resolve()) for path in written_paths],
        "field_dictionary_path": _resolved_path_string(field_dictionary_path),
    }
    metadata_path = output_dir / STAGE_METADATA_NAME
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata_path


def stage_actual_contract(args: argparse.Namespace) -> list[Path]:
    route_defaults = ROUTE_DEFAULTS[args.route]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    as_of_date = getattr(args, "as_of_date", None)

    written: list[Path] = []
    required_tables = {
        "fact_clo_collateral_position": args.collateral_export,
        "dim_clo_tranche": args.tranche_export,
    }
    for table_id, source_path in required_tables.items():
        frame = pd.read_csv(source_path)
        normalized = _normalize_frame(frame, table_id, args.deal_id, route_defaults["source_family"], as_of_date)
        output_path = output_dir / f"{table_id}.csv"
        normalized.to_csv(output_path, index=False)
        written.append(output_path)

    optional_sources = {
        "agg_clo_cohort_default": args.cohort_export,
        "fact_clo_manager_report": args.manager_export,
        "fact_clo_default_event": args.default_export,
        "fact_clo_recovery_event": args.recovery_export,
        "fact_clo_tranche_cashflow": args.cashflow_export,
    }
    for table_id, source_path in optional_sources.items():
        output_path = _write_if_supplied(
            output_dir,
            table_id,
            source_path,
            args.deal_id,
            route_defaults["source_family"],
            as_of_date,
        )
        if output_path is not None:
            written.append(output_path)

    stress = _build_stress_frame(args, route_defaults["source_family"], route_defaults["pack_label"])
    stress_output = output_dir / "scenario_clo_stress.csv"
    stress.to_csv(stress_output, index=False)
    written.append(stress_output)

    field_dictionary_path = _copy_field_dictionary(output_dir, getattr(args, "field_dictionary_export", None))
    if field_dictionary_path is not None:
        written.append(field_dictionary_path)

    metadata_path = _write_stage_metadata(output_dir, args, route_defaults, written, field_dictionary_path)
    written.append(metadata_path)
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize Bloomberg air-gap or public case-study CLO exports into the Chapter 4 live contract."
    )
    parser.add_argument(
        "--route",
        choices=sorted(ROUTE_DEFAULTS),
        required=True,
        help="Choose the actual-data staging route.",
    )
    parser.add_argument("--deal-id", required=True, help="Representative deal identifier for the normalized bundle.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory where normalized CSVs are written.")
    parser.add_argument("--tranche-export", type=Path, required=True, help="CSV export with tranche terms.")
    parser.add_argument("--collateral-export", type=Path, required=True, help="CSV export with collateral rows.")
    parser.add_argument("--cohort-export", type=Path, help="Optional cohort-default panel for rho calibration.")
    parser.add_argument("--manager-export", type=Path, help="Optional manager-report export.")
    parser.add_argument("--default-export", type=Path, help="Optional loan default event export.")
    parser.add_argument("--recovery-export", type=Path, help="Optional loan recovery event export.")
    parser.add_argument("--cashflow-export", type=Path, help="Optional tranche cash-flow export.")
    parser.add_argument("--stress-export", type=Path, help="Optional prebuilt stress CSV to normalize.")
    parser.add_argument("--field-dictionary-export", type=Path, help="Optional Bloomberg field dictionary CSV.")
    parser.add_argument("--as-of-date", help="Fallback as-of date applied when an export omits it.")
    parser.add_argument(
        "--source-url",
        action="append",
        default=[],
        help="Optional provenance URL recorded in stage_metadata.json. Repeat for multiple sources.",
    )
    parser.add_argument("--base-rho", type=float, help="Optional base rho when stress rows are built from CLI values.")
    parser.add_argument("--low-rho", type=float, help="Low-scenario explicit rho.")
    parser.add_argument("--high-rho", type=float, help="High-scenario explicit rho.")
    parser.add_argument("--low-pd-multiplier", type=float, default=1.0)
    parser.add_argument("--high-pd-multiplier", type=float, default=1.0)
    parser.add_argument("--low-cpr-multiplier", type=float, default=1.0)
    parser.add_argument("--high-cpr-multiplier", type=float, default=1.0)
    parser.add_argument("--low-lgd-addon", type=float, default=0.0)
    parser.add_argument("--high-lgd-addon", type=float, default=0.0)
    parser.add_argument("--discount-rate", type=float, default=DEFAULT_DISCOUNT_RATE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    written = stage_actual_contract(args)
    print("Wrote normalized Chapter 4 live contract files:")
    for path in written:
        print(f"- {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
