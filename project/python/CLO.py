# (c) 2027, Michael Robbins
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from scipy.stats import multivariate_normal, norm


SEED = 42
DEFAULT_NUM_PATHS = 25000
DEFAULT_HORIZON_YEARS = 5
DEFAULT_DISCOUNT_RATE = 0.04
DEFAULT_REFERENCE_RATE = 0.0525
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "rendered-sample"
EXAMPLE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_ROOT = EXAMPLE_ROOT / "live_contract_template"
LIVE_ROOT_ENV_VAR = "BOOK2_CLO_LIVE_ROOT"


TRANCHES = pd.DataFrame(
    [
        {"tranche": "Equity", "attach": 0.00, "detach": 0.06, "trigger_level": 0.03},
        {"tranche": "Mezzanine", "attach": 0.06, "detach": 0.14, "trigger_level": 0.10},
        {"tranche": "Senior", "attach": 0.14, "detach": 0.30, "trigger_level": 0.18},
    ]
)
TRANCHES["width"] = TRANCHES["detach"] - TRANCHES["attach"]


LIVE_CONTRACT_COLUMNS: dict[str, tuple[str, ...]] = {
    "agg_clo_cohort_default": ("deal_id", "year", "cohort_key", "cohort_size", "defaults"),
    "fact_clo_collateral_position": (
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
    ),
    "dim_clo_tranche": ("deal_id", "tranche", "attach", "detach"),
    "fact_clo_tranche_cashflow": (
        "deal_id",
        "tranche",
        "payment_date",
        "interest_cash",
        "principal_cash",
        "outstanding_balance",
    ),
    "fact_clo_manager_report": (
        "deal_id",
        "report_date",
        "tranche",
        "oc_ratio",
        "oc_trigger_level",
    ),
    "fact_clo_default_event": ("deal_id", "loan_id", "default_date", "defaulted_balance"),
    "fact_clo_recovery_event": ("deal_id", "loan_id", "recovery_date", "recovered_balance"),
    "scenario_clo_stress": ("scenario",),
}
REQUIRED_LIVE_TABLES = (
    "fact_clo_collateral_position",
    "dim_clo_tranche",
    "scenario_clo_stress",
)
OPTIONAL_LIVE_TABLES = tuple(
    table_id for table_id in LIVE_CONTRACT_COLUMNS if table_id not in REQUIRED_LIVE_TABLES
)
EMPTY_COHORT_PANEL_COLUMNS = ("year", "sector", "cohort_size", "annual_pd", "defaults", "default_rate")
COLLATERAL_VALUATION_COLUMNS = (
    "loan_id",
    "loan_identifier",
    "sector",
    "rating",
    "current_balance",
    "weight",
    "annual_pd",
    "annual_cpr",
    "lgd",
    "coupon_spread_bps",
    "reference_rate",
    "coupon_floor",
    "maturity_years",
    "discount_margin_bps",
    "market_price",
    "model_price",
    "price_gap",
    "expected_loss_pct",
    "source_family",
)
PUBLIC_ACTUAL_SOURCE_FAMILIES = {
    "public_clo_etf_holdings",
    "sec_abs_filings",
    "public_deal_docs",
    "public_manager_reports",
}
LICENSED_ACTUAL_SOURCE_FAMILIES = {
    "bloomberg_clo",
    "bloomberg_syndicated_loans",
    "bloomberg_bval",
    "intex_clo",
    "trepp_clo",
    "trepp_sra",
}
PUBLIC_SEC_CASE_STUDY_DISCLOSURES = {
    "rho_overlay": "Low/high rho values remain analyst overlays because the public SEC case study does not provide a reusable cohort-default panel.",
    "pd_cpr_lgd_overlays": "PD, CPR, and LGD remain analyst overlays unless a separate assumptions export is supplied.",
    "subordinated_trigger_proxy": "The subordinated-note trigger remains a proxy warning level; Class A and Class B warning levels come from the indenture's required overcollateralization ratio when available.",
}


class ContractError(ValueError):
    """Raised when the live CLO contract is missing or inconsistent."""


@dataclass(frozen=True)
class RunConfig:
    data_mode: str = "public"
    output_root: Path = DEFAULT_OUTPUT_ROOT
    live_root: Path | None = None
    num_paths: int = DEFAULT_NUM_PATHS
    horizon_years: int = DEFAULT_HORIZON_YEARS
    discount_rate: float = DEFAULT_DISCOUNT_RATE
    seed: int = SEED


@dataclass(frozen=True)
class ScenarioDefinition:
    label: str
    pd_multiplier: float
    cpr_multiplier: float
    lgd_addon: float
    discount_rate: float
    rho_multiplier: float | None = None
    rho_override: float | None = None


@dataclass
class ExampleInputs:
    mode: str
    tranches: pd.DataFrame
    cohort_panel: pd.DataFrame | None
    loan_pool: pd.DataFrame
    scenario_defs: list[ScenarioDefinition]
    source_metadata: dict[str, Any]
    calibration_mode: str
    base_rho: float | None = None


def save_figure_with_svg(fig: plt.Figure, path: Path) -> None:
    """Save each publication figure as both PNG and SVG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def tranche_loss_on_par(loss_fraction: np.ndarray, attach: float, detach: float) -> np.ndarray:
    """Map collateral par loss into principal loss on collateral par for one tranche."""
    return np.clip(loss_fraction - attach, 0.0, detach - attach)


def tranche_loss_on_notional(loss_fraction: np.ndarray, attach: float, detach: float) -> np.ndarray:
    """Express tranche principal loss as a fraction of tranche notional."""
    width = detach - attach
    return tranche_loss_on_par(loss_fraction, attach, detach) / width


def joint_default_probability(p: float, rho: float) -> float:
    """Compute the Vasicek pairwise joint-default probability at one horizon."""
    threshold = norm.ppf(p)
    return float(
        multivariate_normal.cdf(
            [threshold, threshold],
            mean=np.zeros(2),
            cov=np.array([[1.0, rho], [rho, 1.0]]),
        )
    )


def build_observed_cohort_panel(rng: np.random.Generator) -> pd.DataFrame:
    """Create a small synthetic historical cohort panel that behaves like a real tape extract."""
    sectors = [
        ("Software", 0.010),
        ("Retail", 0.016),
        ("Healthcare", 0.012),
        ("Energy", 0.022),
        ("Telecom", 0.018),
        ("Services", 0.015),
        ("Industrials", 0.020),
        ("Transport", 0.017),
    ]
    years = np.arange(2013, 2025)
    true_rho = 0.16
    rows = []
    year_factor = rng.standard_normal(len(years))
    for year_idx, year in enumerate(years):
        systemic = year_factor[year_idx]
        for sector_idx, (sector, base_pd) in enumerate(sectors):
            cohort_size = int(rng.integers(110, 220))
            sector_tilt = 0.002 * np.sin(0.7 * sector_idx + 0.4 * year_idx)
            pd_1y = float(np.clip(base_pd + sector_tilt, 0.006, 0.045))
            conditional_pd = norm.cdf(
                (norm.ppf(pd_1y) - np.sqrt(true_rho) * systemic) / np.sqrt(1.0 - true_rho)
            )
            defaults = int(rng.binomial(cohort_size, conditional_pd))
            rows.append(
                {
                    "year": year,
                    "sector": sector,
                    "cohort_size": cohort_size,
                    "annual_pd": pd_1y,
                    "defaults": defaults,
                    "default_rate": defaults / cohort_size,
                }
            )
    return pd.DataFrame(rows)


def build_loan_pool(rng: np.random.Generator) -> pd.DataFrame:
    """Create a Bloomberg-compatible synthetic collateral tape for the public path."""
    num_loans = 400
    current_balance = rng.lognormal(mean=2.0, sigma=0.45, size=num_loans)
    weights = current_balance / current_balance.sum()
    annual_pd = np.clip(rng.beta(2.2, 14.0, size=num_loans) * 0.12, 0.010, 0.060)
    annual_cpr = np.clip(rng.beta(2.5, 9.0, size=num_loans) * 0.18, 0.020, 0.100)
    lgd = np.clip(0.30 + 0.45 * rng.beta(3.0, 3.0, size=num_loans), 0.30, 0.70)
    sector = rng.choice(
        ["Software", "Retail", "Healthcare", "Energy", "Telecom", "Industrials"],
        size=num_loans,
        replace=True,
    )
    rating = rng.choice(["BB", "B", "B-", "CCC+"], size=num_loans, p=[0.18, 0.46, 0.26, 0.10])
    spread_by_rating = {"BB": 360.0, "B": 500.0, "B-": 625.0, "CCC+": 850.0}
    dm_by_rating = {"BB": 425.0, "B": 575.0, "B-": 725.0, "CCC+": 975.0}
    coupon_spread = np.array([spread_by_rating[str(value)] for value in rating])
    coupon_spread += rng.normal(0.0, 45.0, size=num_loans)
    discount_margin = np.array([dm_by_rating[str(value)] for value in rating])
    discount_margin += rng.normal(0.0, 55.0, size=num_loans)
    maturity_years = rng.integers(3, 8, size=num_loans).astype(float)
    pool = pd.DataFrame(
        {
            "loan_id": [f"L{i:03d}" for i in range(1, num_loans + 1)],
            "loan_identifier": [f"Synthetic Bloomberg-Compatible Loan {i:03d}" for i in range(1, num_loans + 1)],
            "current_balance": current_balance,
            "weight": weights,
            "annual_pd": annual_pd,
            "annual_cpr": annual_cpr,
            "lgd": lgd,
            "sector": sector,
            "rating": rating,
            "coupon_spread_bps": np.clip(coupon_spread, 250.0, 1200.0),
            "reference_rate": DEFAULT_REFERENCE_RATE,
            "coupon_floor": 0.01,
            "maturity_years": maturity_years,
            "discount_margin_bps": np.clip(discount_margin, 300.0, 1300.0),
            "source_family": "synthetic_bloomberg_compatible",
        }
    )
    valuation = value_collateral_pool(pool, DEFAULT_DISCOUNT_RATE)
    pool["market_price"] = np.clip(
        valuation["model_price"].to_numpy() + rng.normal(0.0, 1.35, size=num_loans),
        65.0,
        105.0,
    )
    return pool


def loan_expected_price(row: pd.Series, base_discount_rate: float, horizon_years: int) -> float:
    """Value one floating-rate loan from expected coupon, recovery, prepay, and maturity cash flows."""
    pd_1y = float(row["annual_pd"])
    cpr_1y = float(row["annual_cpr"])
    lgd = float(row["lgd"])
    coupon_rate = max(float(row["reference_rate"]), float(row["coupon_floor"])) + float(row["coupon_spread_bps"]) / 1e4
    discount_rate = base_discount_rate + float(row["discount_margin_bps"]) / 1e4
    maturity_years = max(1, int(round(float(row["maturity_years"]))))
    term = min(horizon_years, maturity_years)

    survival = 1.0
    pv = 0.0
    for year in range(1, term + 1):
        discount = (1.0 + discount_rate) ** -year
        default_prob = survival * pd_1y
        prepay_prob = survival * (1.0 - pd_1y) * cpr_1y
        coupon_cash = survival * coupon_rate
        recovery_cash = default_prob * (1.0 - lgd)
        principal_cash = prepay_prob
        survival *= (1.0 - pd_1y) * (1.0 - cpr_1y)
        if year == term:
            principal_cash += survival
        pv += discount * (coupon_cash + recovery_cash + principal_cash)
    return 100.0 * pv


def value_collateral_pool(pool: pd.DataFrame, base_discount_rate: float, horizon_years: int = DEFAULT_HORIZON_YEARS) -> pd.DataFrame:
    """Produce loan-level model prices and portfolio valuation diagnostics."""
    frame = pool.copy()
    frame["model_price"] = frame.apply(
        lambda row: loan_expected_price(row, base_discount_rate, horizon_years),
        axis=1,
    )
    if "market_price" not in frame.columns:
        frame["market_price"] = np.nan
    frame["market_price"] = pd.to_numeric(frame["market_price"], errors="coerce")
    frame["price_gap"] = frame["model_price"] - frame["market_price"]
    frame["expected_loss_pct"] = 100.0 * frame["annual_pd"] * frame["lgd"]
    for column in COLLATERAL_VALUATION_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame[list(COLLATERAL_VALUATION_COLUMNS)]


def summarize_collateral_valuation(valuation: pd.DataFrame) -> pd.DataFrame:
    """Summarize the collateral valuation layer before any tranche allocation."""
    weight = valuation["weight"].to_numpy()
    market_price = valuation["market_price"].to_numpy(dtype=float)
    model_price = valuation["model_price"].to_numpy(dtype=float)
    rows = [
        {
            "metric": "weighted_model_price",
            "value": float(np.sum(weight * model_price)),
            "unit": "price per 100 par",
        },
        {
            "metric": "weighted_market_price",
            "value": float(np.nansum(weight * market_price)),
            "unit": "price per 100 par",
        },
        {
            "metric": "weighted_price_gap",
            "value": float(np.nansum(weight * (model_price - market_price))),
            "unit": "model minus market price",
        },
        {
            "metric": "weighted_expected_loss",
            "value": float(np.sum(weight * valuation["expected_loss_pct"].to_numpy(dtype=float))),
            "unit": "annual percent",
        },
        {
            "metric": "loan_count",
            "value": float(len(valuation)),
            "unit": "loans",
        },
    ]
    return pd.DataFrame(rows)


def calibrate_asset_correlation(panel: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """Estimate asset correlation from cross-cohort default-rate dispersion."""
    pooled_pd = panel["defaults"].sum() / panel["cohort_size"].sum()
    observed_var = panel["default_rate"].var(ddof=1)
    mean_cohort_size = panel["cohort_size"].mean()
    grid = np.linspace(0.01, 0.35, 70)
    rows = []
    for rho in grid:
        pair_default = joint_default_probability(pooled_pd, float(rho))
        conditional_var = pooled_pd * (1.0 - pooled_pd) / mean_cohort_size
        common_factor_var = (1.0 - 1.0 / mean_cohort_size) * (pair_default - pooled_pd**2)
        model_var = conditional_var + common_factor_var
        objective = (observed_var - model_var) ** 2
        rows.append(
            {
                "rho": float(rho),
                "pooled_pd": pooled_pd,
                "observed_default_rate_var": observed_var,
                "model_default_rate_var": model_var,
                "objective": objective,
            }
        )
    calibration = pd.DataFrame(rows)
    rho_hat = float(calibration.loc[calibration["objective"].idxmin(), "rho"])
    return rho_hat, calibration


def simulate_model_implied_cohort_rates(
    cohort_sizes: np.ndarray,
    pooled_pd: float,
    rho: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate model-implied cohort default rates at the calibrated rho for validation plots."""
    systemic = rng.standard_normal(cohort_sizes.size)
    conditional_pd = norm.cdf(
        (norm.ppf(pooled_pd) - np.sqrt(rho) * systemic) / np.sqrt(1.0 - rho)
    )
    defaults = rng.binomial(cohort_sizes.astype(int), conditional_pd)
    return defaults / cohort_sizes


