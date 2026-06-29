# (c) 2027, Michael Robbins
"""Workflow helpers for the public Options Implied Ceasefire sample notebook."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
from matplotlib.ticker import PercentFormatter

_OUTPUT_TABLE_SPECS: dict[str, dict[str, Any]] = {
    "structural_ceasefire_futures_strip": {"parse_dates": None, "required": True},
    "cl_probability_curve_compare": {"parse_dates": ["target", "expiry"], "required": True},
    "uso_cl_driven_curve_compare": {"parse_dates": ["target", "expiry"], "required": True},
    "reverse_engineered_cl_event_curve_compare": {"parse_dates": ["target", "expiry"], "required": True},
    "uso_event_equivalent_curve_compare": {"parse_dates": ["target", "expiry"], "required": True},
    "inferred_event_sensitivity_envelope": {"parse_dates": ["expiry"], "required": False},
    "figure5_live_plot_table_long": {"parse_dates": ["x_date"], "required": True},
}

_PUBLIC_FIGURE_SERIES_PATTERNS = (
    "Inferred event-equivalent",
    "Source-truth-aligned",
    "Archived Polymarket",
    "CL front anchor expiries",
)


def _read_csv(path: Path, parse_dates: list[str] | None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=parse_dates)


def _output_contract_paths(bundle: Mapping[str, Any]) -> dict[str, Path]:
    root = Path(bundle["selected_root"])
    return {table_name: root / f"{table_name}.csv" for table_name in _OUTPUT_TABLE_SPECS}


def _load_output_contract(bundle: Mapping[str, Any]) -> dict[str, Any]:
    paths = _output_contract_paths(bundle)
    tables = {
        table_name: _read_csv(paths[table_name], spec["parse_dates"])
        for table_name, spec in _OUTPUT_TABLE_SPECS.items()
    }
    missing_required = [
        table_name
        for table_name, spec in _OUTPUT_TABLE_SPECS.items()
        if spec["required"] and tables[table_name].empty
    ]
    return {
        "paths": paths,
        "tables": tables,
        "missing_required": missing_required,
        "ready": not missing_required,
    }


def _first_token(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().split()[0]


def _analysis_date(bundle: Mapping[str, Any]) -> pd.Timestamp:
    value = bundle.get("analysis_date")
    if value is None:
        raise ValueError("Bundle is missing `analysis_date`.")
    return pd.Timestamp(value).normalize()


def _normalize_contract_panel(bundle: Mapping[str, Any], strip: pd.DataFrame) -> pd.DataFrame:
    panel = strip.copy()
    panel["future_contract_id"] = panel["ticker"].map(_first_token)

    contracts = bundle["tables"].get("futures_contracts", pd.DataFrame()).copy()
    if not contracts.empty:
        keep = [
            column
            for column in ["future_contract_id", "vendor_ticker", "expiry_date", "contract_month", "days_to_expiry_as_of"]
            if column in contracts.columns
        ]
        panel = panel.merge(contracts[keep], on="future_contract_id", how="left", suffixes=("", "_bundle"))

    analysis_date = _analysis_date(bundle)
    fallback_expiry = analysis_date + pd.to_timedelta(pd.to_numeric(panel.get("days_to_expiration"), errors="coerce"), unit="D")
    panel["vendor_ticker"] = panel.get("vendor_ticker").fillna(panel["ticker"]) if "vendor_ticker" in panel.columns else panel["ticker"]
    panel["option_expiry"] = pd.to_datetime(panel.get("expiry_date"), errors="coerce").fillna(fallback_expiry)
    panel["baseline_price"] = pd.to_numeric(panel.get("prewar_price"), errors="coerce")
    panel["asof_price"] = pd.to_numeric(panel.get("price"), errors="coerce")
    panel["war_premium"] = pd.to_numeric(panel.get("war_premium"), errors="coerce")
    panel["war_premium"] = panel["war_premium"].fillna(panel["asof_price"] - panel["baseline_price"])
    panel["days_to_expiry_as_of"] = pd.to_numeric(panel.get("days_to_expiration"), errors="coerce")
    panel["lambda_contract"] = pd.to_numeric(panel.get("state_weight"), errors="coerce")
    panel["ceasefire_threshold_full"] = pd.to_numeric(panel.get("ceasefire_price"), errors="coerce")
    panel["mapped_threshold_mean"] = panel["ceasefire_threshold_full"]
    return panel.sort_values("option_expiry").reset_index(drop=True)


def _normalize_cl_curve(frame: pd.DataFrame, curve_source: str) -> pd.DataFrame:
    curve = frame.copy()
    curve["deadline"] = pd.to_datetime(curve.get("target"), errors="coerce")
    curve["option_expiry"] = pd.to_datetime(curve.get("expiry"), errors="coerce")
    curve["deadline_label"] = curve.get("label")
    curve["deadline_label"] = curve["deadline_label"].fillna(curve["deadline"].dt.strftime("%Y-%m-%d"))
    curve["future_contract_id"] = curve.get("underlying_ticker", curve.get("source_sheet", curve.get("label"))).map(_first_token)
    curve["ceasefire_threshold"] = pd.to_numeric(curve.get("target_kstar"), errors="coerce")
    curve["ceasefire_threshold"] = curve["ceasefire_threshold"].fillna(pd.to_numeric(curve.get("structural_kstar"), errors="coerce"))
    curve["lambda_contract"] = pd.to_numeric(curve.get("fitted_multiplier"), errors="coerce")
    curve["removal_fraction"] = curve["lambda_contract"]
    curve["surface_points"] = pd.to_numeric(curve.get("probability_weight"), errors="coerce").fillna(1.0)
    curve["probability_raw"] = pd.to_numeric(curve.get("probability_raw"), errors="coerce")
    curve["probability"] = pd.to_numeric(curve.get("probability"), errors="coerce")
    curve["probability_raw"] = curve["probability_raw"].fillna(curve["probability"])
    curve["curve_source"] = curve_source
    return curve.sort_values("deadline").reset_index(drop=True)


def _normalize_uso_curve(
    frame: pd.DataFrame,
    curve_source: str,
    probability_column: str,
    raw_probability_column: str,
    target_column: str,
) -> pd.DataFrame:
    curve = frame.copy()
    curve["deadline"] = pd.to_datetime(curve.get("target", curve.get("expiry")), errors="coerce")
    curve["option_expiry"] = pd.to_datetime(curve.get("expiry"), errors="coerce")
    curve["deadline_label"] = curve.get("label")
    curve["deadline_label"] = curve["deadline_label"].fillna(curve["deadline"].dt.strftime("%Y-%m-%d"))
    curve["target_probability"] = pd.to_numeric(curve.get(target_column), errors="coerce")
    curve["bootstrap_kstar"] = pd.to_numeric(curve.get("cl_led_kstar"), errors="coerce")
    curve["bootstrap_kstar"] = curve["bootstrap_kstar"].fillna(pd.to_numeric(curve.get("terminal_equivalent_kstar"), errors="coerce"))
    curve["bootstrap_kstar"] = curve["bootstrap_kstar"].fillna(pd.to_numeric(curve.get("structural_kstar"), errors="coerce"))
    curve["threshold_ratio"] = pd.to_numeric(curve.get("ceasefire_basket_ratio"), errors="coerce")
    curve["uso_forward"] = pd.to_numeric(curve.get("uso_forward"), errors="coerce")
    curve["probability_raw"] = pd.to_numeric(curve.get(raw_probability_column), errors="coerce")
    curve["probability"] = pd.to_numeric(curve.get(probability_column), errors="coerce")
    curve["probability_raw"] = curve["probability_raw"].fillna(curve["probability"])
    curve["surface_points"] = 1.0
    curve["curve_source"] = curve_source
    return curve.sort_values("deadline").reset_index(drop=True)


def _normalize_sensitivity_envelope(frame: pd.DataFrame) -> pd.DataFrame:
    envelope = frame.copy()
    envelope["deadline"] = pd.to_datetime(envelope.get("expiry"), errors="coerce")
    envelope["probability_low"] = pd.to_numeric(envelope.get("probability_low"), errors="coerce")
    envelope["probability_high"] = pd.to_numeric(envelope.get("probability_high"), errors="coerce")
    envelope["probability_median"] = pd.to_numeric(envelope.get("probability_median"), errors="coerce")
    return envelope.sort_values("deadline").reset_index(drop=True)


def _retain_public_figure_series(table: pd.DataFrame) -> pd.DataFrame:
    filtered = table.copy()
    series_name = filtered.get("series_name", pd.Series(index=filtered.index, dtype="object")).astype(str)
    mask = pd.Series(False, index=filtered.index)
    for pattern in _PUBLIC_FIGURE_SERIES_PATTERNS:
        mask = mask | series_name.str.contains(pattern, regex=False, na=False)
    return filtered.loc[mask].reset_index(drop=True)


def _normalize_figure_table(frame: pd.DataFrame) -> pd.DataFrame:
    table = frame.copy()
    table["x_date"] = pd.to_datetime(table.get("x_date"), errors="coerce")
    table["y_probability"] = pd.to_numeric(table.get("y_probability"), errors="coerce")
    table["y_probability_low"] = pd.to_numeric(table.get("y_probability_low"), errors="coerce")
    table["y_probability_high"] = pd.to_numeric(table.get("y_probability_high"), errors="coerce")
    table = _retain_public_figure_series(table)
    return table.sort_values(["plot_order", "x_date", "series_name"]).reset_index(drop=True)


def run_options_implied_ceasefire_workflow(
    bundle: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _ = config
    contract = _load_output_contract(bundle)
    if contract["missing_required"]:
        raise FileNotFoundError(
            "Missing required chapter-output contract tables: " + ", ".join(contract["missing_required"])
        )

    output_tables = contract["tables"]
    contract_panel = _normalize_contract_panel(bundle, output_tables["structural_ceasefire_futures_strip"])
    cl_curve = _normalize_cl_curve(output_tables["cl_probability_curve_compare"], "source_truth_aligned_cl")
    uso_curve = _normalize_uso_curve(
        output_tables["uso_cl_driven_curve_compare"],
        "source_truth_aligned_uso",
        probability_column="cl_led_probability",
        raw_probability_column="cl_led_probability_raw",
        target_column="cl_target_probability",
    )
    event_equivalent_cl_curve = _normalize_cl_curve(
        output_tables["reverse_engineered_cl_event_curve_compare"],
        "inferred_event_equivalent_cl",
    )
    event_equivalent_uso_curve = _normalize_uso_curve(
        output_tables["uso_event_equivalent_curve_compare"],
        "inferred_event_equivalent_uso",
        probability_column="terminal_equivalent_probability",
        raw_probability_column="terminal_equivalent_probability_raw",
        target_column="jpm_target_probability",
    )
    sensitivity_envelope = _normalize_sensitivity_envelope(output_tables["inferred_event_sensitivity_envelope"])
    figure_table = _normalize_figure_table(output_tables["figure5_live_plot_table_long"])

    summary = {
        "data_mode": bundle["config"]["data_mode"],
        "analysis_date": bundle["analysis_date"],
        "workflow_variant": "bundled_output_contract",
        "contract_panel_count": int(len(contract_panel.index)),
        "cl_curve_points": int(len(cl_curve.index)),
        "uso_curve_points": int(len(uso_curve.index)),
        "event_equivalent_cl_points": int(len(event_equivalent_cl_curve.index)),
        "event_equivalent_uso_points": int(len(event_equivalent_uso_curve.index)),
        "sensitivity_points": int(len(sensitivity_envelope.index)),
        "figure_series_count": int(figure_table["series_name"].nunique()) if not figure_table.empty else 0,
        "output_contract_ready": contract["ready"],
    }
    return {
        "summary": summary,
        "contract_panel": contract_panel,
        "cl_event_curve": cl_curve,
        "uso_validation_curve": uso_curve,
        "event_equivalent_cl_curve": event_equivalent_cl_curve,
        "event_equivalent_uso_curve": event_equivalent_uso_curve,
        "sensitivity_envelope": sensitivity_envelope,
        "figure_table": figure_table,
        "output_contract_paths": {name: str(path) for name, path in contract["paths"].items()},
    }


def _style_value(value: Any, default: str | None = None) -> str | None:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text or default


def _plot_event_figure(figure_table: pd.DataFrame, summary: Mapping[str, Any], note: str) -> Any:
    frame = figure_table.copy()
    if frame.empty:
        fig, ax = plt.subplots(figsize=(11.8, 6.8))
        ax.text(0.5, 0.5, "No Figure 5 contract rows available.", ha="center", va="center")
        ax.axis("off")
        return fig

    fig, ax = plt.subplots(figsize=(11.8, 6.8))
    primary_handles = []
    primary_labels = []
    diagnostic_handles = []
    diagnostic_labels = []
    line_style_map = {"solid": "-", "dashed": "--", "dotted": ":", "fill": "-"}

    for (_, series_name), series in frame.groupby(["plot_order", "series_name"], sort=True):
        series = series.sort_values("x_date")
        first = series.iloc[0]
        color = _style_value(first.get("color_hex"), "#444444")
        plot_type = _style_value(first.get("plot_type"), "line").lower()
        diagnostic_only = str(first.get("diagnostic_only")).strip().lower() == "true"
        marker = _style_value(first.get("marker"), None)
        linestyle = line_style_map.get(_style_value(first.get("line_style"), "solid").lower(), "-")

        if plot_type == "band":
            handle = ax.fill_between(
                series["x_date"],
                series["y_probability_low"],
                series["y_probability_high"],
                color=color,
                alpha=0.24,
                linewidth=0.0,
                label=series_name,
            )
            ax.plot(series["x_date"], series["y_probability"], color=color, linewidth=1.2, alpha=0.85)
        else:
            (handle,) = ax.plot(
                series["x_date"],
                series["y_probability"],
                color=color,
                linestyle=linestyle,
                marker=marker,
                linewidth=2.6 if not diagnostic_only else 1.8,
                markersize=6 if not diagnostic_only else 5,
                alpha=0.96 if not diagnostic_only else 0.84,
                label=series_name,
            )

        if diagnostic_only:
            diagnostic_handles.append(handle)
            diagnostic_labels.append(series_name)
        else:
            primary_handles.append(handle)
            primary_labels.append(series_name)

    analysis_date = pd.Timestamp(summary["analysis_date"]).strftime("%Y-%m-%d") if summary.get("analysis_date") else "n/a"
    ax.set_title("CL/USO ceasefire-timing reconstruction with sensitivity envelope", loc="left", pad=16)
    ax.text(
        0.0,
        1.02,
        f"Analysis date {analysis_date} | bundled fake sample data",
        transform=ax.transAxes,
        fontsize=9,
        color="#444444",
        va="bottom",
    )
    ax.set_ylabel("Probability")
    ax.set_xlabel("Deadline")
    ax.set_ylim(0.0, 1.0)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.22, linewidth=0.8)
    ax.grid(axis="x", alpha=0.08, linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if primary_handles:
        primary_legend = ax.legend(
            primary_handles,
            primary_labels,
            loc="upper left",
            frameon=False,
            title="Primary and standalone series",
            fontsize=8.5,
            title_fontsize=9,
        )
        ax.add_artist(primary_legend)
    if diagnostic_handles:
        ax.legend(
            diagnostic_handles,
            diagnostic_labels,
            loc="lower right",
            frameon=False,
            title="Diagnostic only",
            fontsize=8.5,
            title_fontsize=9,
        )
    ax.text(
        0.015,
        0.02,
        note,
        transform=ax.transAxes,
        fontsize=8.4,
        color="#555555",
        va="bottom",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#f7f4ef", "edgecolor": "#ddd2c2", "alpha": 0.95},
    )
    fig.tight_layout()
    return fig


def _plot_strip_figure(contract_panel: pd.DataFrame, summary: Mapping[str, Any]) -> Any:
    if contract_panel.empty:
        fig, ax = plt.subplots(figsize=(11.5, 5.8))
        ax.text(0.5, 0.5, "No structural ceasefire strip available.", ha="center", va="center")
        ax.axis("off")
        return fig

    panel = contract_panel.copy().sort_values("option_expiry")
    fig, ax = plt.subplots(figsize=(11.5, 5.8))
    ax.fill_between(
        panel["option_expiry"],
        panel["baseline_price"],
        panel["asof_price"],
        color="#d8c2b6",
        alpha=0.35,
        label="War-premium wedge",
    )
    ax.plot(panel["option_expiry"], panel["asof_price"], color="#8c564b", marker="o", linewidth=2.6, label="As-of CL strip")
    ax.plot(panel["option_expiry"], panel["baseline_price"], color="#6f6f6f", marker="s", linewidth=2.1, label="Pre-war CL strip")
    ax.plot(panel["option_expiry"], panel["ceasefire_threshold_full"], color="#2f7d32", marker="d", linewidth=2.2, linestyle="--", label="Ceasefire strip")
    if panel["mapped_threshold_mean"].notna().any():
        ax.plot(panel["option_expiry"], panel["mapped_threshold_mean"], color="#0b7285", marker="^", linewidth=2.1, linestyle=":", label="Mapped threshold mean")
    ax.set_title("Structural ceasefire futures strip", loc="left", pad=16)
    ax.text(
        0.0,
        1.02,
        f"Rendered from bundled fake sample data | mode {summary['data_mode']}",
        transform=ax.transAxes,
        fontsize=9,
        color="#444444",
        va="bottom",
    )
    ax.set_ylabel("Price")
    ax.set_xlabel("Option expiry")
    ax.xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.22, linewidth=0.8)
    ax.grid(axis="x", alpha=0.08, linewidth=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="best", frameon=False, fontsize=8.5)
    fig.tight_layout()
    return fig


def plot_options_implied_ceasefire_figures(result: Mapping[str, Any]) -> tuple[Any, Any]:
    note = "This figure is rendered directly from the bundled fake output-contract tables used by the sample notebook."
    fig_event = _plot_event_figure(result["figure_table"], result["summary"], note)
    fig_strip = _plot_strip_figure(result["contract_panel"], result["summary"])
    return fig_event, fig_strip
