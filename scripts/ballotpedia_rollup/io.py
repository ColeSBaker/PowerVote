"""Input/output helpers for Ballotpedia rollup parser."""
from __future__ import annotations

import csv
import json
from dataclasses import fields, is_dataclass
from pathlib import Path


def list_input_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*.txt") if path.is_file())


def _row_to_dict(row: object) -> dict:
    if hasattr(row, "to_dict"):
        return row.to_dict()
    if is_dataclass(row):
        return {field.name: getattr(row, field.name) for field in fields(row)}
    if isinstance(row, dict):
        return dict(row)
    raise TypeError(f"Unsupported row type: {type(row)!r}")


def write_json(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [_row_to_dict(row) for row in rows]
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
def write_jsonl(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_row_to_dict(row), sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_dicts = [_row_to_dict(row) for row in rows]
    for row in row_dicts:
        for key, value in list(row.items()):
            if isinstance(value, (dict, list)):
                row[key] = json.dumps(value, sort_keys=True)
    fieldnames = sorted({key for row in row_dicts for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in row_dicts:
            writer.writerow(row)


def write_rows(path: Path, rows: list[object], output_format: str) -> None:
    if output_format == "jsonl":
        write_jsonl(path, rows)
        return
    if output_format == "csv":
        write_csv(path, rows)
        return
    raise ValueError(f"Unsupported output format: {output_format}")