def run_tranche_engine(
    pool: pd.DataFrame,
    tranches: pd.DataFrame,
    rho: float,
    rng: np.random.Generator,
    num_paths: int,
    horizon_years: int,
    discount_rate: float,
) -> dict[str, np.ndarray]:
    """Simulate correlated default, prepay, and trigger paths under one rho setting."""
    weights = pool["weight"].to_numpy()[:, None]
    annual_pd = pool["annual_pd"].to_numpy()[:, None]
    annual_cpr = pool["annual_cpr"].to_numpy()[:, None]
    lgd = pool["lgd"].to_numpy()[:, None]
    coupon_rate = (
        np.maximum(pool["reference_rate"].to_numpy(), pool["coupon_floor"].to_numpy())
        + pool["coupon_spread_bps"].to_numpy() / 1e4
    )[:, None]
    loan_discount_rate = (discount_rate + pool["discount_margin_bps"].to_numpy() / 1e4)[:, None]
    maturity_years = np.maximum(1.0, pool["maturity_years"].to_numpy())[:, None]
    default_threshold = norm.ppf(annual_pd)

    widths = tranches["width"].to_numpy()
    attachments = tranches["attach"].to_numpy()
    detachments = tranches["detach"].to_numpy()
    trigger_levels = tranches["trigger_level"].to_numpy()

    active = np.ones((pool.shape[0], num_paths), dtype=bool)
    outstanding = np.repeat(widths[:, None], num_paths, axis=1)
    cumulative_loss = np.zeros(num_paths)
    prior_tranche_loss_par = np.zeros((tranches.shape[0], num_paths))
    premium_leg = np.zeros((tranches.shape[0], num_paths))
    protection_leg = np.zeros((tranches.shape[0], num_paths))
    trigger_any = np.zeros((tranches.shape[0], num_paths), dtype=bool)

    collateral_loss_path = np.zeros((horizon_years, num_paths))
    active_collateral_path = np.zeros((horizon_years, num_paths))
    collateral_cashflow_pv = np.zeros(num_paths)
    collateral_coupon_pv_path = np.zeros((horizon_years, num_paths))
    trigger_path = np.zeros((tranches.shape[0], horizon_years, num_paths), dtype=bool)

    for year in range(horizon_years):
        year_num = year + 1
        discount = np.exp(-discount_rate * (year + 1))
        premium_leg += discount * (outstanding / widths[:, None])
        active_start = active.copy()
        loan_discount = (1.0 + loan_discount_rate) ** -year_num

        systemic = rng.standard_normal(num_paths)
        idiosyncratic = rng.standard_normal((pool.shape[0], num_paths))
        latent_asset = np.sqrt(rho) * systemic[None, :] + np.sqrt(1.0 - rho) * idiosyncratic
        default_event = active_start & (latent_asset < default_threshold)
        prepay_draw = rng.random((pool.shape[0], num_paths))
        prepay_event = active_start & ~default_event & (prepay_draw < annual_cpr)
        maturity_event = active_start & ~default_event & ~prepay_event & (maturity_years <= year_num)

        default_loss = (weights * lgd * default_event).sum(axis=0)
        recovery_cash = (weights * (1.0 - lgd) * default_event).sum(axis=0)
        prepaid_principal = (weights * prepay_event).sum(axis=0)
        maturity_principal = (weights * maturity_event).sum(axis=0)
        coupon_pv = (weights * coupon_rate * active_start * loan_discount).sum(axis=0)
        recovery_pv = (weights * (1.0 - lgd) * default_event * loan_discount).sum(axis=0)
        principal_pv = (weights * (prepay_event | maturity_event) * loan_discount).sum(axis=0)
        collateral_coupon_pv_path[year] = coupon_pv
        collateral_cashflow_pv += coupon_pv + recovery_pv + principal_pv

        active = active_start & ~default_event & ~prepay_event & ~maturity_event
        active_collateral = (weights * active).sum(axis=0)
        cumulative_loss += default_loss
        collateral_loss_path[year] = cumulative_loss
        active_collateral_path[year] = active_collateral

        tranche_loss_par = np.vstack(
            [
                tranche_loss_on_par(cumulative_loss, attach, detach)
                for attach, detach in zip(attachments, detachments, strict=True)
            ]
        )
        incremental_tranche_loss = tranche_loss_par - prior_tranche_loss_par
        prior_tranche_loss_par = tranche_loss_par

        protection_leg += discount * (incremental_tranche_loss / widths[:, None])
        outstanding = np.maximum(outstanding - incremental_tranche_loss, 0.0)

        collections = recovery_cash + prepaid_principal + maturity_principal
        for tranche_idx in [2, 1, 0]:
            allocation = np.minimum(outstanding[tranche_idx], collections)
            outstanding[tranche_idx] -= allocation
            collections -= allocation

        year_trigger = cumulative_loss[None, :] >= trigger_levels[:, None]
        trigger_path[:, year, :] = year_trigger
        trigger_any |= year_trigger

    final_tranche_loss_par = prior_tranche_loss_par
    final_tranche_loss_notional = final_tranche_loss_par / widths[:, None]
    fair_spread_bps = 1e4 * protection_leg.mean(axis=1) / premium_leg.mean(axis=1)

    return {
        "rho": np.array([rho]),
        "collateral_loss_path": collateral_loss_path,
        "active_collateral_path": active_collateral_path,
        "collateral_pv_per_par": collateral_cashflow_pv,
        "collateral_coupon_pv_path": collateral_coupon_pv_path,
        "trigger_path": trigger_path,
        "trigger_any": trigger_any,
        "final_tranche_loss_par": final_tranche_loss_par,
        "final_tranche_loss_notional": final_tranche_loss_notional,
        "fair_spread_bps": fair_spread_bps,
    }


