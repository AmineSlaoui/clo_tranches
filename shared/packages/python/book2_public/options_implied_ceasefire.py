# (c) 2027, Michael Robbins
"""Load bundled fake data for the public Options Implied Ceasefire example."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd

_REPO_ROOT_FALLBACK = Path(__file__).resolve().parents[3]

_DEFAULT_CONFIG: dict[str, Any] = {
    "data_mode": "sample",
    "pack_label": "scenario",
    "as_of_date": None,
    "strict": False,
}

_NOTEBOOK_SECTIONS = [
    "Title and chapter context",
    "Configuration",
    "Load data",
    "Structural strip",
    "CL probability curve",
    "USO validation curve",
    "Event-equivalent diagnostics",
    "Sensitivity envelope",
    "Figure contract",
    "Interpretation",
]

_TABLE_SPECS: dict[str, dict[str, Any]] = {
    "futures_contracts": {
        "role": "required",
        "parse_dates": ["expiry_date", "analysis_date"],
        "columns": [
            "future_contract_id",
            "underlying_root",
            "vendor_ticker",
            "contract_month",
            "expiry_date",
            "contract_size",
            "days_to_expiry_as_of",
            "analysis_date",
            "source_quality_flag",
        ],
    },
    "futures_prices_daily": {
        "role": "required",
        "parse_dates": ["date", "expiry_date"],
        "columns": [
            "future_contract_id",
            "vendor_ticker",
            "date",
            "expiry_date",
            "close_price",
            "settle_price",
            "days_to_expiry",
            "field",
            "source_quality_flag",
        ],
    },
    "cl_option_surface_nodes": {
        "role": "required",
        "parse_dates": ["date", "expiry_date"],
        "columns": [
            "future_contract_id",
            "vendor_ticker",
            "date",
            "expiry_date",
            "source_table",
            "node_type",
            "node_value",
            "strike",
            "implied_vol",
            "option_side",
            "bid",
            "ask",
            "last",
            "volume",
            "source_quality_flag",
        ],
    },
    "uso_option_surface_nodes": {
        "role": "required",
        "parse_dates": ["date", "expiry_date"],
        "columns": [
            "security_id",
            "vendor_ticker",
            "date",
            "expiry_date",
            "source_table",
            "node_type",
            "node_value",
            "strike",
            "implied_vol",
            "option_side",
            "bid",
            "ask",
            "last",
            "volume",
            "source_quality_flag",
        ],
    },
    "event_deadlines": {
        "role": "required",
        "parse_dates": ["event_deadline"],
        "columns": [
            "event_deadline",
            "deadline_label",
            "source_family",
            "source_family_title",
            "is_primary_curve",
            "exact_front_end_match",
            "near_front_end_match_within_7d",
            "source_quality_flag",
        ],
    },
    "polymarket_curve": {
        "role": "diagnostic",
        "parse_dates": ["x_date"],
        "columns": [
            "x_date",
            "y_probability",
            "series_title",
            "series_key",
            "component_count",
            "proxy_method",
            "source_quality_flag",
        ],
    },
    "figure5_plot_table_reference": {
        "role": "diagnostic",
        "parse_dates": ["x_date"],
        "columns": [
            "series_name",
            "series_group",
            "plot_type",
            "plot_order",
            "x_date",
            "y_probability",
            "y_probability_low",
            "y_probability_high",
            "point_label",
            "color_hex",
            "line_style",
            "marker",
            "diagnostic_only",
            "source_file",
        ],
    },
    "cl_probability_curve_reference": {
        "role": "diagnostic",
        "parse_dates": ["target", "expiry"],
        "columns": [
            "target",
            "expiry",
            "label",
            "horizon_days",
            "source_sheet",
            "underlying_ticker",
            "structural_kstar",
            "probability_raw",
            "probability_weight",
            "approximation",
            "probability",
            "fit_residual",
            "probability_model",
            "source_quality_flag",
        ],
    },
    "uso_validation_curve_reference": {
        "role": "diagnostic",
        "parse_dates": ["expiry"],
        "columns": [
            "expiry",
            "target_probability",
            "uso_forward",
            "current_basket_price",
            "ceasefire_basket_price",
            "ceasefire_basket_ratio",
            "bootstrap_kstar",
            "uso_probability_surface_direct",
            "uso_probability_parametric",
            "curve_source",
            "source_quality_flag",
        ],
    },
}

_REQUIRED_TABLES = [name for name, spec in _TABLE_SPECS.items() if spec["role"] == "required"]
_DIAGNOSTIC_TABLES = [name for name, spec in _TABLE_SPECS.items() if spec["role"] == "diagnostic"]


def _resolve_repo_root(start: Path | None = None) -> Path:
    search_root = (start or Path.cwd()).resolve()
    for candidate in (search_root, *search_root.parents):
        if (candidate / "packages" / "python" / "book2_public").is_dir():
            return candidate
        nested_repo = candidate / "repo"
        if (nested_repo / "packages" / "python" / "book2_public").is_dir():
            return nested_repo
    return _REPO_ROOT_FALLBACK


def _merge_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(_DEFAULT_CONFIG)
    if config:
        merged.update(dict(config))

    data_mode = str(merged["data_mode"]).strip().lower()
    if data_mode != "sample":
        raise NotImplementedError(
            "`sample` is the only public repo mode. Any licensed run should fetch data live outside the repo."
        )

    merged["data_mode"] = data_mode
    merged["pack_label"] = str(merged["pack_label"]).strip().lower()
    merged["strict"] = bool(merged.get("strict", False))
    return merged


def _empty_table(table_name: str) -> pd.DataFrame:
    return pd.DataFrame(columns=_TABLE_SPECS[table_name]["columns"])


def _read_table(path: Path, table_name: str) -> pd.DataFrame:
    if not path.exists():
        return _empty_table(table_name)

    try:
        frame = pd.read_csv(path, parse_dates=_TABLE_SPECS[table_name]["parse_dates"])
    except pd.errors.EmptyDataError:
        return _empty_table(table_name)

    expected = list(_TABLE_SPECS[table_name]["columns"])
    for column in expected:
        if column not in frame.columns:
            frame[column] = pd.NA
    remaining = [column for column in frame.columns if column not in expected]
    return frame[expected + remaining]


def _load_tables(sample_root: Path) -> tuple[dict[str, pd.DataFrame], dict[str, list[Path]]]:
    tables: dict[str, pd.DataFrame] = {}
    sources: dict[str, list[Path]] = {}
    for table_name in _TABLE_SPECS:
        path = sample_root / f"{table_name}.csv"
        tables[table_name] = _read_table(path, table_name)
        sources[table_name] = [path]
    return tables, sources


def _resolve_analysis_date(tables: Mapping[str, pd.DataFrame], configured_as_of: Any) -> pd.Timestamp | None:
    if configured_as_of is not None:
        timestamp = pd.to_datetime(configured_as_of, errors="coerce")
        return pd.Timestamp(timestamp).normalize() if pd.notna(timestamp) else None

    contracts = tables["futures_contracts"]
    if not contracts.empty:
        timestamp = pd.to_datetime(contracts["analysis_date"], errors="coerce").dropna().max()
        if pd.notna(timestamp):
            return pd.Timestamp(timestamp).normalize()

    prices = tables["futures_prices_daily"]
    if not prices.empty:
        timestamp = pd.to_datetime(prices["date"], errors="coerce").dropna().max()
        if pd.notna(timestamp):
            return pd.Timestamp(timestamp).normalize()

    return None


def _build_table_summaries(
    tables: Mapping[str, pd.DataFrame],
    sources: Mapping[str, list[Path]],
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for table_name, frame in tables.items():
        paths = sources[table_name]
        missing_paths = [str(path) for path in paths if not path.exists()]
        summaries[table_name] = {
            "role": _TABLE_SPECS[table_name]["role"],
            "rows": int(len(frame.index)),
            "column_count": int(len(frame.columns)),
            "columns": list(frame.columns),
            "source_paths": [str(path) for path in paths],
            "missing_source_paths": missing_paths,
            "schema_staged": not missing_paths,
            "nonempty": not frame.empty,
        }
    return summaries


def _build_summary(table_summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    required = [table_summaries[name] for name in _REQUIRED_TABLES]
    diagnostics = [table_summaries[name] for name in _DIAGNOSTIC_TABLES]
    missing_required = [name for name in _REQUIRED_TABLES if table_summaries[name]["missing_source_paths"]]
    empty_required = [name for name in _REQUIRED_TABLES if not table_summaries[name]["nonempty"]]
    return {
        "required_total": len(required),
        "required_schema_staged": sum(1 for item in required if item["schema_staged"]),
        "required_nonempty": sum(1 for item in required if item["nonempty"]),
        "diagnostic_total": len(diagnostics),
        "diagnostic_schema_staged": sum(1 for item in diagnostics if item["schema_staged"]),
        "diagnostic_nonempty": sum(1 for item in diagnostics if item["nonempty"]),
        "schema_staged": not missing_required,
        "ready_for_analysis": not missing_required and not empty_required,
        "missing_required_objects": missing_required,
        "empty_required_objects": empty_required,
    }


def load_options_implied_ceasefire(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return notebook-friendly tables for the bundled sample dataset."""

    resolved_config = _merge_config(config)
    repo_root = _resolve_repo_root()
    sample_root = repo_root / "packs" / resolved_config["pack_label"] / "options-implied-ceasefire"

    tables, sources = _load_tables(sample_root)
    analysis_date = _resolve_analysis_date(tables, resolved_config.get("as_of_date"))
    table_summaries = _build_table_summaries(tables, sources)
    summary = _build_summary(table_summaries)

    if resolved_config["strict"] and (summary["missing_required_objects"] or summary["empty_required_objects"]):
        problems: list[str] = []
        if summary["missing_required_objects"]:
            problems.append("missing required objects: " + ", ".join(summary["missing_required_objects"]))
        if summary["empty_required_objects"]:
            problems.append("empty required objects: " + ", ".join(summary["empty_required_objects"]))
        raise FileNotFoundError("; ".join(problems))

    return {
        "chapter_id": "ceasefire_implied_uso",
        "config": resolved_config,
        "repo_root": str(repo_root),
        "selected_root": str(sample_root),
        "analysis_date": analysis_date.isoformat() if analysis_date is not None else None,
        "workflow_sections": list(_NOTEBOOK_SECTIONS),
        "tables": tables,
        "table_summaries": table_summaries,
        "summary": summary,
        "notes": [
            "The public notebook runs on the bundled fake scenario dataset.",
            "All required chapter tables are loaded directly from the staged sample pack.",
            "Any licensed run should happen outside the repo in a private environment.",
        ],
    }
