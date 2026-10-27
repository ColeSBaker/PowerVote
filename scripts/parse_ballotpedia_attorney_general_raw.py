#!/usr/bin/env python3
"""Build Ballotpedia 2026 attorney general rollups from raw HTML snapshots."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ballotpedia_rollup.scrape_shared import soup_from_html
from ballotpedia_rollup.io import write_csv, write_json, write_rows
from ballotpedia_rollup.kalshi import build_kalshi_contest_indexes
from ballotpedia_rollup.parser import build_rollup_context
from ballotpedia_rollup.states import STATE_ABBR

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "raw" / "ballotpedia_attorney_general_raw"

DEFAULT_OUTPUT_DIR = REPO_ROOT / "apps" / "web" / "data"

_AG_CONTEST_INDEX = DEFAULT_OUTPUT_DIR / "kalshi-us-attorney-general-contest-index.json"


def _load_kalshi_indexes(index_path: Path) -> dict[str, Any]:
    """Load a Kalshi contest index JSON and build lookup indexes.

    Normalizes attorney general field names to match the House/Senate schema
    that ``build_kalshi_contest_indexes`` expects.
    """
    if not index_path.exists():
        return {}
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    raw_contests: list[dict[str, Any]] = payload.get("contests") or []
    normalized: list[dict[str, Any]] = []
    for c in raw_contests:
        nc = dict(c)
        nc.setdefault("seat", nc.get("seat_id"))
        nc.setdefault("party_lane", nc.get("party"))
        nc.setdefault("market_role", nc.get("market_type"))
        if "market_tickers" not in nc:
            nc["market_tickers"] = [
                str(m.get("marketTicker") or "")
                for m in nc.get("markets") or []
                if str(m.get("marketTicker") or "").strip()
            ]
        normalized.append(nc)
    return build_kalshi_contest_indexes(normalized)

_PARTY_DOT_MAP = {"rep": "R", "dem": "D"}

# Notes added due to missing national table data -- removed after overlay resolves them.
_INCUMBENT_NOTES_RESOLVED_BY_NATIONAL = frozenset({
    "incumbent_unknown_fallback",
    "incumbent_party_unknown_fallback",
    "source_missing_incumbent_marker",
    "source_missing_incumbent_field",
})


def parse_ag_national_table(national_html: str) -> dict[str, dict]:
    """Parse the Ballotpedia national attorney general table.

    Returns a dict keyed by state abbreviation:
        {state_abbr: {incumbent_name, incumbent_party, term_limited}}
    Covers states that have a 2026 AG race listed.
    """
    soup = soup_from_html(national_html)
    result: dict[str, dict] = {}
    for table in soup.find_all("table"):
        dots = table.find_all(class_=lambda c: c and "party-dot" in c)
        if not dots:
            continue
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            dot = row.find(class_=lambda c: c and "party-dot" in c)
            if not dot or len(cells) < 3:
                continue
            party_slug = next(
                (cls[len("party--"):] for cls in dot.get("class", []) if cls.startswith("party--")),
                "",
            )
            state_name = cells[0].get_text(strip=True)
            abbr = STATE_ABBR.get(state_name)
            if not abbr:
                continue
            result[abbr] = {
                "incumbent_name": cells[1].get_text(strip=True),
                "incumbent_party": _PARTY_DOT_MAP.get(party_slug, party_slug.upper() or None),
                "term_limited": cells[2].get_text(strip=True).upper() == "Y",
            }
        if result:
            break
    return result


def _build_stub_row(state_abbr: str, entry: dict, template: dict) -> dict:
    """Build a minimal general row for a state that had no scraped 2026 data."""
    stub = {k: None for k in template}
    stub.update({
        "seat": f"{state_abbr}-AG",
        "state": state_abbr,
        "district": "STATEWIDE",
        "incumbent_name": entry["incumbent_name"],
        "incumbent_party": entry["incumbent_party"],
        "incumbent_status": "retiring" if entry["term_limited"] else "running",
        "term_limited": entry["term_limited"],
        "fec_incumbent_name": "",
        "fec_incumbent_party": "",
        "fec_incumbent_conflict": "",
        "general_status": "upcoming",
        "primary_status_d": "unknown",
        "primary_status_r": "unknown",
        "primary_reason_d": "",
        "primary_reason_r": "",
        "other_general_candidates": [],
        "historical_general_vote_totals": {},
        "historical_primary_vote_totals": {},
        "historical_primary_status": {},
        "historical_primary_reason": {},
        "dccc_target": False,
        "nrcc_target": False,
        "dscc_target": False,
        "nrsc_target": False,
        "source_file": "National.txt",
        "parser_notes": ["national_table_stub"],
    })
    return stub


def overlay_national_ag_data(
    general_rows: list[dict],
    national_data: dict[str, dict],
) -> None:
    """Overlay national table data onto general rows in-place.

    For state_attorney_general:
      - Overwrites incumbent_name, incumbent_party, incumbent_status on all rows.
      - Injects stub rows for states present in the national table but absent from parsed output.
    All rows get the term_limited field added.
    """
    existing_states = {row["state"] for row in general_rows}

    for row in general_rows:
        entry = national_data.get(row.get("state", ""))
        row["term_limited"] = entry["term_limited"] if entry else None

        if entry:
            row["incumbent_name"] = entry["incumbent_name"]
            row["incumbent_party"] = entry["incumbent_party"]
            row["incumbent_status"] = "retiring" if entry["term_limited"] else "running"
            row["parser_notes"] = [
                n for n in (row.get("parser_notes") or [])
                if n not in _INCUMBENT_NOTES_RESOLVED_BY_NATIONAL
            ]

    template = general_rows[0] if general_rows else {}
    for state_abbr, entry in sorted(national_data.items()):
        if state_abbr in existing_states:
            continue
        general_rows.append(_build_stub_row(state_abbr, entry, template))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Ballotpedia 2026 attorney general rollups from raw HTML snapshots")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    return parser


def _emit_outputs(output_dir: Path, *, prefix: str, context, output_format: str) -> None:
    write_json(output_dir / f"{prefix}-general-election-rollup.json", context.general_rows)
    write_json(output_dir / f"{prefix}-primary-election-rollup.json", context.primary_rows)
    write_json(output_dir / f"{prefix}-runoff-election-rollup.json", context.runoff_rows)
    write_csv(output_dir / f"{prefix}-general-election-rollup.csv", context.general_rows)
    write_csv(output_dir / f"{prefix}-primary-election-rollup.csv", context.primary_rows)
    write_csv(output_dir / f"{prefix}-runoff-election-rollup.csv", context.runoff_rows)
    write_rows(output_dir / f"{prefix}-general-election-rollup.jsonl", context.general_rows, output_format)
    write_rows(output_dir / f"{prefix}-primary-election-rollup.jsonl", context.primary_rows, output_format)
    write_rows(output_dir / f"{prefix}-runoff-election-rollup.jsonl", context.runoff_rows, output_format)


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    national_path = args.input_dir / "National.txt"
    national_data: dict[str, dict] = {}
    if national_path.exists():
        national_html = national_path.read_text(encoding="utf-8")
        national_data = parse_ag_national_table(national_html)

    ag_kalshi_indexes = _load_kalshi_indexes(_AG_CONTEST_INDEX)

    ag_context = build_rollup_context(
        args.input_dir,
        office="state_attorney_general",
        kalshi_indexes=ag_kalshi_indexes,
    )

    if national_data:
        overlay_national_ag_data(ag_context.general_rows, national_data)

    _emit_outputs(args.output_dir, prefix="ballotpedia-attorney-general", context=ag_context, output_format=args.format)

    print("Attorney General rollups")
    print(f"  National table entries: {len(national_data)}")
    print(f"  Input files discovered: {sum(ag_context.archetype_counts.values())}")
    print(f"  Archetype counts: {ag_context.archetype_counts}")
    print(f"  General rows emitted: {len(ag_context.general_rows)}")
    print(f"  Primary rows emitted: {len(ag_context.primary_rows)}")
    print(f"  Runoff rows emitted: {len(ag_context.runoff_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())