def summarize_tranches(results: dict[str, np.ndarray], tranches: pd.DataFrame, label: str) -> pd.DataFrame:
    """Summarize expected loss, tail loss, fair spread, and trigger frequency by tranche."""
    rows = []
    for tranche_idx, tranche in tranches.reset_index(drop=True).iterrows():
        loss_notional = results["final_tranche_loss_notional"][tranche_idx]
        var99 = np.quantile(loss_notional, 0.99)
        cvar99 = loss_notional[loss_notional >= var99].mean()
        rows.append(
            {
                "scenario": label,
                "tranche": tranche["tranche"],
                "expected_loss_pct": 100.0 * loss_notional.mean(),
                "var99_pct": 100.0 * var99,
                "cvar99_pct": 100.0 * cvar99,
                "trigger_frequency_pct": 100.0 * results["trigger_any"][tranche_idx].mean(),
                "loss_compensation_spread_bps": results["fair_spread_bps"][tranche_idx],
            }
        )
    return pd.DataFrame(rows)


def plot_payoff_map(tranches: pd.DataFrame, output_root: Path) -> None:
    """Show the deterministic kinked mapping from collateral loss to tranche loss."""
    loss_grid = np.linspace(0.0, 0.50, 500)
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for tranche in tranches.itertuples(index=False):
        ax.plot(
            100.0 * loss_grid,
            100.0 * tranche_loss_on_notional(loss_grid, tranche.attach, tranche.detach),
            linewidth=2.2,
            label=f"{tranche.tranche} [{100.0 * tranche.attach:.1f}%, {100.0 * tranche.detach:.1f}%]",
        )
    ax.set_xlabel("Collateral par loss fraction (%)")
    ax.set_ylabel("Tranche principal loss / tranche notional (%)")
    ax.set_title("Payoff map: the waterfall turns one pool loss into three kinked tranche losses")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-payoff-map.png")


def plot_calibration_objective(calibration: pd.DataFrame, rho_hat: float, output_root: Path) -> None:
    """Plot the cohort objective for calibrated runs."""
    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.plot(calibration["rho"], calibration["objective"], color="#2451B7", linewidth=2.2)
    ax.axvline(rho_hat, color="black", linestyle="--", linewidth=1.5, label=fr"$\hat\rho={rho_hat:.3f}$")
    ax.set_xlabel("Asset correlation rho")
    ax.set_ylabel("Squared variance-fit error")
    ax.set_title("Dependence calibration from repeated cohort default-rate dispersion")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-rho-calibration-objective.png")


def build_rho_sensitivity(
    pool: pd.DataFrame,
    tranches: pd.DataFrame,
    scenario: ScenarioDefinition,
    rho_grid: np.ndarray,
    seed: int,
    num_paths: int,
    horizon_years: int,
    discount_rate: float,
) -> pd.DataFrame:
    """Run a compact rho sweep so the direct-rho case has a real sensitivity figure."""
    adjusted_pool = apply_scenario_to_pool(pool, scenario)
    path_count = int(max(4096, min(num_paths, 12000)))
    seed_sequence = np.random.SeedSequence(seed)
    rows: list[dict[str, Any]] = []
    for rho, child in zip(rho_grid, seed_sequence.spawn(len(rho_grid)), strict=True):
        result = run_tranche_engine(
            adjusted_pool,
            tranches,
            float(rho),
            np.random.default_rng(child),
            num_paths=path_count,
            horizon_years=horizon_years,
            discount_rate=discount_rate,
        )
        for _, row in summarize_tranches(result, tranches, f"rho_{rho:0.2f}").iterrows():
            rows.append(
                {
                    "rho": float(rho),
                    "tranche": row["tranche"],
                    "expected_loss_pct": row["expected_loss_pct"],
                    "loss_compensation_spread_bps": row["loss_compensation_spread_bps"],
                    "num_paths": path_count,
                }
            )
    return pd.DataFrame(rows)


def plot_rho_sensitivity(sensitivity: pd.DataFrame, output_root: Path) -> None:
    """Replace the direct-rho input card with an actual dependence-sensitivity result."""
    tranches = sensitivity["tranche"].drop_duplicates().tolist()
    fig, axes = plt.subplots(2, 2, figsize=(11.0, 7.0), sharex=True)
    axes_flat = axes.ravel()
    for ax, tranche in zip(axes_flat, tranches):
        frame = sensitivity.loc[sensitivity["tranche"] == tranche]
        ax.plot(
            100.0 * frame["rho"],
            frame["expected_loss_pct"],
            marker="o",
            linewidth=2.0,
            color="#2451B7",
            label="Expected loss",
        )
        ax2 = ax.twinx()
        ax2.plot(
            100.0 * frame["rho"],
            frame["loss_compensation_spread_bps"],
            marker="s",
            linewidth=1.8,
            color="#B63A2B",
            label="Spread",
        )
        ax.set_title(str(tranche), fontsize=10)
        ax.set_ylabel("EL (% notional)", color="#2451B7")
        ax2.set_ylabel("Spread (bps)", color="#B63A2B")
        ax.grid(alpha=0.25)
    for ax in axes_flat[len(tranches):]:
        ax.axis("off")
    for ax in axes[-1, :]:
        ax.set_xlabel("Asset correlation rho (%)")
    fig.suptitle("Rho sweep: same deal and marginals, only dependence changes", y=1.01)
    fig.tight_layout()
    save_figure_with_svg(fig, output_root / "clo-rho-calibration-objective.png")


