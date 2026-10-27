"""Shared Kalshi integrity checks used by pipeline and tests."""
from __future__ import annotations

from dataclasses import dataclass

from .kalshi import odds_map_sum_status

INTEGRITY_ISSUES: tuple[str, ...] = (
    "missing_sum_status",
    "sum_status_mismatch",
    "odds_map_sum_out_of_band",
    "missing_odds_map_with_markets",
    "classification_mismatch",
)


@dataclass(frozen=True)
class KalshiIntegrityResult:
    passed: bool
    status: str
    issues: list[str]
    odds_map_sum: float
    sum_status: str


def issue_column_name(issue: str) -> str:
    return f"kalshi_integrity_issue_{issue}"


def _odds_map_for_row(row: dict, row_type: str) -> dict[str, float]:
    if row_type == "general":
        raw = row.get("kalshi_general_odds_map") or {}
    elif row_type == "runoff":
        raw = row.get("kalshi_runoff_odds_map") or {}
    else:
        raw = row.get("kalshi_primary_odds_map") or {}

    normalized: dict[str, float] = {}
    for key, value in (raw or {}).items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized


def evaluate_kalshi_row_integrity(row: dict, *, row_type: str) -> KalshiIntegrityResult:
    issues: list[str] = []
    odds_map = _odds_map_for_row(row, row_type)
    odds_sum, computed_sum_status = odds_map_sum_status(odds_map)

    audit = row.get("kalshi_join_audit") or {}
    audit_sum_status = str(audit.get("sum_status") or "").strip()
    if not audit_sum_status:
        issues.append("missing_sum_status")
    elif audit_sum_status != computed_sum_status:
        issues.append("sum_status_mismatch")

    if computed_sum_status == "out_of_band":
        issues.append("odds_map_sum_out_of_band")

    if int(row.get("kalshi_market_count") or 0) > 0 and not odds_map:
        issues.append("missing_odds_map_with_markets")

    if row_type == "primary":
        primary_type = str(row.get("primary_type") or "partisan_binary").strip()
        advance_count = int(row.get("advance_count") or 1)
        if primary_type in ("top_two", "top_four") and advance_count == 1:
            issues.append("classification_mismatch")

    # Keep issues deterministic and bounded to known values.
    unique_issues = sorted({issue for issue in issues if issue in INTEGRITY_ISSUES})
    passed = len(unique_issues) == 0
    return KalshiIntegrityResult(
        passed=passed,
        status="pass" if passed else "fail",
        issues=unique_issues,
        odds_map_sum=odds_sum,
        sum_status=computed_sum_status,
    )


def annotate_rows_with_kalshi_integrity(
    general_rows: list[dict],
    primary_rows: list[dict],
    runoff_rows: list[dict],
) -> None:
    for row_type, rows in (("general", general_rows), ("primary", primary_rows), ("runoff", runoff_rows)):
        for row in rows:
            result = evaluate_kalshi_row_integrity(row, row_type=row_type)
            row["kalshi_integrity_passed"] = result.passed
            row["kalshi_integrity_status"] = result.status
            row["kalshi_integrity_issue_count"] = len(result.issues)
            row.pop("kalshi_integrity_issues", None)
            issue_set = set(result.issues)
            for issue in INTEGRITY_ISSUES:
                row[issue_column_name(issue)] = issue in issue_set
