"""Consolidation and precedence logic for rollup rows."""
from __future__ import annotations

import re


def consolidate_general_rows(rows: list[dict]) -> list[dict]:
    by_seat: dict[str, dict] = {}
    for row in rows:
        seat = row["seat"]
        existing = by_seat.get(seat)
        if existing is None:
            by_seat[seat] = row
            continue
        if row.get("source_priority", 0) > existing.get("source_priority", 0):
            for reason_field in ("primary_reason_d", "primary_reason_r", "primary_reason_np"):
                if not row.get(reason_field) and existing.get(reason_field):
                    row[reason_field] = existing[reason_field]
            if not row.get("incumbent_name") and existing.get("incumbent_name"):
                row["incumbent_name"] = existing["incumbent_name"]
                row["incumbent_party"] = existing.get("incumbent_party") or row.get("incumbent_party")
                row.setdefault("parser_notes", []).append("incumbent_from_state_rollup")
            by_seat[seat] = row
        elif existing is not None and row.get("source_priority", 0) == existing.get("source_priority", 0):
            notes = existing.setdefault("parser_notes", [])
            notes.append(f"conflict_same_priority:{row.get('source_file')}")
        else:
            for reason_field in ("primary_reason_d", "primary_reason_r", "primary_reason_np"):
                if not existing.get(reason_field) and row.get(reason_field):
                    existing[reason_field] = row[reason_field]
            if not existing.get("incumbent_name") and row.get("incumbent_name"):
                existing["incumbent_name"] = row["incumbent_name"]
                existing["incumbent_party"] = row.get("incumbent_party") or existing.get("incumbent_party")
                existing.setdefault("parser_notes", []).append("incumbent_from_state_rollup")
    consolidated = list(by_seat.values())
    for row in consolidated:
        row.pop("source_priority", None)
    return sorted(consolidated, key=lambda row: row["seat"])


def _status_rank(status: str) -> int:
    return {"complete": 4, "runoff": 3, "ongoing": 2, "upcoming": 1, "unknown": 0, "none": -1}.get(status, 0)