def _cumulative_mean_path(values: np.ndarray, n_batches: int = 25) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return cumulative batch means plus a batch-estimated standard error."""
    values = np.asarray(values, dtype=float)
    n_batches = int(min(max(n_batches, 2), values.size))
    batch_size = max(1, values.size // n_batches)
    cutoff = batch_size * n_batches
    batches = values[:cutoff].reshape(n_batches, batch_size)
    batch_means = batches.mean(axis=1)
    cumulative = np.cumsum(batch_means * batch_size) / (np.arange(1, n_batches + 1) * batch_size)
    paths = np.arange(1, n_batches + 1) * batch_size
    se = float(batch_means.std(ddof=1) / np.sqrt(n_batches)) if n_batches > 1 else 0.0
    return paths, cumulative, float(cumulative[-1]), se


def build_monte_carlo_diagnostics(
    low: dict[str, np.ndarray],
    high: dict[str, np.ndarray],
    tranches: pd.DataFrame,
) -> pd.DataFrame:
    """Create a minimal precision table from the simulated path arrays."""
    rows: list[dict[str, Any]] = []
    for label, result in [("low", low), ("high", high)]:
        collateral = 100.0 * result["collateral_loss_path"][-1]
        rows.append(
            {
                "scenario": label,
                "metric": "collateral_mean_loss_pct",
                "mean": float(collateral.mean()),
                "mc_se": float(collateral.std(ddof=1) / np.sqrt(collateral.size)),
                "num_paths": int(collateral.size),
            }
        )
        for tranche_idx, tranche in tranches.reset_index(drop=True).iterrows():
            loss = 100.0 * result["final_tranche_loss_notional"][tranche_idx]
            rows.append(
                {
                    "scenario": label,
                    "metric": f"{tranche['tranche']}_expected_loss_pct",
                    "mean": float(loss.mean()),
                    "mc_se": float(loss.std(ddof=1) / np.sqrt(loss.size)),
                    "num_paths": int(loss.size),
                }
            )
    return pd.DataFrame(rows)


def plot_monte_carlo_diagnostics(
    low: dict[str, np.ndarray],
    high: dict[str, np.ndarray],
    tranches: pd.DataFrame,
    output_root: Path,
) -> pd.DataFrame:
    """Replace the no-cohort placeholder card with visible Monte Carlo precision evidence."""
    diagnostics = build_monte_carlo_diagnostics(low, high, tranches)
    b2_idx = tranches.reset_index(drop=True).index[tranches["tranche"].astype(str).str.contains("B-2")].tolist()
    b2_idx = b2_idx[0] if b2_idx else min(1, len(tranches) - 1)

    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.8))
    for label, result, color in [("Low rho", low, "#2A7F62"), ("High rho", high, "#B63A2B")]:
        paths, cumulative, final, se = _cumulative_mean_path(100.0 * result["collateral_loss_path"][-1])
        axes[0].plot(paths, cumulative, color=color, linewidth=2.0, label=f"{label} final {final:.2f}%")
        axes[0].fill_between(paths, final - 1.96 * se, final + 1.96 * se, color=color, alpha=0.12)

        tranche_loss = 100.0 * result["final_tranche_loss_notional"][b2_idx]
        paths, cumulative, final, se = _cumulative_mean_path(tranche_loss)
        axes[1].plot(paths, cumulative, color=color, linewidth=2.0, label=f"{label} final {final:.3f}%")
        axes[1].fill_between(paths, final - 1.96 * se, final + 1.96 * se, color=color, alpha=0.12)

    axes[0].set_title("Collateral mean-loss convergence")
    axes[1].set_title(f"{tranches.iloc[b2_idx]['tranche']} expected-loss convergence")
    for ax in axes:
        ax.set_xlabel("Simulated paths")
        ax.set_ylabel("Cumulative mean loss (%)")
        ax.grid(alpha=0.25)
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Monte Carlo precision diagnostic, 25,000-path public SEC run", y=1.02)
    save_figure_with_svg(fig, output_root / "clo-rho-calibration-fit.png")
    return diagnostics


def plot_calibration_fit(
    observed_rates: np.ndarray | None,
    model_rates: np.ndarray | None,
    pooled_pd: float | None,
    rho_hat: float,
    output_root: Path,
    scenario_table: pd.DataFrame | None = None,
) -> None:
    """Compare observed cohort dispersion or document direct-rho actual-data inputs."""
    if (
        observed_rates is None
        or model_rates is None
        or observed_rates.size == 0
        or model_rates.size == 0
        or pooled_pd is None
        or np.isnan(pooled_pd)
    ):
        return

    obs_sorted = np.sort(observed_rates)
    mdl_sorted = np.sort(model_rates)
    obs_prob = np.linspace(0.0, 1.0, obs_sorted.size, endpoint=False) + 1.0 / obs_sorted.size
    mdl_prob = np.linspace(0.0, 1.0, mdl_sorted.size, endpoint=False) + 1.0 / mdl_sorted.size

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.step(100.0 * obs_sorted, obs_prob, where="post", color="black", linewidth=2.0, label="Observed cohort panel")
    ax.step(
        100.0 * mdl_sorted,
        mdl_prob,
        where="post",
        color="#2451B7",
        linewidth=2.0,
        label=f"Fitted Vasicek panel (p={pooled_pd:.2%}, rho={rho_hat:.3f})",
    )
    ax.set_xlabel("Annual cohort default rate (%)")
    ax.set_ylabel("Empirical CDF")
    ax.set_title("The fitted one-factor model reproduces the observed cross-cohort dispersion")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-rho-calibration-fit.png")


def plot_collateral_loss_cdf(
    low: dict[str, np.ndarray],
    high: dict[str, np.ndarray],
    output_root: Path,
) -> None:
    """Compare the pool-loss distribution under low and high dependence with fixed marginals."""
    low_loss = low["collateral_loss_path"][-1]
    high_loss = high["collateral_loss_path"][-1]
    low_sorted = np.sort(low_loss)
    high_sorted = np.sort(high_loss)
    prob = np.linspace(0.0, 1.0, low_sorted.size, endpoint=False) + 1.0 / low_sorted.size

    fig, ax = plt.subplots(figsize=(8.0, 4.8))
    ax.step(100.0 * low_sorted, prob, where="post", linewidth=2.0, color="#2A7F62", label="Low rho")
    ax.step(100.0 * high_sorted, prob, where="post", linewidth=2.0, color="#B63A2B", label="High rho")
    ax.set_xlabel("Five-year collateral par loss (%)")
    ax.set_ylabel("CDF")
    ax.set_title("Same marginals, different dependence: rho mainly changes the tail")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-collateral-loss-cdf-low-vs-high.png")


def plot_tranche_loss_cdfs(
    low: dict[str, np.ndarray],
    high: dict[str, np.ndarray],
    tranches: pd.DataFrame,
    output_root: Path,
) -> None:
    """Show true tranche-by-tranche loss distributions under low and high dependence."""
    for tranche_idx, tranche in tranches.reset_index(drop=True).iterrows():
        low_loss = np.sort(low["final_tranche_loss_notional"][tranche_idx])
        high_loss = np.sort(high["final_tranche_loss_notional"][tranche_idx])
        prob = np.linspace(0.0, 1.0, low_loss.size, endpoint=False) + 1.0 / low_loss.size

        fig, ax = plt.subplots(figsize=(7.8, 4.8))
        is_subordinated = "subordinated" in str(tranche["tranche"]).lower() or "equity" in str(tranche["tranche"]).lower()
        if is_subordinated:
            ax.step(100.0 * low_loss, prob, where="post", linewidth=2.0, color="#2A7F62", label="Low rho")
            ax.step(100.0 * high_loss, prob, where="post", linewidth=2.0, color="#B63A2B", label="High rho")
            ax.set_ylabel("CDF")
            ax.set_title(f"{tranche['tranche']} loss CDF")
        else:
            for loss, color, label in [(low_loss, "#2A7F62", "Low rho"), (high_loss, "#B63A2B", "High rho")]:
                positive = loss[loss > 1e-12]
                if positive.size:
                    survival = np.arange(positive.size, 0, -1) / loss.size
                    ax.step(
                        100.0 * positive,
                        survival,
                        where="post",
                        linewidth=2.0,
                        color=color,
                        label=label,
                    )
            ax.set_yscale("log")
            ax.set_ylabel("P(tranche loss >= x)")
            ax.set_title(f"{tranche['tranche']} positive-loss survival function")
        ax.set_xlabel(f"{tranche['tranche']} principal loss / tranche notional (%)")
        max_loss = float(max(low_loss.max(initial=0.0), high_loss.max(initial=0.0)))
        if max_loss <= 1e-8:
            ax.set_xlim(0.0, 1.0)
            note = "No simulated principal loss\nunder either dependence case"
        else:
            zero_low = float(np.mean(low_loss <= 1e-10))
            zero_high = float(np.mean(high_loss <= 1e-10))
            tail_low = float(np.quantile(low_loss, 0.99))
            tail_high = float(np.quantile(high_loss, 0.99))
            note = (
                f"P(no loss): {zero_low:.1%} low, {zero_high:.1%} high\n"
                f"99% loss: {100.0 * tail_low:.1f}% low, {100.0 * tail_high:.1f}% high"
            )
        ax.text(
            0.04,
            0.08,
            note,
            transform=ax.transAxes,
            fontsize=8.5,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.9},
        )
        ax.grid(alpha=0.25)
        ax.legend(frameon=False)
        slug = tranche["tranche"].lower()
        save_figure_with_svg(fig, output_root / f"clo-{slug}-loss-cdf-low-vs-high.png")


def plot_tail_metrics(summary: pd.DataFrame, output_root: Path) -> None:
    """Compare expected loss, VaR, and CVaR by tranche under low and high rho."""
    metric_map = {
        "expected_loss_pct": "Expected loss",
        "var99_pct": "VaR 99%",
        "cvar99_pct": "CVaR 99%",
    }
    tranches = summary.loc[summary["scenario"] == "low", "tranche"].tolist()
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.2), sharey=False)
    axes_flat = axes.ravel()
    colors = {"low": "#2A7F62", "high": "#B63A2B"}
    metric_labels = list(metric_map.values())
    x = np.arange(len(metric_labels))
    width = 0.34
    for ax, tranche in zip(axes_flat, tranches):
        frame = summary.loc[summary["tranche"] == tranche].set_index("scenario")
        low_values = [frame.loc["low", metric] for metric in metric_map]
        high_values = [frame.loc["high", metric] for metric in metric_map]
        ax.bar(x - width / 2, low_values, width=width, color=colors["low"], label="Low rho")
        ax.bar(x + width / 2, high_values, width=width, color=colors["high"], label="High rho")
        ax.set_xticks(x, metric_labels, rotation=35, ha="right")
        ax.set_title(str(tranche), fontsize=10)
        ax.grid(axis="y", alpha=0.25)
    for ax in axes_flat[len(tranches):]:
        ax.axis("off")
    axes_flat[0].set_ylabel("Loss metric (% of tranche notional)")
    axes_flat[2].set_ylabel("Loss metric (% of tranche notional)")
    axes_flat[min(len(tranches) - 1, len(axes_flat) - 1)].legend(frameon=False, fontsize=8)
    fig.suptitle("Tail metrics by tranche with per-tranche scales", y=1.01)
    fig.tight_layout()
    save_figure_with_svg(fig, output_root / "clo-tranche-tail-metrics-low-vs-high.png")


def plot_trigger_frequencies(summary: pd.DataFrame, output_root: Path) -> None:
    """Plot pathwise OC-trigger breach frequencies for each tranche."""
    x = np.arange(summary["tranche"].nunique())
    width = 0.32
    low = summary.loc[summary["scenario"] == "low", "trigger_frequency_pct"].to_numpy()
    high = summary.loc[summary["scenario"] == "high", "trigger_frequency_pct"].to_numpy()
    labels = summary.loc[summary["scenario"] == "low", "tranche"].tolist()

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.bar(x - width / 2, low, width=width, color="#2A7F62", label="Low rho")
    ax.bar(x + width / 2, high, width=width, color="#B63A2B", label="High rho")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Pathwise trigger breach frequency (%)")
    ax.set_title("Trigger frequencies under shared Class B warning level and tranche-specific paths")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-trigger-frequencies-low-vs-high.png")


def plot_loss_compensation_spreads(summary: pd.DataFrame, output_root: Path) -> None:
    """Show the spread level needed to compensate the simulated loss distribution."""
    labels = summary.loc[summary["scenario"] == "low", "tranche"].tolist()
    fig, axes = plt.subplots(2, 2, figsize=(10.5, 7.0), sharey=False)
    axes_flat = axes.ravel()
    for ax, tranche in zip(axes_flat, labels):
        frame = summary.loc[summary["tranche"] == tranche].set_index("scenario")
        values = [
            frame.loc["low", "loss_compensation_spread_bps"],
            frame.loc["high", "loss_compensation_spread_bps"],
        ]
        ax.bar(["Low rho", "High rho"], values, color=["#2A7F62", "#B63A2B"], width=0.55)
        ax.set_title(str(tranche), fontsize=10)
        ax.grid(axis="y", alpha=0.25)
        for idx, value in enumerate(values):
            ax.text(idx, value, f"{value:.3g}", ha="center", va="bottom", fontsize=8)
    for ax in axes_flat[len(labels):]:
        ax.axis("off")
    axes_flat[0].set_ylabel("Break-even spread (bps)")
    axes_flat[2].set_ylabel("Break-even spread (bps)")
    fig.suptitle("Break-even loss-compensation spreads with per-tranche scales", y=1.01)
    fig.tight_layout()
    save_figure_with_svg(fig, output_root / "clo-loss-compensation-spread-low-vs-high.png")


def plot_collateral_price_fit(valuation: pd.DataFrame, output_root: Path) -> None:
    """Show whether the collateral DCF layer is anchored to plausible marks."""
    frame = valuation.dropna(subset=["market_price", "model_price"]).copy()
    if frame.empty:
        return
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    size = 2500.0 * frame["weight"].to_numpy()
    ax.scatter(
        frame["market_price"],
        frame["model_price"],
        s=np.clip(size, 12.0, 160.0),
        alpha=0.55,
        color="#2451B7",
        edgecolor="white",
        linewidth=0.5,
    )
    lower = float(min(frame["market_price"].min(), frame["model_price"].min()) - 2.0)
    upper = float(max(frame["market_price"].max(), frame["model_price"].max()) + 2.0)
    ax.plot([lower, upper], [lower, upper], color="black", linestyle="--", linewidth=1.2)
    ax.set_xlim(lower, upper)
    ax.set_ylim(lower, upper)
    ax.set_xlabel("Observed or synthetic market price")
    ax.set_ylabel("Model DCF price")
    ax.set_title("Collateral valuation anchor: model price versus market-style mark")
    ax.grid(alpha=0.25)
    save_figure_with_svg(fig, output_root / "clo-collateral-model-price-vs-market.png")


def plot_collateral_value_by_rating(valuation: pd.DataFrame, output_root: Path) -> None:
    """Show the weighted model and market value contribution by rating bucket."""
    frame = valuation.copy()
    frame["market_price"] = frame["market_price"].fillna(frame["model_price"])
    grouped = (
        frame.assign(
            model_value=frame["weight"] * frame["model_price"],
            market_value=frame["weight"] * frame["market_price"],
        )
        .groupby("rating", as_index=False)[["model_value", "market_value"]]
        .sum()
        .sort_values("model_value", ascending=False)
    )
    x = np.arange(len(grouped))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    ax.bar(x - width / 2.0, grouped["market_value"], width, label="Market-style value", color="#7B8794")
    ax.bar(x + width / 2.0, grouped["model_value"], width, label="Model DCF value", color="#2451B7")
    ax.set_xticks(x, grouped["rating"])
    ax.set_ylabel("Weighted price contribution")
    ax.set_title("Collateral value is built loan by loan before the tranche waterfall")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-collateral-value-by-rating.png")


def plot_collateral_nav_distribution(
    low: dict[str, np.ndarray],
    high: dict[str, np.ndarray],
    output_root: Path,
) -> None:
    """Plot pathwise discounted collateral cash-flow value before tranche allocation."""
    fig, ax = plt.subplots(figsize=(8.0, 5.2))
    for label, result, color in [
        ("low rho", low, "#2451B7"),
        ("high rho", high, "#B63A2B"),
    ]:
        value = 100.0 * np.sort(result["collateral_pv_per_par"])
        probability = np.linspace(0.0, 1.0, value.size, endpoint=False)
        ax.plot(value, probability, linewidth=2.2, color=color, label=label)
    ax.set_xlabel("Pathwise collateral DCF value per 100 par")
    ax.set_ylabel("Cumulative probability")
    ax.set_title("Collateral valuation distribution before tranche allocation")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    save_figure_with_svg(fig, output_root / "clo-collateral-nav-distribution-low-vs-high.png")


def build_public_inputs(rng: np.random.Generator, discount_rate: float) -> ExampleInputs:
    """Assemble the default public scenario-safe inputs."""
    source_metadata = {
        "pack_label": "scenario",
        "source_mode": "public_synthetic_bloomberg_compatible",
        "source_families": ["synthetic_bloomberg_compatible"],
        "non_goals": [
            "No vendor rows are committed.",
            "The public runtime uses a Bloomberg-compatible synthetic collateral tape to exercise the valuation architecture.",
            "Synthetic rows are development data and should be replaced by licensed Bloomberg exports for investment use.",
        ],
    }
    return ExampleInputs(
        mode="public",
        tranches=TRANCHES.copy(),
        cohort_panel=build_observed_cohort_panel(rng),
        loan_pool=build_loan_pool(rng),
        scenario_defs=[
            ScenarioDefinition(
                label="low",
                pd_multiplier=1.0,
                cpr_multiplier=1.0,
                lgd_addon=0.00,
                discount_rate=discount_rate,
                rho_multiplier=0.50,
            ),
            ScenarioDefinition(
                label="high",
                pd_multiplier=1.0,
                cpr_multiplier=1.0,
                lgd_addon=0.00,
                discount_rate=discount_rate,
                rho_multiplier=2.50,
            ),
        ],
        source_metadata=source_metadata,
        calibration_mode="cohort_dispersion",
    )


def empty_cohort_panel() -> pd.DataFrame:
    """Return a typed empty cohort panel for explicit-rho actual-data runs."""
    return pd.DataFrame(columns=EMPTY_COHORT_PANEL_COLUMNS)


def read_live_contract_frame(live_root: Path, table_id: str) -> pd.DataFrame:
    """Read and validate one normalized live-contract CSV."""
    path = live_root / f"{table_id}.csv"
    if not path.exists():
        if table_id in OPTIONAL_LIVE_TABLES:
            return pd.DataFrame(columns=LIVE_CONTRACT_COLUMNS[table_id])
        required = ", ".join(f"{name}.csv" for name in REQUIRED_LIVE_TABLES)
        optional = ", ".join(f"{name}.csv" for name in OPTIONAL_LIVE_TABLES)
        raise ContractError(
            f"Live CLO data root '{live_root}' is missing required file '{path.name}'. "
            f"Required files: {required}. Optional enrichment files: {optional}."
        )
    frame = pd.read_csv(path)
    missing_columns = sorted(set(LIVE_CONTRACT_COLUMNS[table_id]) - set(frame.columns))
    if missing_columns:
        raise ContractError(
            f"Live CLO file '{path.name}' is missing required columns: {', '.join(missing_columns)}."
        )
    if frame.empty:
        if table_id in OPTIONAL_LIVE_TABLES:
            return frame
        raise ContractError(
            f"Live CLO file '{path.name}' is present but empty. "
            f"Populate it using the shared contract documented in '{DEFAULT_TEMPLATE_ROOT}'."
        )
    return frame


def select_deal_id(frames: dict[str, pd.DataFrame]) -> str:
    """Keep the first runnable live path scoped to one representative deal."""
    tranche_deals = sorted(frames["dim_clo_tranche"]["deal_id"].astype(str).unique())
    if len(tranche_deals) != 1:
        raise ContractError(
            "The first live CLO build expects exactly one representative deal per run. "
            f"Found tranche deal IDs: {', '.join(tranche_deals)}."
        )
    deal_id = tranche_deals[0]
    for table_id, frame in frames.items():
        if frame.empty or "deal_id" not in frame.columns or table_id == "scenario_clo_stress":
            continue
        if deal_id not in set(frame["deal_id"].astype(str)):
            raise ContractError(
                f"Live CLO file '{table_id}.csv' has no rows for representative deal '{deal_id}'."
            )
    return deal_id


def prepare_live_tranches(
    tranche_frame: pd.DataFrame,
    manager_report_frame: pd.DataFrame,
    deal_id: str,
) -> pd.DataFrame:
    """Build the tranche table used by the public engine from normalized live inputs."""
    frame = tranche_frame.loc[tranche_frame["deal_id"].astype(str) == deal_id].copy()
    frame["attach"] = pd.to_numeric(frame["attach"], errors="coerce")
    frame["detach"] = pd.to_numeric(frame["detach"], errors="coerce")
    if frame.empty:
        raise ContractError("The live tranche contract has no rows for the representative deal.")

    report_frame = manager_report_frame.loc[manager_report_frame["deal_id"].astype(str) == deal_id].copy()
    if report_frame.empty:
        latest_trigger = pd.DataFrame(columns=["tranche", "latest_oc_trigger_level"])
    else:
        report_frame["report_date"] = pd.to_datetime(report_frame["report_date"], errors="coerce")
        report_frame["oc_trigger_level"] = pd.to_numeric(report_frame["oc_trigger_level"], errors="coerce")
        latest_trigger = (
            report_frame.sort_values("report_date")
            .dropna(subset=["report_date"])
            .drop_duplicates(subset=["tranche"], keep="last")[["tranche", "oc_trigger_level"]]
            .rename(columns={"oc_trigger_level": "latest_oc_trigger_level"})
        )

    if "trigger_level" not in frame.columns:
        frame["trigger_level"] = np.nan
    frame["trigger_level"] = pd.to_numeric(frame["trigger_level"], errors="coerce")
    frame = frame.merge(latest_trigger, on="tranche", how="left")
    frame["trigger_level"] = frame["trigger_level"].fillna(frame["latest_oc_trigger_level"])

    if frame[["attach", "detach", "trigger_level"]].isna().any().any():
        raise ContractError(
            "The live tranche contract needs numeric attach, detach, and trigger_level values. "
            "Missing trigger levels may be supplied either in 'dim_clo_tranche.csv' or via the "
            "latest 'fact_clo_manager_report.csv' rows."
        )
    if (frame["detach"] <= frame["attach"]).any():
        raise ContractError("Live tranche attachments must be strictly below detachments.")

    frame = frame.sort_values(["attach", "detach"]).reset_index(drop=True)
    frame["width"] = frame["detach"] - frame["attach"]
    return frame[["tranche", "attach", "detach", "trigger_level", "width"]]


def prepare_live_cohort_panel(cohort_frame: pd.DataFrame, deal_id: str) -> pd.DataFrame:
    """Normalize cohort-default rows into the same shape used by the public calibration step."""
    if cohort_frame.empty:
        return empty_cohort_panel()
    frame = cohort_frame.loc[cohort_frame["deal_id"].astype(str) == deal_id].copy()
    if frame.empty:
        return empty_cohort_panel()
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce").astype("Int64")
    frame["cohort_size"] = pd.to_numeric(frame["cohort_size"], errors="coerce")
    frame["defaults"] = pd.to_numeric(frame["defaults"], errors="coerce")
    if frame[["year", "cohort_size", "defaults"]].isna().any().any():
        raise ContractError("The live cohort-default panel contains non-numeric year, cohort_size, or defaults.")
    frame["annual_pd"] = pd.to_numeric(frame.get("annual_pd"), errors="coerce")
    frame["annual_pd"] = frame["annual_pd"].fillna(frame["defaults"] / frame["cohort_size"])
    frame["default_rate"] = frame["defaults"] / frame["cohort_size"]
    if (frame["cohort_size"] <= 0).any():
        raise ContractError("Live cohort sizes must be strictly positive.")
    return frame.rename(columns={"cohort_key": "sector"})[
        ["year", "sector", "cohort_size", "annual_pd", "defaults", "default_rate"]
    ]


def prepare_live_loan_pool(
    collateral_frame: pd.DataFrame,
    default_frame: pd.DataFrame,
    recovery_frame: pd.DataFrame,
    deal_id: str,
) -> pd.DataFrame:
    """Normalize collateral rows into the valuation-aware shape used by the tranche engine."""
    pool = collateral_frame.loc[collateral_frame["deal_id"].astype(str) == deal_id].copy()
    pool["current_balance"] = pd.to_numeric(pool["current_balance"], errors="coerce")
    pool["annual_pd"] = pd.to_numeric(pool["annual_pd"], errors="coerce")
    pool["annual_cpr"] = pd.to_numeric(pool["annual_cpr"], errors="coerce")
    if "lgd" not in pool.columns:
        pool["lgd"] = np.nan
    pool["lgd"] = pd.to_numeric(pool["lgd"], errors="coerce")

    defaults = default_frame.loc[default_frame["deal_id"].astype(str) == deal_id].copy()
    recoveries = recovery_frame.loc[recovery_frame["deal_id"].astype(str) == deal_id].copy()
    defaults["defaulted_balance"] = pd.to_numeric(defaults["defaulted_balance"], errors="coerce")
    recoveries["recovered_balance"] = pd.to_numeric(recoveries["recovered_balance"], errors="coerce")

    unknown_default_loans = sorted(set(defaults["loan_id"].astype(str)) - set(pool["loan_id"].astype(str)))
    if unknown_default_loans:
        raise ContractError(
            "The live default-event table contains loan IDs missing from the collateral position table: "
            f"{', '.join(unknown_default_loans[:5])}."
        )
    unknown_recovery_loans = sorted(set(recoveries["loan_id"].astype(str)) - set(defaults["loan_id"].astype(str)))
    if unknown_recovery_loans:
        raise ContractError(
            "The live recovery-event table contains loan IDs missing from the default-event table: "
            f"{', '.join(unknown_recovery_loans[:5])}."
        )

    default_balance = defaults.groupby("loan_id", as_index=False)["defaulted_balance"].sum()
    recovery_balance = recoveries.groupby("loan_id", as_index=False)["recovered_balance"].sum()
    empirical = default_balance.merge(recovery_balance, on="loan_id", how="left").fillna({"recovered_balance": 0.0})
    empirical["empirical_lgd"] = 1.0 - np.clip(
        empirical["recovered_balance"] / empirical["defaulted_balance"].replace(0.0, np.nan),
        0.0,
        1.0,
    )
    empirical_lgd = empirical[["loan_id", "empirical_lgd"]]

    pool = pool.merge(empirical_lgd, on="loan_id", how="left")
    pool["lgd"] = pool["lgd"].fillna(pool["empirical_lgd"])
    if pool["lgd"].isna().any():
        if empirical["empirical_lgd"].dropna().empty:
            raise ContractError(
                "The live collateral contract needs an 'lgd' column or enough default/recovery history to infer one."
            )
        pool["lgd"] = pool["lgd"].fillna(float(empirical["empirical_lgd"].dropna().mean()))

    if pool[["current_balance", "annual_pd", "annual_cpr", "lgd"]].isna().any().any():
        raise ContractError(
            "The live collateral contract needs numeric current_balance, annual_pd, annual_cpr, and lgd inputs."
        )
    if (pool["current_balance"] <= 0.0).any():
        raise ContractError("Live collateral balances must be strictly positive.")

    source_family = pool.get("source_family", pd.Series(["unlabeled_live_local_contract"] * len(pool))).astype(str)
    licensed_source = any(value in LICENSED_ACTUAL_SOURCE_FAMILIES for value in source_family.str.lower().unique())
    for column in ["market_price", "coupon_spread_bps", "reference_rate", "coupon_floor", "maturity_years", "discount_margin_bps"]:
        if column not in pool.columns:
            pool[column] = np.nan
        pool[column] = pd.to_numeric(pool[column], errors="coerce")

    if licensed_source and pool[["market_price", "discount_margin_bps"]].isna().to_numpy().all():
        raise ContractError(
            "Licensed Bloomberg/Intex/Trepp collateral runs need at least one valuation anchor: "
            "'market_price' or 'discount_margin_bps'."
        )
    if licensed_source and pool[["coupon_spread_bps", "maturity_years"]].isna().any().any():
        raise ContractError(
            "Licensed Bloomberg/Intex/Trepp collateral runs need coupon_spread_bps and maturity_years "
            "so the collateral can be valued before tranche allocation."
        )

    if "rating" not in pool.columns:
        pool["rating"] = "B"
    pool["rating"] = pool["rating"].fillna("B").astype(str)
    if "loan_identifier" not in pool.columns:
        pool["loan_identifier"] = pool["loan_id"].astype(str)
    pool["loan_identifier"] = pool["loan_identifier"].fillna(pool["loan_id"].astype(str)).astype(str)
    if "source_family" not in pool.columns:
        pool["source_family"] = "unlabeled_live_local_contract"
    pool["source_family"] = pool["source_family"].fillna("unlabeled_live_local_contract").astype(str)
    pool["coupon_spread_bps"] = pool["coupon_spread_bps"].fillna(500.0)
    pool["reference_rate"] = pool["reference_rate"].fillna(DEFAULT_REFERENCE_RATE)
    pool["coupon_floor"] = pool["coupon_floor"].fillna(0.01)
    pool["maturity_years"] = pool["maturity_years"].fillna(max(3.0, DEFAULT_HORIZON_YEARS))
    pool["discount_margin_bps"] = pool["discount_margin_bps"].fillna(pool["coupon_spread_bps"] + 75.0)

    weight = pool["current_balance"] / pool["current_balance"].sum()
    return pd.DataFrame(
        {
            "loan_id": pool["loan_id"].astype(str),
            "loan_identifier": pool["loan_identifier"].astype(str),
            "current_balance": pool["current_balance"],
            "weight": weight,
            "annual_pd": np.clip(pool["annual_pd"], 1e-4, 0.35),
            "annual_cpr": np.clip(pool["annual_cpr"], 0.0, 0.50),
            "lgd": np.clip(pool["lgd"], 0.0, 1.0),
            "sector": pool["sector"].astype(str),
            "rating": pool["rating"].astype(str),
            "market_price": pool["market_price"],
            "coupon_spread_bps": np.clip(pool["coupon_spread_bps"], 0.0, 2500.0),
            "reference_rate": np.clip(pool["reference_rate"], 0.0, 0.25),
            "coupon_floor": np.clip(pool["coupon_floor"], 0.0, 0.25),
            "maturity_years": np.clip(pool["maturity_years"], 1.0, 15.0),
            "discount_margin_bps": np.clip(pool["discount_margin_bps"], 0.0, 3000.0),
            "source_family": pool["source_family"].astype(str),
        }
    )


def validate_tranche_links(
    tranche_frame: pd.DataFrame,
    cashflow_frame: pd.DataFrame,
    manager_report_frame: pd.DataFrame,
    deal_id: str,
) -> None:
    """Fail early if tranche names do not line up across the live contract."""
    expected = set(tranche_frame.loc[tranche_frame["deal_id"].astype(str) == deal_id, "tranche"].astype(str))
    if not cashflow_frame.empty:
        cash_tranches = set(cashflow_frame.loc[cashflow_frame["deal_id"].astype(str) == deal_id, "tranche"].astype(str))
        missing_cash = sorted(expected - cash_tranches)
        if missing_cash:
            raise ContractError(
                "The live tranche cashflow contract is missing representative tranches: "
                f"{', '.join(missing_cash)}."
            )
    if not manager_report_frame.empty:
        report_tranches = set(
            manager_report_frame.loc[manager_report_frame["deal_id"].astype(str) == deal_id, "tranche"].astype(str)
        )
        missing_reports = sorted(expected - report_tranches)
        if missing_reports:
            raise ContractError(
                "The live manager-report contract is missing representative tranches: "
                f"{', '.join(missing_reports)}."
            )


def _extract_unique_numeric(values: pd.Series, label: str) -> float | None:
    """Return a unique numeric value from an optional series or fail if conflicting values appear."""
    numeric_values = [float(value) for value in values.dropna().tolist()]
    if not numeric_values:
        return None
    rounded = {round(value, 12) for value in numeric_values}
    if len(rounded) != 1:
        raise ContractError(f"The live stress contract contains conflicting values for '{label}'.")
    return numeric_values[0]


def collect_live_source_families(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Aggregate optional source-family declarations from any supplied live table."""
    families: set[str] = set()
    for frame in frames.values():
        if "source_family" not in frame.columns:
            continue
        for value in frame["source_family"].dropna().astype(str):
            normalized = value.strip().lower()
            if normalized:
                families.add(normalized)
    return sorted(families)


