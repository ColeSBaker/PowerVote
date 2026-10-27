from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import xml.etree.ElementTree as ET


WhenLiteral = Literal["setup", "call", "teardown"]


@dataclass(frozen=True)
class PhaseTimingRow:
    nodeid: str
    classname: str
    when: WhenLiteral
    duration: float


@dataclass(frozen=True)
class TestCaseTiming:
    nodeid: str
    classname: str
    setup_seconds: float
    call_seconds: float
    teardown_seconds: float

    @property
    def total_seconds(self) -> float:
        return self.setup_seconds + self.call_seconds + self.teardown_seconds


@dataclass(frozen=True)
class ModuleTiming:
    module: str
    time_seconds: float


@dataclass(frozen=True)
class ConcentrationPoint:
    top_n: int
    cumulative_seconds: float
    share: float


class TimingPlugin:
    def __init__(self) -> None:
        self.rows: list[PhaseTimingRow] = []

    def pytest_runtest_logreport(self, report):  # type: ignore[no-untyped-def]
        when = report.when
        if when not in {"setup", "call", "teardown"}:
            return
        self.rows.append(
            PhaseTimingRow(
                nodeid=report.nodeid,
                classname=getattr(report, "location", ("", "", ""))[0].replace("/", ".").replace(".py", ""),
                when=when,
                duration=float(report.duration or 0.0),
            )
        )


def parse_junitxml(path: Path) -> list[TestCaseTiming]:
    root = ET.parse(path).getroot()
    phase_rows: list[PhaseTimingRow] = []
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname", "")
        name = testcase.attrib.get("name", "")
        nodeid = f"{classname}::{name}" if classname else name
        time_seconds = float(testcase.attrib.get("time", "0") or 0)
        phase_rows.append(
            PhaseTimingRow(
                nodeid=nodeid,
                classname=classname,
                when="call",
                duration=time_seconds,
            )
        )
    return merge_phase_rows(phase_rows)


def merge_phase_rows(rows: list[PhaseTimingRow]) -> list[TestCaseTiming]:
    buckets: dict[str, dict[str, float | str]] = {}
    for row in rows:
        if row.nodeid not in buckets:
            buckets[row.nodeid] = {
                "classname": row.classname,
                "setup": 0.0,
                "call": 0.0,
                "teardown": 0.0,
            }
        buckets[row.nodeid][row.when] = float(buckets[row.nodeid][row.when]) + row.duration

    cases: list[TestCaseTiming] = []
    for nodeid, data in buckets.items():
        cases.append(
            TestCaseTiming(
                nodeid=nodeid,
                classname=str(data["classname"]),
                setup_seconds=float(data["setup"]),
                call_seconds=float(data["call"]),
                teardown_seconds=float(data["teardown"]),
            )
        )
    return cases


def aggregate_by_module(cases: list[TestCaseTiming]) -> list[ModuleTiming]:
    totals: dict[str, float] = {}
    for case in cases:
        parts = case.classname.split(".")
        if len(parts) <= 1:
            module = case.classname
        elif parts[-1].startswith("test_"):
            module = case.classname
        else:
            module = ".".join(parts[:-1])
        totals[module] = totals.get(module, 0.0) + case.total_seconds
    return sorted(
        [ModuleTiming(module=module, time_seconds=seconds) for module, seconds in totals.items()],
        key=lambda item: item.time_seconds,
        reverse=True,
    )


def concentration(cases: list[TestCaseTiming], top_ns: list[int]) -> list[ConcentrationPoint]:
    sorted_cases = sorted(cases, key=lambda case: case.total_seconds, reverse=True)
    total = sum(case.total_seconds for case in sorted_cases)
    output: list[ConcentrationPoint] = []
    for top_n in top_ns:
        cumulative = sum(case.total_seconds for case in sorted_cases[:top_n])
        share = cumulative / total if total else 0.0
        output.append(
            ConcentrationPoint(top_n=top_n, cumulative_seconds=cumulative, share=share)
        )
    return output


def run_pytest(pytest_args: list[str], junitxml_path: Path) -> tuple[int, list[TestCaseTiming]]:
    import pytest

    plugin = TimingPlugin()
    command = [*pytest_args, f"--junitxml={junitxml_path}"]
    exit_code = pytest.main(command, plugins=[plugin])
    return exit_code, merge_phase_rows(plugin.rows)


def print_summary(cases: list[TestCaseTiming], top_tests: int, top_modules: int) -> None:
    total = sum(case.total_seconds for case in cases)
    print(f"Total tests: {len(cases)}")
    print(f"Total measured case time: {total:.3f}s")

    print("\nConcentration:")
    for point in concentration(cases, [5, 10, 20]):
        print(
            f"- Top {point.top_n:>2}: {point.cumulative_seconds:>8.3f}s "
            f"({point.share * 100:>5.1f}%)"
        )

    print("\nSlowest tests:")
    for case in sorted(cases, key=lambda row: row.total_seconds, reverse=True)[:top_tests]:
        print(
            "- "
            f"{case.total_seconds:>8.3f}s "
            f"(setup={case.setup_seconds:.3f}s, call={case.call_seconds:.3f}s, teardown={case.teardown_seconds:.3f}s) "
            f"{case.nodeid}"
        )

    print("\nSlowest modules:")
    for module in aggregate_by_module(cases)[:top_modules]:
        print(f"- {module.time_seconds:>8.3f}s  {module.module}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run pytest and summarize per-test timings.")
    parser.add_argument(
        "--junitxml",
        default=".tmp/pytest-timings.xml",
        help="Path to JUnit XML report. Used for parse-only mode, and as output path when running pytest.",
    )
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="Do not run pytest; parse an existing --junitxml report.",
    )
    parser.add_argument("--top-tests", type=int, default=15, help="Number of slow tests to print.")
    parser.add_argument("--top-modules", type=int, default=10, help="Number of slow modules to print.")
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to pytest. Example: -- tests -q",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    report_path = Path(args.junitxml)

    if args.parse_only:
        if not report_path.exists():
            raise FileNotFoundError(f"JUnit XML report not found: {report_path}")
        cases = parse_junitxml(report_path)
        print_summary(cases, top_tests=args.top_tests, top_modules=args.top_modules)
        print("\nNote: parse-only mode uses call-phase time from JUnit XML.")
        return 0

    report_path.parent.mkdir(parents=True, exist_ok=True)
    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    exit_code, cases = run_pytest(pytest_args or ["tests", "-q"], report_path)
    if exit_code != 0:
        return int(exit_code)

    print_summary(cases, top_tests=args.top_tests, top_modules=args.top_modules)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