def _normalize_name(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalized_candidate_key(row: dict) -> tuple[str, ...]:
    names = row.get("candidates") or []
    if not isinstance(names, list):
        return ()
    normalized = sorted({_normalize_name(name) for name in names if _normalize_name(name)})
    return tuple(normalized)


def _merge_primary_rows(existing: dict, incoming: dict) -> dict:
    merged = dict(existing)
    merged_notes = merged.setdefault("parser_notes", [])
    for note in incoming.get("parser_notes") or []:
        if note not in merged_notes:
            merged_notes.append(note)

    merged_candidates = merged.setdefault("candidates", [])
    for candidate_name in incoming.get("candidates") or []:
        if candidate_name not in merged_candidates:
            merged_candidates.append(candidate_name)

    merged_party_map = dict(merged.get("candidate_party_map") or {})
    for candidate_name, party_value in (incoming.get("candidate_party_map") or {}).items():
        existing_party = merged_party_map.get(candidate_name)
        if existing_party in (None, "", "OTH"):
            merged_party_map[candidate_name] = party_value
    merged["candidate_party_map"] = merged_party_map

    merged_incumbent_map = dict(merged.get("candidate_incumbent_map") or {})
    for candidate_name, incumbent_value in (incoming.get("candidate_incumbent_map") or {}).items():
        merged_incumbent_map[candidate_name] = bool(merged_incumbent_map.get(candidate_name) or incumbent_value)
    merged["candidate_incumbent_map"] = merged_incumbent_map

    existing_reason = str(merged.get("cancellation_reason") or "").strip()
    incoming_reason = str(incoming.get("cancellation_reason") or "").strip()
    if not existing_reason and incoming_reason:
        merged["cancellation_reason"] = incoming_reason
    return merged


def suppress_np_oth_primary_mirrors(rows: list[dict]) -> list[dict]:
    by_signature: dict[tuple[str, str, tuple[str, ...]], list[dict]] = {}
    for row in rows:
        signature = (
            row.get("seat", ""),
            row.get("round", ""),
            _normalized_candidate_key(row),
        )
        by_signature.setdefault(signature, []).append(row)

    suppressed_ids: set[str] = set()
    for grouped in by_signature.values():
        np_rows = [row for row in grouped if row.get("party") == "NP"]
        oth_rows = [row for row in grouped if row.get("party") == "OTH"]
        if not np_rows or not oth_rows:
            continue
        has_district_np = any("state_rollup_used" not in (row.get("parser_notes") or []) for row in np_rows)
        if not has_district_np:
            continue
        # Preserve candidate-level metadata from state rollup before suppressing mirrors.
        merged_np = np_rows[0]
        for oth_row in oth_rows:
            merged_np = _merge_primary_rows(merged_np, oth_row)
        np_rows[0].clear()
        np_rows[0].update(merged_np)
        for oth_row in oth_rows:
            if "state_rollup_used" in (oth_row.get("parser_notes") or []):
                primary_id = str(oth_row.get("primary_id") or "").strip()
                if primary_id:
                    suppressed_ids.add(primary_id)

    if not suppressed_ids:
        return rows
    return [row for row in rows if str(row.get("primary_id") or "").strip() not in suppressed_ids]


def consolidate_primary_rows(rows: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for row in rows:
        key = row["primary_id"]
        existing = by_id.get(key)
        if existing is None:
            by_id[key] = row
            continue
        if row.get("source_priority", 0) > existing.get("source_priority", 0):
            by_id[key] = _merge_primary_rows(row, existing)
            continue
        if row.get("source_priority", 0) == existing.get("source_priority", 0) and _status_rank(row.get("status", "unknown")) > _status_rank(existing.get("status", "unknown")):
            by_id[key] = _merge_primary_rows(row, existing)
            continue
        by_id[key] = _merge_primary_rows(existing, row)
    consolidated = suppress_np_oth_primary_mirrors(list(by_id.values()))
    for row in consolidated:
        row.pop("source_priority", None)
    return sorted(consolidated, key=lambda row: row["primary_id"])


def backfill_primary_links(general_rows: list[dict], primary_rows: list[dict]) -> None:
    by_seat_party: dict[tuple[str, str], list[dict]] = {}
    by_primary_id: dict[str, dict] = {}
    for row in primary_rows:
        by_seat_party.setdefault((row["seat"], row["party"]), []).append(row)
        primary_id = str(row.get("primary_id") or "").strip()
        if primary_id:
            by_primary_id[primary_id] = row

    for row in general_rows:
        for party, status_field, id_field, reason_field in (
            ("D", "primary_status_d", "primary_id_d", "primary_reason_d"),
            ("R", "primary_status_r", "primary_id_r", "primary_reason_r"),
            ("NP", "primary_status_np", "primary_id_np", "primary_reason_np"),
        ):
            existing_primary_id = str(row.get(id_field) or "").strip()
            if existing_primary_id:
                linked_row = by_primary_id.get(existing_primary_id)
                if linked_row:
                    # Always sync status so runoff promotion is reflected in the general row.
                    row[status_field] = linked_row["status"]
                    if not row.get(reason_field):
                        row[reason_field] = str(linked_row.get("cancellation_reason") or "").strip()
                continue
            options = by_seat_party.get((row["seat"], party), [])
            if not options:
                continue
            options = sorted(options, key=lambda item: (_status_rank(item["status"]), item["round"]), reverse=True)
            row[id_field] = options[0]["primary_id"]
            row[status_field] = options[0]["status"]
            row[reason_field] = str(options[0].get("cancellation_reason") or "").strip()

    for row in general_rows:
        for status_field, reason_field in (
            ("primary_status_d", "primary_reason_d"),
            ("primary_status_r", "primary_reason_r"),
        ):
            status_value = str(row.get(status_field) or "").strip().lower()
            reason_value = str(row.get(reason_field) or "").strip().lower()
            if status_value == "none" and not reason_value:
                row[reason_field] = "no_primary_structure"


def split_and_link_primary_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    primary_rows = [dict(row) for row in rows if row.get("round") != "runoff"]
    runoff_rows = [dict(row) for row in rows if row.get("round") == "runoff"]

    by_seat_party_primary: dict[tuple[str, str], dict] = {}
    for row in primary_rows:
        key = (row.get("seat", ""), row.get("party", ""))
        existing = by_seat_party_primary.get(key)
        if existing is None or _status_rank(row.get("status", "unknown")) > _status_rank(existing.get("status", "unknown")):
            by_seat_party_primary[key] = row

    for runoff_row in runoff_rows:
        key = (runoff_row.get("seat", ""), runoff_row.get("party", ""))
        parent_primary = by_seat_party_primary.get(key)
        if parent_primary is None:
            continue

        runoff_id = runoff_row["primary_id"]
        parent_id = parent_primary["primary_id"]
        parent_primary["runoff_id"] = runoff_id
        runoff_row["parent_primary_id"] = parent_id

        # A linked runoff row always means the primary resulted in a runoff,
        # regardless of whether the runoff itself is upcoming or already complete.
        parent_primary["status"] = "runoff"
        if not parent_primary.get("runoff_candidate_1"):
            parent_primary["runoff_candidate_1"] = runoff_row.get("runoff_candidate_1")
        if not parent_primary.get("runoff_candidate_2"):
            parent_primary["runoff_candidate_2"] = runoff_row.get("runoff_candidate_2")

    return (
        sorted(primary_rows, key=lambda row: row["primary_id"]),
        sorted(runoff_rows, key=lambda row: row["primary_id"]),
    )