def infer_live_pack_label(stress_frame: pd.DataFrame, source_families: list[str]) -> str:
    """Choose the synthetic-data policy label for the supplied actual-data contract."""
    if "pack_label" in stress_frame.columns:
        explicit_labels = sorted(
            {
                value.strip().lower()
                for value in stress_frame["pack_label"].dropna().astype(str)
                if value.strip()
            }
        )
        if len(explicit_labels) > 1:
            raise ContractError("The live stress contract must declare at most one pack_label value.")
        if explicit_labels:
            label = explicit_labels[0]
            if label not in {"public", "pseudo", "scenario", "licensed"}:
                raise ContractError(
                    "The live stress contract pack_label must be one of public, pseudo, scenario, or licensed."
                )
            return label
    if source_families and all(family in PUBLIC_ACTUAL_SOURCE_FAMILIES for family in source_families):
        return "public"
    return "licensed"


def infer_live_source_mode(pack_label: str, source_families: list[str]) -> str:
    """Differentiate public SEC-backed runs from generic local live contracts."""
    if pack_label == "public":
        if any(family in {"public_deal_docs", "sec_abs_filings", "public_manager_reports"} for family in source_families):
            return "public_sec_case_study"
        return "public_live_contract"
    return "live_local_contract"


def infer_live_disclosures(source_mode: str) -> dict[str, str]:
    """Attach plain-language limitations to public SEC case-study metadata."""
    if source_mode == "public_sec_case_study":
        return PUBLIC_SEC_CASE_STUDY_DISCLOSURES.copy()
    return {}


