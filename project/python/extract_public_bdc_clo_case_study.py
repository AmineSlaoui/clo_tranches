# (c) 2027, Michael Robbins
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

import pandas as pd
from bs4 import BeautifulSoup

from CLO import DEFAULT_DISCOUNT_RATE


RAW_COLLATERAL_NAME = "public_collateral_export.csv"
RAW_STRESS_NAME = "public_stress_export.csv"
RAW_TRANCHE_NAME = "public_tranche_export.csv"
METADATA_NAME = "public_case_study_metadata.json"
USER_AGENT = "Book2Chapter4Extractor/1.0 (contact: research@example.com)"
SEC_ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data"
SEC_REFERER = "https://www.sec.gov/"
SEC_SUBMISSIONS_ROOT = "https://data.sec.gov/submissions"
SEC_MIN_REQUEST_INTERVAL_SECONDS = 0.25
PUBLIC_CASE_STUDY_DISCLOSURES = {
    "rho_overlay": "Low/high rho values remain analyst overlays because the public SEC case study does not provide a reusable cohort-default panel.",
    "pd_cpr_lgd_overlays": "PD, CPR, and LGD remain analyst overlays unless an assumptions export is supplied.",
    "subordinated_trigger_proxy": "The subordinated-note trigger remains a proxy warning level; Class A and Class B warning levels are derived from the indenture's required overcollateralization ratio when available.",
}

PUBLIC_CASE_STUDIES = {
    "palmer_square_bdc_clo_1": {
        "deal_id": "PALMER_SQUARE_BDC_CLO_1",
        "manager_name": "Palmer Square Capital BDC Inc.",
        "cik": "1794776",
        "note_form": "8-K",
        "note_accession": "0001213900-24-046305",
        "note_filing_date": "2024-05-23",
        "note_document_patterns": [r"ea\d+.*8k.*palmersquare.*\.htm$"],
        "indenture_form": "8-K",
        "indenture_accession": "0001213900-24-046305",
        "indenture_filing_date": "2024-05-23",
        "indenture_document_patterns": [r"ex10-2", r"indenture"],
        "collateral_form": "10-K",
        "collateral_accession": "0001193125-26-073362",
        "collateral_filing_date": "2026-03-16",
        "collateral_document_patterns": [r"psbd-20251231\.htm$"],
        "as_of_date": "2025-12-31",
        "collateral_footnote_marker": "8",
        "capital_stack_order": [
            "Subordinated Notes",
            "Class B-2 Notes",
            "Class B-1 Notes",
            "Class A Notes",
        ],
    }
}


@dataclass(frozen=True)
class ResolvedEdgarDocument:
    label: str
    retrieval_method: str
    source: str
    filing_url: str | None
    document_url: str
    cik: str | None
    accession: str | None
    filing_date: str | None
    filing_form: str | None
    document_name: str | None


class SecEdgarClient:
    def __init__(self, user_agent: str, cache_dir: Path | None = None) -> None:
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self._last_request_time = 0.0
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        parsed = urlsplit(url)
        suffix = Path(parsed.path).suffix or ".cache"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}{suffix}"

    def fetch_bytes(self, url: str) -> bytes:
        cache_path = self._cache_path(url)
        if cache_path is not None and cache_path.exists():
            return cache_path.read_bytes()

        elapsed = time.monotonic() - self._last_request_time
        if elapsed < SEC_MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(SEC_MIN_REQUEST_INTERVAL_SECONDS - elapsed)

        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": SEC_REFERER,
            },
        )
        with urlopen(request) as response:
            payload = response.read()
        self._last_request_time = time.monotonic()

        if cache_path is not None:
            cache_path.write_bytes(payload)
        return payload

    def fetch_text(self, url: str) -> str:
        return self.fetch_bytes(url).decode("utf-8", errors="ignore")

    def fetch_json(self, url: str) -> dict[str, Any]:
        return json.loads(self.fetch_text(url))


