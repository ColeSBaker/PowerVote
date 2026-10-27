"""Senate FEC linkage utilities with deterministic + controlled fallback joins."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEC_CANDIDATE_SUMMARY_FILE = REPO_ROOT / "test_data" / "candidates" / "candidate_summary_2026.csv"
DEFAULT_SENATE_CANDIDATE_ROLLUP = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-senate-2026.csv"
DEFAULT_OUTPUT_ENRICHED = REPO_ROOT / "apps" / "web" / "data" / "candidate-rollup-senate-2026-fec.csv"
DEFAULT_OUTPUT_AUDIT = REPO_ROOT / "apps" / "web" / "data" / "senate-fec-linkage-audit.csv"
DEFAULT_OUTPUT_CONFLICTS = REPO_ROOT / "apps" / "web" / "data" / "senate-fec-linkage-conflicts.csv"


def _normalize_name(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if "," in text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if len(parts) >= 2:
            text = " ".join(parts[1:] + [parts[0]])
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_party(value: str | None) -> str:
    text = str(value or "").strip().upper()
    if text in {"DEM", "DFL", "D"}:
        return "D"
    if text in {"REP", "R"}:
        return "R"
    if text in {"IND", "NPA"}:
        return "IND"
    if text == "LIB":
        return "L"
    if text in {"GRE", "GRN"}:
        return "G"
    return "OTH"


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out: dict[str, Any] = {}
            for key, value in row.items():
                if isinstance(value, (dict, list)):
                    out[key] = json.dumps(value, sort_keys=True)
                else:
                    out[key] = value
            writer.writerow(out)


def _senate_fec_rows(fec_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in fec_rows:
        if str(row.get("Cand_Office") or "").strip().upper() != "S":
            continue
        state = str(row.get("Cand_Office_St") or "").strip().upper()
        if not state:
            continue
        output.append(row)
    return output


def link_senate_candidates_with_fec(
    senate_candidate_rows: list[dict[str, str]],
    fec_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    senate_fec = _senate_fec_rows(fec_rows)
    by_state_party_name: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    by_state_name: dict[tuple[str, str], list[dict[str, str]]] = {}

    for row in senate_fec:
        state = str(row.get("Cand_Office_St") or "").strip().upper()
        party = _normalize_party(row.get("Cand_Party_Affiliation"))
        name = _normalize_name(row.get("Cand_Name"))
        if not state or not name:
            continue
        by_state_party_name.setdefault((state, party, name), []).append(row)
        by_state_name.setdefault((state, name), []).append(row)

    enriched: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for row in senate_candidate_rows:
        out = dict(row)
        seat = str(row.get("2026 Seat") or "").strip().upper()
        state = seat.split("-", 1)[0] if "-" in seat else ""
        name = _normalize_name(row.get("BallotpediaName"))
        party = _normalize_party(row.get("Party"))
        exact = by_state_party_name.get((state, party, name)) or []
        fallback = by_state_name.get((state, name)) or []

        match_strategy = "none"
        selected: dict[str, str] | None = None
        conflict_reason = ""

        if len(exact) == 1:
            selected = exact[0]
            match_strategy = "state_party_name_exact"
        elif len(exact) > 1:
            selected = sorted(exact, key=lambda item: str(item.get("Coverage_End_Date") or ""), reverse=True)[0]
            match_strategy = "state_party_name_latest"
            conflict_reason = "multiple_exact_matches"
        elif len(fallback) == 1:
            selected = fallback[0]
            match_strategy = "state_name_fallback"
            selected_party = _normalize_party(selected.get("Cand_Party_Affiliation"))
            if selected_party != party:
                conflict_reason = "party_mismatch_fallback"
        elif len(fallback) > 1:
            selected = sorted(fallback, key=lambda item: str(item.get("Coverage_End_Date") or ""), reverse=True)[0]
            match_strategy = "state_name_fallback_latest"
            conflict_reason = "multiple_fallback_matches"

        out["FEC Candidate ID"] = str(selected.get("Cand_Id") or "") if selected else ""
        out["FEC Candidate Name"] = str(selected.get("Cand_Name") or "") if selected else ""
        out["FEC Party"] = _normalize_party(selected.get("Cand_Party_Affiliation")) if selected else ""
        out["FEC Total Receipts"] = str(selected.get("Total_Receipt") or "") if selected else ""
        out["FEC Cash On Hand"] = str(selected.get("Cash_On_Hand_COP") or "") if selected else ""
        out["FEC Match Strategy"] = match_strategy
        out["FEC Conflict"] = conflict_reason
        enriched.append(out)

        audit.append(
            {
                "seat": seat,
                "state": state,
                "ballotpedia_name": row.get("BallotpediaName") or "",
                "party": party,
                "match_strategy": match_strategy,
                "matched_candidate_id": out["FEC Candidate ID"],
                "matched_candidate_name": out["FEC Candidate Name"],
                "conflict": conflict_reason,
            }
        )
        if conflict_reason:
            conflicts.append(dict(audit[-1]))

    return enriched, audit, conflicts


def build_senate_fec_linkage(
    *,
    senate_candidate_rollup: Path = DEFAULT_SENATE_CANDIDATE_ROLLUP,
    fec_candidate_summary: Path = DEFAULT_FEC_CANDIDATE_SUMMARY_FILE,
    output_enriched: Path = DEFAULT_OUTPUT_ENRICHED,
    output_audit: Path = DEFAULT_OUTPUT_AUDIT,
    output_conflicts: Path = DEFAULT_OUTPUT_CONFLICTS,
) -> dict[str, int]:
    senate_rows = _load_csv_rows(senate_candidate_rollup)
    fec_rows = _load_csv_rows(fec_candidate_summary)
    enriched, audit, conflicts = link_senate_candidates_with_fec(senate_rows, fec_rows)
    _write_csv(output_enriched, enriched)
    _write_csv(output_audit, audit)
    _write_csv(output_conflicts, conflicts)
    return {
        "senate_rows": len(senate_rows),
        "fec_rows": len(fec_rows),
        "matched_rows": sum(1 for row in enriched if row.get("FEC Candidate ID")),
        "conflicts": len(conflicts),
    }