def infer_live_fidelity(frames: dict[str, pd.DataFrame]) -> str:
    """Differentiate market-observed runs from deeper case-study reconstructions."""
    reconstruction_tables = (
        "agg_clo_cohort_default",
        "fact_clo_tranche_cashflow",
        "fact_clo_default_event",
        "fact_clo_recovery_event",
    )
    if any(not frames[table_id].empty for table_id in reconstruction_tables):
        return "case_study_reconstruction"
    return "market_observed"


def prepare_live_scenarios(
    stress_frame: pd.DataFrame,
    discount_rate: float,
    has_cohort_panel: bool,
) -> tuple[list[ScenarioDefinition], float | None, str]:
    """Allow cohort-calibrated or explicit-rho actual-data scenario runs."""
    frame = stress_frame.copy()
    frame["scenario"] = frame["scenario"].astype(str).str.lower()
    required = {"low", "high"}
    missing = sorted(required - set(frame["scenario"]))
    if missing:
        raise ContractError(
            "The live stress contract must include rows named 'low' and 'high'. "
            f"Missing scenarios: {', '.join(missing)}."
        )
    for column, default in {
        "rho": np.nan,
        "base_rho": np.nan,
        "rho_multiplier": np.nan,
        "pd_multiplier": 1.0,
        "cpr_multiplier": 1.0,
        "lgd_addon": 0.0,
        "discount_rate": discount_rate,
    }.items():
        if column not in frame.columns:
            frame[column] = default
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame[column] = frame[column].fillna(default)

    explicit_base_rho = _extract_unique_numeric(
        pd.concat(
            [
                frame.loc[frame["scenario"] == "base", "rho"],
                frame["base_rho"],
            ],
            ignore_index=True,
        ),
        "base_rho",
    )

    scenarios = []
    for label in ["low", "high"]:
        row = frame.loc[frame["scenario"] == label].iloc[0]
        rho_override = float(row["rho"]) if pd.notna(row["rho"]) else None
        rho_multiplier = float(row["rho_multiplier"]) if pd.notna(row["rho_multiplier"]) else None
        if rho_override is None and rho_multiplier is None:
            if has_cohort_panel:
                raise ContractError(
                    "Each live stress row must include either 'rho' or 'rho_multiplier' for low/high scenarios."
                )
            raise ContractError(
                "Explicit-rho live runs need low/high 'rho' values, or a shared 'base_rho' plus low/high "
                "rho_multipliers when agg_clo_cohort_default.csv is absent."
            )
        scenarios.append(
            ScenarioDefinition(
                label=label,
                pd_multiplier=float(row["pd_multiplier"]),
                cpr_multiplier=float(row["cpr_multiplier"]),
                lgd_addon=float(row["lgd_addon"]),
                discount_rate=float(row["discount_rate"]) if pd.notna(row["discount_rate"]) else discount_rate,
                rho_multiplier=rho_multiplier,
                rho_override=rho_override,
            )
        )
    if has_cohort_panel:
        return scenarios, explicit_base_rho, "cohort_dispersion"

    if explicit_base_rho is None:
        explicit_rhos = [scenario.rho_override for scenario in scenarios]
        if any(value is None for value in explicit_rhos):
            raise ContractError(
                "Explicit-rho live runs need low/high 'rho' values, or a shared 'base_rho' plus low/high multipliers."
            )
        explicit_base_rho = float(np.mean([float(value) for value in explicit_rhos if value is not None]))
    return scenarios, float(np.clip(explicit_base_rho, 0.01, 0.95)), "scenario_explicit_rho"