def _normalize_accession(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    if len(digits) != 18:
        clean = str(value).strip()
        return clean or None
    return f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"


def _accession_nodash(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)


def _normalized_cik(value: str | int) -> str:
    return f"{int(str(value).strip()):010d}"


def _archive_directory_url(cik: str, accession: str) -> str:
    return f"{SEC_ARCHIVES_ROOT}/{int(cik)}/{_accession_nodash(accession)}/"


def _read_text(source: str, client: SecEdgarClient | None = None) -> str:
    if source.lower().startswith(("http://", "https://")):
        active_client = client or SecEdgarClient(USER_AGENT)
        return active_client.fetch_text(source)
    return Path(source).read_text(encoding="utf-8")


def _collapse_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _html_to_text(html_text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _collapse_space(unescape(text))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "loan"


def _strip_footnote_markers(value: str) -> str:
    cleaned = re.sub(r"\([^)]*\)", "", value)
    cleaned = re.sub(r"\s+\d{1,2}(?:\s+\d{1,2})*$", "", cleaned)
    return _collapse_space(cleaned)


def _normalize_lookup_key(value: str) -> str:
    clean = _strip_footnote_markers(str(value))
    return _collapse_space(re.sub(r"[^A-Za-z0-9]+", " ", clean).lower())


def _maybe_ratio(value: float) -> float:
    return value / 100.0 if value > 2.0 else value


def _find_column(columns: list[str], patterns: tuple[str, ...]) -> str:
    normalized = {column.lower(): column for column in columns}
    for pattern in patterns:
        for lower, original in normalized.items():
            if pattern in lower:
                return original
    raise ValueError(f"Could not find a column matching {patterns}. Available columns: {columns}")


def _find_matching_columns(columns: list[str], patterns: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for column in columns:
        lowered = column.lower()
        if any(pattern in lowered for pattern in patterns):
            matches.append(column)
    return matches


def _find_best_numeric_column(frame: pd.DataFrame, patterns: tuple[str, ...]) -> str:
    candidates = _find_matching_columns(list(frame.columns), patterns)
    if not candidates:
        raise ValueError(f"Could not find a numeric column matching {patterns}. Available columns: {list(frame.columns)}")
    best_column = candidates[0]
    best_score = -1
    for column in candidates:
        parsed = frame[column].astype(str).str.replace(",", "", regex=False).str.extract(r"([\d.]+)")[0]
        score = int(parsed.notna().sum())
        if score > best_score:
            best_column = column
            best_score = score
    return best_column


def _extract_required_oc_ratio(text: str, labels: tuple[str, ...]) -> float | None:
    for label in labels:
        pattern = rf"{label}[^0-9]{{0,120}}(\d{{2,3}}(?:\.\d+)?)%"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _maybe_ratio(float(match.group(1)))
    return None


def _amount_to_millions(amount_text: str, unit: str | None) -> float:
    amount = float(amount_text.replace(",", ""))
    normalized_unit = (unit or "").strip().lower()
    if normalized_unit == "billion":
        return amount * 1000.0
    if normalized_unit == "million":
        return amount
    if amount > 10000.0:
        return amount / 1_000_000.0
    return amount


def _parse_note_amounts(note_text: str) -> dict[str, dict[str, float]]:
    tranche_patterns: dict[str, list[tuple[str, str | None]]] = {
        "Class A Notes": [
            (
                r"\$([\d.,]+)\s*(million|billion)?(?: of)?(?: [A-Z-]+)?\s*Class A Notes.*?(?:Term )?SOFR plus\s+([\d.]+)%",
                "percent",
            ),
            (
                r"\$([\d.,]+)\s*(million|billion)?(?: of)?(?: [A-Z-]+)?\s*Class A Notes.*?(\d+(?:\.\d+)?)\s*basis points",
                "bps",
            ),
            (
                r"Class A Notes.*?\$([\d.,]+)\s*(million|billion)?.*?(?:Term )?SOFR plus\s+([\d.]+)%",
                "percent",
            ),
            (
                r"Class A Notes.*?\$([\d.,]+)\s*(million|billion)?.*?(\d+(?:\.\d+)?)\s*basis points",
                "bps",
            ),
        ],
        "Class B-1 Notes": [
            (
                r"\$([\d.,]+)\s*(million|billion)?(?: of)?(?: [A-Z-]+)?\s*Class B-1 Notes.*?(?:Term )?SOFR plus\s+([\d.]+)%",
                "percent",
            ),
            (
                r"\$([\d.,]+)\s*(million|billion)?(?: of)?(?: [A-Z-]+)?\s*Class B-1 Notes.*?(\d+(?:\.\d+)?)\s*basis points",
                "bps",
            ),
            (
                r"Class B-1 Notes.*?\$([\d.,]+)\s*(million|billion)?.*?(?:Term )?SOFR plus\s+([\d.]+)%",
                "percent",
            ),
            (
                r"Class B-1 Notes.*?\$([\d.,]+)\s*(million|billion)?.*?(\d+(?:\.\d+)?)\s*basis points",
                "bps",
            ),
        ],
        "Class B-2 Notes": [
            (
                r"\$([\d.,]+)\s*(million|billion)?(?: of)?(?: [A-Z-]+)?\s*Class B-2 Notes.*?(?:fixed rate of|interest at)\s+([\d.]+)%",
                "percent",
            ),
            (
                r"\$([\d.,]+)\s*(million|billion)?(?: of)?(?: [A-Z-]+)?\s*Class B-2 Notes.*?(\d+(?:\.\d+)?)\s*basis points",
                "bps",
            ),
            (
                r"Class B-2 Notes.*?\$([\d.,]+)\s*(million|billion)?.*?(?:fixed rate of|interest at)\s+([\d.]+)%",
                "percent",
            ),
            (
                r"Class B-2 Notes.*?\$([\d.,]+)\s*(million|billion)?.*?(\d+(?:\.\d+)?)\s*basis points",
                "bps",
            ),
        ],
        "Subordinated Notes": [
            (r"\$([\d.,]+)\s*(million|billion)?(?: of)?\s*Subordinated Notes", None),
            (r"Subordinated Notes.*?\$([\d.,]+)\s*(million|billion)?", None),
        ],
    }
    rows: dict[str, dict[str, float]] = {}
    for tranche, patterns in tranche_patterns.items():
        for pattern, coupon_mode in patterns:
            match = re.search(pattern, note_text, flags=re.IGNORECASE | re.DOTALL)
            if match is None:
                continue
            amount_mm = _amount_to_millions(match.group(1), match.group(2) if len(match.groups()) >= 2 else None)
            coupon_bps = 0.0
            if coupon_mode == "percent" and len(match.groups()) >= 3:
                coupon_bps = float(match.group(3)) * 100.0
            elif coupon_mode == "bps" and len(match.groups()) >= 3:
                coupon_bps = float(match.group(3))
            rows[tranche] = {"amount_mm": amount_mm, "coupon_bps": coupon_bps}
            break
        if tranche not in rows:
            raise ValueError(f"Could not parse {tranche} from the public case-study note filing.")
    return rows


def _derive_trigger_levels(
    stack_rows: list[dict[str, float]],
    indenture_text: str,
    senior_trigger_level: float | None,
    mezz_trigger_level: float | None,
    equity_trigger_level: float | None,
) -> tuple[dict[str, float], dict[str, str]]:
    protected_debt_fraction = {row["tranche"]: 1.0 - row["attach"] for row in stack_rows}
    senior_oc_ratio = _extract_required_oc_ratio(
        indenture_text,
        ("Class A Overcollateralization Ratio", "Class A Overcollateralization Test"),
    )
    mezz_oc_ratio = _extract_required_oc_ratio(
        indenture_text,
        (
            "Class B Overcollateralization Ratio",
            "Class B Overcollateralization Test",
            "Class A/B Overcollateralization Ratio",
            "Class A/B Overcollateralization Test",
        ),
    )
    generic_oc_ratio = _extract_required_oc_ratio(
        indenture_text,
        ("Required Overcollateralization Ratio",),
    )
    if senior_oc_ratio is None:
        senior_oc_ratio = generic_oc_ratio
    if mezz_oc_ratio is None:
        mezz_oc_ratio = generic_oc_ratio

    triggers: dict[str, float] = {}
    trigger_sources: dict[str, str] = {}

    if senior_trigger_level is not None:
        triggers["Class A Notes"] = float(senior_trigger_level)
        trigger_sources["Class A Notes"] = "explicit_override"
    elif senior_oc_ratio is not None:
        triggers["Class A Notes"] = max(0.0, 1.0 - senior_oc_ratio * protected_debt_fraction["Class A Notes"])
        trigger_sources["Class A Notes"] = f"parsed_required_oc_ratio_{senior_oc_ratio:.6f}"
    else:
        senior_row = next(row for row in stack_rows if row["tranche"] == "Class A Notes")
        triggers["Class A Notes"] = senior_row["attach"] + 0.5 * (senior_row["detach"] - senior_row["attach"])
        trigger_sources["Class A Notes"] = "fallback_midpoint_proxy"

    mezz_classes = ("Class B-1 Notes", "Class B-2 Notes")
    if mezz_trigger_level is not None:
        mezz_level = float(mezz_trigger_level)
        mezz_source = "explicit_override"
    elif mezz_oc_ratio is not None:
        mezz_level = max(0.0, 1.0 - mezz_oc_ratio * protected_debt_fraction["Class B-1 Notes"])
        mezz_source = f"parsed_required_oc_ratio_{mezz_oc_ratio:.6f}"
    else:
        mezz_row = next(row for row in stack_rows if row["tranche"] == "Class B-1 Notes")
        mezz_level = mezz_row["attach"] + 0.5 * (mezz_row["detach"] - mezz_row["attach"])
        mezz_source = "fallback_midpoint_proxy"
    for tranche in mezz_classes:
        triggers[tranche] = mezz_level
        trigger_sources[tranche] = mezz_source

    if equity_trigger_level is not None:
        triggers["Subordinated Notes"] = float(equity_trigger_level)
        trigger_sources["Subordinated Notes"] = "explicit_override"
    else:
        # Public filings do not expose a standalone subordinated-note warning test in this route.
        equity_row = next(row for row in stack_rows if row["tranche"] == "Subordinated Notes")
        triggers["Subordinated Notes"] = 0.5 * min(mezz_level, equity_row["detach"])
        trigger_sources["Subordinated Notes"] = "proxy_half_of_next_senior_warning_level"

    return triggers, trigger_sources


def _build_tranche_frame(args: argparse.Namespace, note_text: str, indenture_text: str) -> tuple[pd.DataFrame, dict[str, str]]:
    case_study = PUBLIC_CASE_STUDIES[args.case_study]
    parsed_notes = _parse_note_amounts(note_text)
    total_capital = sum(parsed_notes[tranche]["amount_mm"] for tranche in case_study["capital_stack_order"])
    cumulative = 0.0
    stack_rows: list[dict[str, float]] = []
    for tranche in case_study["capital_stack_order"]:
        amount = parsed_notes[tranche]["amount_mm"]
        attach = cumulative / total_capital
        cumulative += amount
        detach = cumulative / total_capital
        stack_rows.append(
            {
                "tranche": tranche,
                "attach": attach,
                "detach": detach,
                "coupon_bps": parsed_notes[tranche]["coupon_bps"],
            }
        )

    triggers, trigger_sources = _derive_trigger_levels(
        stack_rows,
        indenture_text=indenture_text,
        senior_trigger_level=args.senior_trigger_level,
        mezz_trigger_level=args.mezz_trigger_level,
        equity_trigger_level=args.equity_trigger_level,
    )
    tranche_frame = pd.DataFrame(stack_rows)
    tranche_frame["deal_id"] = case_study["deal_id"]
    tranche_frame["manager_name"] = case_study["manager_name"]
    tranche_frame["trigger_level"] = tranche_frame["tranche"].map(triggers)
    tranche_frame["source_family"] = "public_deal_docs"
    return tranche_frame[
        ["deal_id", "tranche", "attach", "detach", "trigger_level", "coupon_bps", "manager_name", "source_family"]
    ], trigger_sources


def _extract_submission_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    compact = payload
    if isinstance(payload.get("filings"), dict) and isinstance(payload["filings"].get("recent"), dict):
        compact = payload["filings"]["recent"]
    accessions = compact.get("accessionNumber") or []
    rows: list[dict[str, Any]] = []
    for idx in range(len(accessions)):
        row: dict[str, Any] = {}
        for key, values in compact.items():
            if isinstance(values, list) and idx < len(values):
                row[key] = values[idx]
        if row:
            rows.append(row)
    return rows


def _load_submission_rows(client: SecEdgarClient, cik: str) -> list[dict[str, Any]]:
    payload = client.fetch_json(f"{SEC_SUBMISSIONS_ROOT}/CIK{_normalized_cik(cik)}.json")
    rows = _extract_submission_rows(payload)
    for extra_file in payload.get("filings", {}).get("files", []):
        name = extra_file.get("name")
        if not name:
            continue
        extra_payload = client.fetch_json(urljoin(f"{SEC_SUBMISSIONS_ROOT}/", name))
        rows.extend(_extract_submission_rows(extra_payload))

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        accession = _normalize_accession(str(row.get("accessionNumber", "")).strip())
        if accession:
            deduped[accession] = row
    return list(deduped.values())


def _resolve_filing_entry(
    rows: list[dict[str, Any]],
    accession: str | None,
    filing_form: str | None,
    filing_date: str | None,
) -> dict[str, Any]:
    normalized_accession = _normalize_accession(accession)
    candidates = rows
    if filing_form is not None:
        candidates = [row for row in candidates if str(row.get("form", "")).upper() == filing_form.upper()]
    if normalized_accession is not None:
        candidates = [
            row
            for row in candidates
            if _normalize_accession(str(row.get("accessionNumber", "")).strip()) == normalized_accession
        ]
    if filing_date is not None:
        dated = [row for row in candidates if str(row.get("filingDate", "")).strip() == filing_date]
        if dated:
            candidates = dated
    if not candidates:
        raise ValueError(
            "Could not resolve the requested SEC filing from the submissions history. "
            f"Form={filing_form!r}, accession={normalized_accession!r}, filing_date={filing_date!r}."
        )
    candidates.sort(key=lambda row: (str(row.get("filingDate", "")), str(row.get("accessionNumber", ""))), reverse=True)
    return candidates[0]


def _resolve_index_items(client: SecEdgarClient, cik: str, accession: str) -> list[dict[str, Any]]:
    directory_url = _archive_directory_url(cik, accession)
    index_payload = client.fetch_json(urljoin(directory_url, "index.json"))
    return list(index_payload.get("directory", {}).get("item", []))


def _select_document_name(
    items: list[dict[str, Any]],
    document_patterns: list[str],
    fallback_name: str | None,
) -> str:
    item_names = [str(item.get("name", "")) for item in items if item.get("name")]
    for pattern in document_patterns:
        regex = re.compile(pattern, flags=re.IGNORECASE)
        for name in item_names:
            if regex.search(name):
                return name
    if fallback_name and fallback_name in item_names:
        return fallback_name
    html_names = [name for name in item_names if name.lower().endswith((".htm", ".html", ".txt"))]
    if fallback_name and fallback_name in html_names:
        return fallback_name
    if html_names:
        return html_names[0]
    raise ValueError("Could not resolve a filing document from the EDGAR filing index.")


def _resolve_case_document(
    args: argparse.Namespace,
    client: SecEdgarClient,
    role: str,
) -> ResolvedEdgarDocument:
    case_study = PUBLIC_CASE_STUDIES[args.case_study]
    direct_source = getattr(args, f"{role}_source", None)
    if direct_source:
        return ResolvedEdgarDocument(
            label=role,
            retrieval_method="direct_override",
            source=str(direct_source),
            filing_url=str(direct_source),
            document_url=str(direct_source),
            cik=case_study.get("cik"),
            accession=_normalize_accession(getattr(args, f"{role}_accession", None)),
            filing_date=None,
            filing_form=None,
            document_name=Path(str(direct_source)).name,
        )

    accession = _normalize_accession(getattr(args, f"{role}_accession", None) or case_study.get(f"{role}_accession"))
    filing_form = case_study.get(f"{role}_form")
    filing_date = case_study.get(f"{role}_filing_date")
    cik = _normalized_cik(case_study["cik"])
    rows = _load_submission_rows(client, cik)
    entry = _resolve_filing_entry(rows, accession=accession, filing_form=filing_form, filing_date=filing_date)
    resolved_accession = _normalize_accession(str(entry.get("accessionNumber", "")).strip())
    if resolved_accession is None:
        raise ValueError(f"The resolved SEC filing for '{role}' did not expose an accession number.")
    index_items = _resolve_index_items(client, cik, resolved_accession)
    primary_document = str(entry.get("primaryDocument", "")).strip() or None
    document_patterns = list(case_study.get(f"{role}_document_patterns", []) or [])
    document_name = _select_document_name(index_items, document_patterns, fallback_name=primary_document)
    directory_url = _archive_directory_url(cik, resolved_accession)
    filing_url = urljoin(directory_url, primary_document or document_name)
    document_url = urljoin(directory_url, document_name)
    return ResolvedEdgarDocument(
        label=role,
        retrieval_method="edgar_direct",
        source=document_url,
        filing_url=filing_url,
        document_url=document_url,
        cik=cik,
        accession=resolved_accession,
        filing_date=str(entry.get("filingDate", "")).strip() or None,
        filing_form=str(entry.get("form", "")).strip() or None,
        document_name=document_name,
    )


def _expand_row_to_width(row: list[str], width: int) -> list[str]:
    return row + ([""] * max(0, width - len(row)))


def _table_to_matrix(table: Any) -> list[list[str]]:
    pending: dict[int, tuple[str, int]] = {}
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row: list[str] = []
        column_index = 0

        while column_index in pending:
            text, remaining = pending[column_index]
            row.append(text)
            if remaining <= 1:
                del pending[column_index]
            else:
                pending[column_index] = (text, remaining - 1)
            column_index += 1

        for cell in cells:
            while column_index in pending:
                text, remaining = pending[column_index]
                row.append(text)
                if remaining <= 1:
                    del pending[column_index]
                else:
                    pending[column_index] = (text, remaining - 1)
                column_index += 1

            text = _collapse_space(cell.get_text(" ", strip=True))
            rowspan = int(str(cell.get("rowspan", "1")) or "1")
            colspan = int(str(cell.get("colspan", "1")) or "1")
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    pending[column_index] = (text, rowspan - 1)
                column_index += 1

        while column_index in pending:
            text, remaining = pending[column_index]
            row.append(text)
            if remaining <= 1:
                del pending[column_index]
            else:
                pending[column_index] = (text, remaining - 1)
            column_index += 1

        rows.append(row)

    if not rows:
        return []
    width = max(len(row) for row in rows)
    return [_expand_row_to_width([_collapse_space(cell) for cell in row], width) for row in rows]


def _make_unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique_headers: list[str] = []
    for idx, header in enumerate(headers, start=1):
        base = header or f"column_{idx}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        unique_headers.append(base if count == 1 else f"{base}_{count}")
    return unique_headers


def _flatten_header_rows(rows: list[list[str]], header_depth: int) -> list[str]:
    width = max(len(row) for row in rows[:header_depth])
    flattened: list[str] = []
    for col_idx in range(width):
        pieces: list[str] = []
        for row in rows[:header_depth]:
            cell = row[col_idx] if col_idx < len(row) else ""
            if cell and cell.lower() not in {piece.lower() for piece in pieces}:
                pieces.append(cell)
        flattened.append(" ".join(pieces))
    return _make_unique_headers(flattened)


def _header_score(headers: list[str]) -> int:
    lowered = [header.lower() for header in headers]
    score = 0
    if any("portfolio company" in header for header in lowered):
        score += 4
    if any("industry" in header for header in lowered):
        score += 2
    if any("principal" in header or re.search(r"\bpar\b", header) for header in lowered):
        score += 4
    if any("maturity" in header for header in lowered):
        score += 1
    if any("interest rate" in header for header in lowered):
        score += 1
    return score


def _frame_from_matrix(matrix: list[list[str]]) -> tuple[pd.DataFrame, int]:
    rows = [row for row in matrix if any(cell for cell in row)]
    if len(rows) < 2:
        return pd.DataFrame(), 0
    best_depth = 1
    best_headers = _flatten_header_rows(rows, 1)
    best_score = _header_score(best_headers)
    for header_depth in range(2, min(3, len(rows) - 1) + 1):
        headers = _flatten_header_rows(rows, header_depth)
        score = _header_score(headers)
        if score > best_score:
            best_depth = header_depth
            best_headers = headers
            best_score = score
    data_rows = [_expand_row_to_width(row, len(best_headers))[: len(best_headers)] for row in rows[best_depth:]]
    data_rows = [row for row in data_rows if any(cell for cell in row)]
    return pd.DataFrame(data_rows, columns=best_headers), best_score


def _find_schedule_table(html_text: str) -> pd.DataFrame:
    parser = "xml" if html_text.lstrip().startswith("<?xml") else "lxml"
    soup = BeautifulSoup(html_text, parser)
    schedule_anchor = soup.find(string=re.compile(r"schedule\s+of\s+investments", re.IGNORECASE))
    candidate_tables: list[Any] = []
    if schedule_anchor is not None:
        anchor = schedule_anchor.parent if getattr(schedule_anchor, "parent", None) is not None else soup
        candidate_tables.extend(anchor.find_all_next("table", limit=6))
    candidate_tables.extend(soup.find_all("table"))

    best_frame = pd.DataFrame()
    best_score = -1
    seen_ids: set[int] = set()
    for idx, table in enumerate(candidate_tables):
        table_id = id(table)
        if table_id in seen_ids:
            continue
        seen_ids.add(table_id)
        matrix = _table_to_matrix(table)
        if not matrix:
            continue
        frame, score = _frame_from_matrix(matrix)
        if frame.empty:
            continue
        if schedule_anchor is not None and idx < 6:
            score += 2
        if score > best_score:
            best_frame = frame
            best_score = score

    if best_frame.empty or best_score < 6:
        raise ValueError("Could not locate a Schedule of Investments table in the public collateral filing.")
    return best_frame


def _merge_collateral_assumptions(collateral: pd.DataFrame, assumptions_export: Path | None) -> pd.DataFrame:
    if assumptions_export is None:
        return collateral
    assumptions = pd.read_csv(assumptions_export)
    assumptions.columns = [str(column).strip() for column in assumptions.columns]
    lowered = {column.lower(): column for column in assumptions.columns}

    overlay = assumptions.copy()
    if "loan_id" in lowered:
        overlay["loan_lookup_key"] = overlay[lowered["loan_id"]].astype(str).map(_normalize_lookup_key)
    elif "loan_identifier" in lowered:
        overlay["loan_lookup_key"] = overlay[lowered["loan_identifier"]].astype(str).map(_normalize_lookup_key)
    elif "portfolio_company" in lowered:
        overlay["loan_lookup_key"] = overlay[lowered["portfolio_company"]].astype(str).map(_normalize_lookup_key)
    else:
        overlay["loan_lookup_key"] = pd.NA

    if "sector" in lowered:
        overlay["sector_lookup_key"] = overlay[lowered["sector"]].astype(str).map(_normalize_lookup_key)
    elif "industry" in lowered:
        overlay["sector_lookup_key"] = overlay[lowered["industry"]].astype(str).map(_normalize_lookup_key)
    else:
        overlay["sector_lookup_key"] = pd.NA

    for column in ["annual_pd", "annual_cpr", "lgd", "sector"]:
        source_column = lowered.get(column)
        if source_column is None:
            continue
        loan_mapping = (
            overlay.dropna(subset=["loan_lookup_key"])
            .drop_duplicates(subset=["loan_lookup_key"], keep="last")
            .set_index("loan_lookup_key")[source_column]
        )
        sector_mapping = (
            overlay.dropna(subset=["sector_lookup_key"])
            .drop_duplicates(subset=["sector_lookup_key"], keep="last")
            .set_index("sector_lookup_key")[source_column]
        )
        collateral[column] = collateral[column].where(collateral[column].notna(), collateral["loan_lookup_key"].map(loan_mapping))
        collateral[column] = collateral[column].where(
            collateral[column].notna(),
            collateral["sector_lookup_key"].map(sector_mapping),
        )
    return collateral


def _row_matches_footnote_marker(value: str, marker: str) -> bool:
    normalized = _collapse_space(value)
    explicit_patterns = [
        rf"\(\s*{re.escape(marker)}\s*\)",
        rf"\[\s*{re.escape(marker)}\s*\]",
        rf"(?<!\d){re.escape(marker)}(?!\d)",
    ]
    return any(re.search(pattern, normalized) for pattern in explicit_patterns)


def _build_collateral_frame(args: argparse.Namespace, collateral_html: str) -> pd.DataFrame:
    case_study = PUBLIC_CASE_STUDIES[args.case_study]
    schedule = _find_schedule_table(collateral_html)
    columns = list(schedule.columns)
    portfolio_column = _find_column(columns, ("portfolio company",))
    industry_column = _find_column(columns, ("industry",))
    principal_column = _find_best_numeric_column(schedule, ("principal", "par"))

    frame = schedule[[portfolio_column, industry_column, principal_column]].copy()
    marker = str(args.collateral_footnote_marker or case_study["collateral_footnote_marker"]).strip()
    frame = frame.loc[frame[portfolio_column].astype(str).map(lambda value: _row_matches_footnote_marker(value, marker))].copy()
    if frame.empty:
        raise ValueError(
            "The public collateral filing did not expose any pledged rows for the requested footnote marker. "
            f"Marker: ({marker})."
        )

    frame["loan_identifier"] = frame[portfolio_column].astype(str).map(_strip_footnote_markers)
    frame["sector"] = frame[industry_column].astype(str).map(_collapse_space)
    frame["current_balance"] = (
        frame[principal_column].astype(str).str.replace(",", "", regex=False).str.extract(r"([\d.]+)")[0].astype(float)
    )
    frame = frame.dropna(subset=["current_balance"]).copy()
    if frame.empty:
        raise ValueError("The public collateral filing did not expose numeric principal balances for pledged rows.")

    frame["loan_id"] = frame["loan_identifier"].map(_slugify)
    duplicate_counts: dict[str, int] = {}
    resolved_ids: list[str] = []
    for loan_id in frame["loan_id"]:
        duplicate_counts[loan_id] = duplicate_counts.get(loan_id, 0) + 1
        suffix = duplicate_counts[loan_id]
        resolved_ids.append(f"{loan_id}_{suffix}" if suffix > 1 else loan_id)
    frame["loan_id"] = resolved_ids

    frame["loan_lookup_key"] = frame["loan_identifier"].map(_normalize_lookup_key)
    frame["sector_lookup_key"] = frame["sector"].map(_normalize_lookup_key)
    frame["annual_pd"] = pd.NA
    frame["annual_cpr"] = pd.NA
    frame["lgd"] = pd.NA
    frame = _merge_collateral_assumptions(frame, args.assumptions_export)

    # The public filing exposes pledged rows, not loan-level risk estimates, so these stay analyst overlays by default.
    frame["annual_pd"] = pd.to_numeric(frame["annual_pd"], errors="coerce").fillna(args.default_annual_pd)
    frame["annual_cpr"] = pd.to_numeric(frame["annual_cpr"], errors="coerce").fillna(args.default_annual_cpr)
    frame["lgd"] = pd.to_numeric(frame["lgd"], errors="coerce").fillna(args.default_lgd)
    frame["deal_id"] = case_study["deal_id"]
    frame["as_of_date"] = args.as_of_date
    frame["source_family"] = "public_deal_docs"
    return frame[
        [
            "deal_id",
            "as_of_date",
            "loan_id",
            "sector",
            "current_balance",
            "annual_pd",
            "annual_cpr",
            "lgd",
            "loan_identifier",
            "source_family",
        ]
    ].copy()


def _build_stress_frame(args: argparse.Namespace) -> pd.DataFrame | None:
    if args.low_rho is None or args.high_rho is None:
        return None
    # The public SEC case-study route does not estimate rho from filing history; low/high values are explicit overlays.
    base_rho = args.base_rho if args.base_rho is not None else 0.5 * (args.low_rho + args.high_rho)
    return pd.DataFrame(
        [
            {
                "scenario": "low",
                "rho": args.low_rho,
                "base_rho": base_rho,
                "pd_multiplier": args.low_pd_multiplier,
                "cpr_multiplier": args.low_cpr_multiplier,
                "lgd_addon": args.low_lgd_addon,
                "discount_rate": args.discount_rate,
                "source_family": "public_deal_docs",
                "pack_label": "public",
            },
            {
                "scenario": "high",
                "rho": args.high_rho,
                "base_rho": base_rho,
                "pd_multiplier": args.high_pd_multiplier,
                "cpr_multiplier": args.high_cpr_multiplier,
                "lgd_addon": args.high_lgd_addon,
                "discount_rate": args.discount_rate,
                "source_family": "public_deal_docs",
                "pack_label": "public",
            },
        ]
    )


def extract_public_case_study(args: argparse.Namespace) -> dict[str, Path]:
    case_study = PUBLIC_CASE_STUDIES[args.case_study]
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    client = SecEdgarClient(
        user_agent=getattr(args, "sec_user_agent", USER_AGENT),
        cache_dir=getattr(args, "cache_dir", None),
    )
    resolved_documents = {role: _resolve_case_document(args, client, role) for role in ("note", "indenture", "collateral")}

    note_html = _read_text(resolved_documents["note"].document_url, client)
    indenture_html = _read_text(resolved_documents["indenture"].document_url, client)
    collateral_html = _read_text(resolved_documents["collateral"].document_url, client)
    note_text = _html_to_text(note_html)
    indenture_text = _html_to_text(indenture_html)

    tranche_frame, trigger_sources = _build_tranche_frame(args, note_text, indenture_text)
    collateral_frame = _build_collateral_frame(args, collateral_html)
    stress_frame = _build_stress_frame(args)

    written = {
        "tranche_export": output_dir / RAW_TRANCHE_NAME,
        "collateral_export": output_dir / RAW_COLLATERAL_NAME,
    }
    tranche_frame.to_csv(written["tranche_export"], index=False)
    collateral_frame.to_csv(written["collateral_export"], index=False)

    if stress_frame is not None:
        written["stress_export"] = output_dir / RAW_STRESS_NAME
        stress_frame.to_csv(written["stress_export"], index=False)

    metadata_path = output_dir / METADATA_NAME
    metadata = {
        "source_mode": "public_sec_case_study",
        "retrieval_method": "edgar_direct"
        if all(document.retrieval_method == "edgar_direct" for document in resolved_documents.values())
        else "mixed_override",
        "case_study": args.case_study,
        "deal_id": case_study["deal_id"],
        "cik": _normalized_cik(case_study["cik"]),
        "as_of_date": args.as_of_date,
        "sources": {
            "note_source": resolved_documents["note"].document_url,
            "indenture_source": resolved_documents["indenture"].document_url,
            "collateral_source": resolved_documents["collateral"].document_url,
            "source_urls": [document.document_url for document in resolved_documents.values()],
        },
        "resolved_documents": {
            role: {
                "retrieval_method": document.retrieval_method,
                "source": document.source,
                "filing_url": document.filing_url,
                "document_url": document.document_url,
                "cik": document.cik,
                "accession": document.accession,
                "filing_date": document.filing_date,
                "filing_form": document.filing_form,
                "document_name": document.document_name,
            }
            for role, document in resolved_documents.items()
        },
        "assumptions": {
            "assumptions_export": str(args.assumptions_export.resolve()) if args.assumptions_export else None,
            "default_annual_pd": args.default_annual_pd,
            "default_annual_cpr": args.default_annual_cpr,
            "default_lgd": args.default_lgd,
        },
        "disclosures": PUBLIC_CASE_STUDY_DISCLOSURES,
        "requested_accessions": {
            "note": _normalize_accession(getattr(args, "note_accession", None) or case_study.get("note_accession")),
            "indenture": _normalize_accession(
                getattr(args, "indenture_accession", None) or case_study.get("indenture_accession")
            ),
            "collateral": _normalize_accession(
                getattr(args, "collateral_accession", None) or case_study.get("collateral_accession")
            ),
        },
        "trigger_sources": trigger_sources,
        "collateral_footnote_marker": args.collateral_footnote_marker,
        "written_files": {name: str(path.resolve()) for name, path in written.items()},
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    written["metadata"] = metadata_path
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a public BDC-sponsored CLO case-study raw package for Chapter 4."
    )
    parser.add_argument(
        "--case-study",
        choices=sorted(PUBLIC_CASE_STUDIES),
        default="palmer_square_bdc_clo_1",
        help="Pinned public CLO case study to extract.",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory that will receive the raw public CSV exports.")
    parser.add_argument("--note-source", help="Optional override for the public note / 8-K source HTML or URL.")
    parser.add_argument("--indenture-source", help="Optional override for the public indenture source HTML or URL.")
    parser.add_argument("--collateral-source", help="Optional override for the public collateral source HTML or URL.")
    parser.add_argument("--note-accession", help="Optional accession override for the public note filing.")
    parser.add_argument("--indenture-accession", help="Optional accession override for the public indenture exhibit filing.")
    parser.add_argument("--collateral-accession", help="Optional accession override for the public collateral filing.")
    parser.add_argument("--sec-user-agent", default=USER_AGENT, help="Declared SEC user agent for EDGAR requests.")
    parser.add_argument("--cache-dir", type=Path, help="Optional cache directory for SEC JSON and HTML responses.")
    parser.add_argument("--assumptions-export", type=Path, help="Optional CSV overlay keyed by loan or sector with annual_pd, annual_cpr, and lgd.")
    parser.add_argument("--as-of-date", help="Override the public case-study as-of date.")
    parser.add_argument(
        "--collateral-footnote-marker",
        help="Footnote marker used in the public schedule to flag loans pledged into the CLO.",
    )
    parser.add_argument("--senior-trigger-level", type=float, help="Optional direct trigger level for the senior class.")
    parser.add_argument("--mezz-trigger-level", type=float, help="Optional direct trigger level for the mezzanine classes.")
    parser.add_argument("--equity-trigger-level", type=float, help="Optional direct trigger level for the subordinated notes.")
    parser.add_argument(
        "--default-annual-pd",
        type=float,
        default=0.02,
        help="Judgmental annual PD fallback used when the public case study does not provide a loan-level overlay.",
    )
    parser.add_argument(
        "--default-annual-cpr",
        type=float,
        default=0.04,
        help="Judgmental annual CPR fallback used when the public case study does not provide a loan-level overlay.",
    )
    parser.add_argument(
        "--default-lgd",
        type=float,
        default=0.60,
        help="Judgmental LGD fallback used when the public case study does not provide a loan-level overlay.",
    )
    parser.add_argument("--base-rho", type=float, help="Optional base rho for the generated public stress file.")
    parser.add_argument("--low-rho", type=float, help="Optional low-scenario explicit rho.")
    parser.add_argument("--high-rho", type=float, help="Optional high-scenario explicit rho.")
    parser.add_argument("--low-pd-multiplier", type=float, default=1.0)
    parser.add_argument("--high-pd-multiplier", type=float, default=1.0)
    parser.add_argument("--low-cpr-multiplier", type=float, default=1.0)
    parser.add_argument("--high-cpr-multiplier", type=float, default=1.0)
    parser.add_argument("--low-lgd-addon", type=float, default=0.0)
    parser.add_argument("--high-lgd-addon", type=float, default=0.0)
    parser.add_argument("--discount-rate", type=float, default=DEFAULT_DISCOUNT_RATE)
    return parser


def _apply_case_study_defaults(args: argparse.Namespace) -> argparse.Namespace:
    case_study = PUBLIC_CASE_STUDIES[args.case_study]
    if args.as_of_date is None:
        args.as_of_date = case_study["as_of_date"]
    if args.collateral_footnote_marker is None:
        args.collateral_footnote_marker = case_study["collateral_footnote_marker"]
    return args


def main() -> int:
    args = _apply_case_study_defaults(build_parser().parse_args())
    written = extract_public_case_study(args)
    print(f"Extracted public Chapter 4 case study to {Path(args.output_dir).resolve()}")
    print(f"Tranche export: {written['tranche_export']}")
    print(f"Collateral export: {written['collateral_export']}")
    if "stress_export" in written:
        print(f"Stress export: {written['stress_export']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