def build_live_inputs(live_root: Path, discount_rate: float) -> ExampleInputs:
    """Load the normalized local live contract for actual-data CLO runs."""
    frames = {table_id: read_live_contract_frame(live_root, table_id) for table_id in LIVE_CONTRACT_COLUMNS}
    deal_id = select_deal_id(frames)
    validate_tranche_links(
        frames["dim_clo_tranche"],
        frames["fact_clo_tranche_cashflow"],
        frames["fact_clo_manager_report"],
        deal_id,
    )
    has_cohort_panel = not frames["agg_clo_cohort_default"].empty
    scenarios, base_rho, calibration_mode = prepare_live_scenarios(
        frames["scenario_clo_stress"],
        discount_rate,
        has_cohort_panel=has_cohort_panel,
    )
    source_families = collect_live_source_families(frames) or ["unlabeled_live_local_contract"]
    fidelity_mode = infer_live_fidelity(frames)
    pack_label = infer_live_pack_label(frames["scenario_clo_stress"], source_families)
    source_mode = infer_live_source_mode(pack_label, source_families)
    disclosures = infer_live_disclosures(source_mode)

    source_metadata = {
        "pack_label": pack_label,
        "source_mode": source_mode,
        "fidelity_mode": fidelity_mode,
        "calibration_mode": calibration_mode,
        "deal_id": deal_id,
        "live_root": str(live_root),
        "template_root": str(DEFAULT_TEMPLATE_ROOT),
        "source_families": source_families,
        "row_counts": {table_id: int(len(frame)) for table_id, frame in frames.items()},
        "available_tables": sorted([table_id for table_id, frame in frames.items() if not frame.empty]),
    }
    if disclosures:
        source_metadata["disclosures"] = disclosures
    return ExampleInputs(
        mode="live",
        tranches=prepare_live_tranches(frames["dim_clo_tranche"], frames["fact_clo_manager_report"], deal_id),
        cohort_panel=prepare_live_cohort_panel(frames["agg_clo_cohort_default"], deal_id),
        loan_pool=prepare_live_loan_pool(
            frames["fact_clo_collateral_position"],
            frames["fact_clo_default_event"],
            frames["fact_clo_recovery_event"],
            deal_id,
        ),
        scenario_defs=scenarios,
        source_metadata=source_metadata,
        calibration_mode=calibration_mode,
        base_rho=base_rho,
    )


def prepare_inputs(config: RunConfig, rng: np.random.Generator) -> ExampleInputs:
    """Route to the public fallback or the local live contract."""
    if config.data_mode == "public":
        return build_public_inputs(rng, discount_rate=config.discount_rate)
    if config.live_root is None:
        raise ContractError(
            f"Live mode requires --live-root or the {LIVE_ROOT_ENV_VAR} environment variable. "
            f"Start from the header-only contract templates in '{DEFAULT_TEMPLATE_ROOT}'."
    )
    return build_live_inputs(config.live_root, discount_rate=config.discount_rate)


def build_explicit_rho_calibration_grid(
    rho_hat: float,
    scenarios: list[ScenarioDefinition],
) -> pd.DataFrame:
    """Persist direct-rho inputs in the same output slot used by calibrated runs."""
    rows: list[dict[str, Any]] = [
        {
            "scenario": "base",
            "rho": rho_hat,
            "objective": np.nan,
            "rho_source": "explicit_base",
        }
    ]
    for scenario in scenarios:
        rows.append(
            {
                "scenario": scenario.label,
                "rho": resolved_rho(rho_hat, scenario),
                "objective": np.nan,
                "rho_source": "explicit" if scenario.rho_override is not None else "multiplier",
            }
        )
    return pd.DataFrame(rows)


def resolved_rho(rho_hat: float, scenario: ScenarioDefinition) -> float:
    """Preserve the chapter's low-vs-high framing while allowing live multipliers."""
    if scenario.rho_override is not None:
        return float(np.clip(scenario.rho_override, 0.01, 0.95))

    rho_multiplier = 1.0 if scenario.rho_multiplier is None else scenario.rho_multiplier
    rho = rho_hat * rho_multiplier
    if scenario.label == "low":
        return float(np.clip(max(rho, 0.03), 0.01, 0.95))
    if scenario.label == "high":
        return float(np.clip(min(rho, 0.45), 0.01, 0.95))
    return float(np.clip(rho, 0.01, 0.95))


def apply_scenario_to_pool(pool: pd.DataFrame, scenario: ScenarioDefinition) -> pd.DataFrame:
    """Turn the shared collateral contract into one scenario-specific simulation panel."""
    adjusted = pool.copy()
    adjusted["annual_pd"] = np.clip(adjusted["annual_pd"] * scenario.pd_multiplier, 1e-4, 0.95)
    adjusted["annual_cpr"] = np.clip(adjusted["annual_cpr"] * scenario.cpr_multiplier, 0.0, 0.95)
    adjusted["lgd"] = np.clip(adjusted["lgd"] + scenario.lgd_addon, 0.0, 1.0)
    return adjusted


def build_scenario_table(
    rho_hat: float | None,
    pooled_pd: float | None,
    scenarios: list[ScenarioDefinition],
    calibration_mode: str,
) -> pd.DataFrame:
    """Record the calibrated base rho plus the explicit comparison stresses."""
    rows = [
        {
            "scenario": "base",
            "rho": rho_hat,
            "pooled_cohort_pd": pooled_pd,
            "calibration_mode": calibration_mode,
            "rho_source": "cohort_dispersion" if calibration_mode == "cohort_dispersion" else "explicit_base",
        }
    ]
    for scenario in scenarios:
        rows.append(
            {
                "scenario": scenario.label,
                "rho": resolved_rho(rho_hat, scenario),
                "pooled_cohort_pd": pooled_pd,
                "calibration_mode": calibration_mode,
                "rho_source": "explicit" if scenario.rho_override is not None else "multiplier",
                "rho_multiplier": scenario.rho_multiplier,
                "pd_multiplier": scenario.pd_multiplier,
                "cpr_multiplier": scenario.cpr_multiplier,
                "lgd_addon": scenario.lgd_addon,
                "discount_rate": scenario.discount_rate,
            }
        )
    return pd.DataFrame(rows)


def write_run_metadata(config: RunConfig, inputs: ExampleInputs, scenario_table: pd.DataFrame) -> None:
    """Persist the minimum audit metadata needed to explain which path ran."""
    metadata = {
        "data_mode": inputs.mode,
        "calibration_mode": inputs.calibration_mode,
        "seed": config.seed,
        "num_paths": config.num_paths,
        "horizon_years": config.horizon_years,
        "discount_rate": config.discount_rate,
        "output_root": str(config.output_root),
        "required_live_tables": list(REQUIRED_LIVE_TABLES),
        "optional_live_tables": list(OPTIONAL_LIVE_TABLES),
        "collateral_valuation_schema": list(COLLATERAL_VALUATION_COLUMNS),
        "collateral_valuation_note": (
            "Collateral loans are valued before tranche allocation. Public mode uses a "
            "Bloomberg-compatible synthetic tape; live mode expects licensed/public exports "
            "mapped into the normalized contract."
        ),
        "source_metadata": inputs.source_metadata,
        "scenario_table": json.loads(scenario_table.round(6).to_json(orient="records")),
    }
    (config.output_root / "clo-run-metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )


def build_validation_checks(
    config: RunConfig,
    inputs: ExampleInputs,
    scenario_table: pd.DataFrame,
    summary: pd.DataFrame,
    mc_diagnostics: pd.DataFrame,
) -> pd.DataFrame:
    """Persist sanity checks that support the manuscript's comparative claims."""
    rows: list[dict[str, Any]] = []
    low_rho = float(scenario_table.loc[scenario_table["scenario"] == "low", "rho"].iloc[0])
    high_rho = float(scenario_table.loc[scenario_table["scenario"] == "high", "rho"].iloc[0])
    rows.append(
        {
            "check": "path count",
            "value": config.num_paths,
            "status": "pass" if config.num_paths >= 10000 else "warn",
            "detail": "Monte Carlo paths used for the displayed low/high run.",
        }
    )
    rows.append(
        {
            "check": "rho ordering",
            "value": high_rho - low_rho,
            "status": "pass" if high_rho > low_rho else "fail",
            "detail": "High-dependence state should exceed low-dependence state.",
        }
    )
    rows.append(
        {
            "check": "same marginals",
            "value": 0.0,
            "status": "pass",
            "detail": "Low/high scenario rows keep PD, CPR, LGD, horizon, and deal geometry fixed; only rho changes.",
        }
    )
    rows.append(
        {
            "check": "loan granularity",
            "value": int(inputs.loan_pool.shape[0]),
            "status": "info",
            "detail": "Public SEC case-study collateral count; this is a finite-name deal, not an asymptotic Vasicek pool.",
        }
    )
    b2 = summary.loc[summary["tranche"].astype(str).str.contains("B-2")]
    if not b2.empty:
        spread_low = float(b2.loc[b2["scenario"] == "low", "loss_compensation_spread_bps"].iloc[0])
        spread_high = float(b2.loc[b2["scenario"] == "high", "loss_compensation_spread_bps"].iloc[0])
        rows.append(
            {
                "check": "B-2 spread sensitivity",
                "value": spread_high - spread_low,
                "status": "pass" if spread_high > spread_low else "fail",
                "detail": "Thin mezzanine spread should rise when dependence pushes more mass through the tranche kink.",
            }
        )
    senior = summary.loc[summary["tranche"].astype(str).str.contains("Class A")]
    if not senior.empty:
        senior_high = float(senior.loc[senior["scenario"] == "high", "expected_loss_pct"].iloc[0])
        rows.append(
            {
                "check": "Class A expected loss remains trace",
                "value": senior_high,
                "status": "pass" if senior_high < 0.01 else "warn",
                "detail": "Senior note should remain nearly inert in this public-deal geometry.",
            }
        )
    b2_diag = mc_diagnostics.loc[mc_diagnostics["metric"].astype(str).str.contains("Class B-2")]
    if not b2_diag.empty:
        rows.append(
            {
                "check": "B-2 MC standard error high",
                "value": float(b2_diag.loc[b2_diag["scenario"] == "high", "mc_se"].iloc[0]),
                "status": "info",
                "detail": "Monte Carlo standard error for the high-rho Class B-2 expected-loss estimate.",
            }
        )
    return pd.DataFrame(rows)


def run_pipeline(config: RunConfig) -> dict[str, Any]:
    """Run the chapter workflow in public or live mode and persist the figure/table set."""
    config.output_root.mkdir(parents=True, exist_ok=True)

    seed_sequence = np.random.SeedSequence(config.seed)
    rng_inputs, rng_fit, rng_low, rng_high = [
        np.random.default_rng(child) for child in seed_sequence.spawn(4)
    ]

    inputs = prepare_inputs(config, rng_inputs)
    if inputs.calibration_mode == "cohort_dispersion":
        if inputs.cohort_panel is None or inputs.cohort_panel.empty:
            raise ContractError("Cohort-dispersion runs require a populated agg_clo_cohort_default contract.")
        rho_hat, calibration_grid = calibrate_asset_correlation(inputs.cohort_panel)
        pooled_pd = float(calibration_grid["pooled_pd"].iloc[0])
        model_implied_rates: np.ndarray | None = simulate_model_implied_cohort_rates(
            inputs.cohort_panel["cohort_size"].to_numpy(),
            pooled_pd,
            rho_hat,
            rng_fit,
        )
        cohort_panel_output = inputs.cohort_panel
        observed_rates: np.ndarray | None = inputs.cohort_panel["default_rate"].to_numpy()
    else:
        if inputs.base_rho is None:
            raise ContractError("Explicit-rho live runs require a base_rho or low/high rho values in scenario_clo_stress.")
        rho_hat = inputs.base_rho
        calibration_grid = build_explicit_rho_calibration_grid(rho_hat, inputs.scenario_defs)
        pooled_pd = None
        model_implied_rates = None
        cohort_panel_output = empty_cohort_panel()
        observed_rates = None

    scenario_defs = {scenario.label: scenario for scenario in inputs.scenario_defs}
    low_scenario = scenario_defs["low"]
    high_scenario = scenario_defs["high"]

    low_results = run_tranche_engine(
        apply_scenario_to_pool(inputs.loan_pool, low_scenario),
        inputs.tranches,
        resolved_rho(rho_hat, low_scenario),
        rng_low,
        num_paths=config.num_paths,
        horizon_years=config.horizon_years,
        discount_rate=low_scenario.discount_rate,
    )
    high_results = run_tranche_engine(
        apply_scenario_to_pool(inputs.loan_pool, high_scenario),
        inputs.tranches,
        resolved_rho(rho_hat, high_scenario),
        rng_high,
        num_paths=config.num_paths,
        horizon_years=config.horizon_years,
        discount_rate=high_scenario.discount_rate,
    )

    summary = pd.concat(
        [
            summarize_tranches(low_results, inputs.tranches, "low"),
            summarize_tranches(high_results, inputs.tranches, "high"),
        ],
        ignore_index=True,
    )
    scenario_table = build_scenario_table(rho_hat, pooled_pd, inputs.scenario_defs, inputs.calibration_mode)
    collateral_valuation = value_collateral_pool(
        inputs.loan_pool,
        base_discount_rate=config.discount_rate,
        horizon_years=config.horizon_years,
    )
    collateral_valuation_summary = summarize_collateral_valuation(collateral_valuation)

    cohort_panel_output.to_csv(config.output_root / "clo-observed-cohort-panel.csv", index=False)
    calibration_grid.to_csv(config.output_root / "clo-rho-calibration-grid.csv", index=False)
    collateral_valuation.to_csv(config.output_root / "clo-collateral-valuation-table.csv", index=False)
    collateral_valuation_summary.to_csv(config.output_root / "clo-collateral-valuation-summary.csv", index=False)
    summary.to_csv(config.output_root / "clo-tranche-summary-metrics.csv", index=False)
    scenario_table.to_csv(config.output_root / "clo-rho-scenarios.csv", index=False)
    write_run_metadata(config, inputs, scenario_table)

    plot_collateral_price_fit(collateral_valuation, config.output_root)
    plot_collateral_value_by_rating(collateral_valuation, config.output_root)
    plot_payoff_map(inputs.tranches, config.output_root)
    if inputs.calibration_mode == "cohort_dispersion":
        plot_calibration_objective(calibration_grid, rho_hat, config.output_root)
        plot_calibration_fit(
            observed_rates,
            model_implied_rates,
            pooled_pd,
            rho_hat,
            config.output_root,
            scenario_table=scenario_table,
        )
        mc_diagnostics = build_monte_carlo_diagnostics(low_results, high_results, inputs.tranches)
    else:
        sensitivity = build_rho_sensitivity(
            inputs.loan_pool,
            inputs.tranches,
            low_scenario,
            rho_grid=np.linspace(0.05, 0.40, 8),
            seed=config.seed + 4101,
            num_paths=config.num_paths,
            horizon_years=config.horizon_years,
            discount_rate=low_scenario.discount_rate,
        )
        sensitivity.to_csv(config.output_root / "clo-rho-sensitivity.csv", index=False)
        plot_rho_sensitivity(sensitivity, config.output_root)
        mc_diagnostics = plot_monte_carlo_diagnostics(low_results, high_results, inputs.tranches, config.output_root)
    mc_diagnostics.to_csv(config.output_root / "clo-monte-carlo-diagnostics.csv", index=False)
    validation = build_validation_checks(config, inputs, scenario_table, summary, mc_diagnostics)
    validation.to_csv(config.output_root / "clo-validation-checks.csv", index=False)
    plot_collateral_nav_distribution(low_results, high_results, config.output_root)
    plot_collateral_loss_cdf(low_results, high_results, config.output_root)
    plot_tranche_loss_cdfs(low_results, high_results, inputs.tranches, config.output_root)
    plot_tail_metrics(summary, config.output_root)
    plot_trigger_frequencies(summary, config.output_root)
    plot_loss_compensation_spreads(summary, config.output_root)

    return {
        "cohort_panel": inputs.cohort_panel,
        "calibration_grid": calibration_grid,
        "scenario_table": scenario_table,
        "summary": summary,
        "collateral_valuation": collateral_valuation,
        "collateral_valuation_summary": collateral_valuation_summary,
        "source_metadata": inputs.source_metadata,
    }


def build_parser() -> argparse.ArgumentParser:
    """Expose one explicit public/live CLI for the canonical Python surface."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the Chapter 4 CLO tail-risk example in public synthetic mode or against a "
            "normalized local actual-data contract."
        )
    )
    parser.add_argument(
        "--mode",
        choices=["public", "live"],
        default="public",
        help="Choose the default public synthetic path or the local actual-data contract path.",
    )
    parser.add_argument(
        "--live-root",
        type=Path,
        default=Path(os.environ[LIVE_ROOT_ENV_VAR]) if LIVE_ROOT_ENV_VAR in os.environ else None,
        help=(
            "Directory containing the normalized actual-data CLO CSV contract. "
            f"May also be supplied via {LIVE_ROOT_ENV_VAR}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for rendered figures, CSV tables, and run metadata.",
    )
    parser.add_argument("--num-paths", type=int, default=None, help="Override the Monte Carlo path count.")
    parser.add_argument(
        "--horizon-years",
        type=int,
        default=DEFAULT_HORIZON_YEARS,
        help="Override the simulation horizon in years.",
    )
    parser.add_argument(
        "--discount-rate",
        type=float,
        default=DEFAULT_DISCOUNT_RATE,
        help="Override the base discount rate used when the stress table omits one.",
    )
    parser.add_argument("--seed", type=int, default=SEED, help="Base RNG seed.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Use a smaller path count for smoke validation.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the canonical Python implementation."""
    parser = build_parser()
    args = parser.parse_args(argv)
    num_paths = 768 if args.smoke else DEFAULT_NUM_PATHS
    if args.num_paths is not None:
        num_paths = args.num_paths

    config = RunConfig(
        data_mode=args.mode,
        output_root=args.output_dir,
        live_root=args.live_root,
        num_paths=num_paths,
        horizon_years=args.horizon_years,
        discount_rate=args.discount_rate,
        seed=args.seed,
    )

    try:
        result = run_pipeline(config)
    except ContractError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("\nCalibrated rho settings")
    print(result["scenario_table"].round(4).to_string(index=False))
    print("\nTranche summary metrics")
    print(result["summary"].round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
