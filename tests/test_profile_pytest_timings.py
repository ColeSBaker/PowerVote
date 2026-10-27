from __future__ import annotations

from pathlib import Path

from scripts.profile_pytest_timings import (
    PhaseTimingRow,
    aggregate_by_module,
    concentration,
    merge_phase_rows,
    parse_junitxml,
)


def test_parse_junitxml_extracts_case_times_as_call_phase_only(tmp_path: Path) -> None:
    report = tmp_path / "report.xml"
    report.write_text(
        """
        <testsuites>
          <testsuite name=\"pytest\" tests=\"2\" failures=\"0\" errors=\"0\" skipped=\"0\" time=\"1.5\">
            <testcase classname=\"tests.test_alpha.AlphaTests\" name=\"test_a\" time=\"0.4\" />
            <testcase classname=\"tests.test_beta.BetaTests\" name=\"test_b\" time=\"1.1\" />
          </testsuite>
        </testsuites>
        """,
        encoding="utf-8",
    )

    cases = parse_junitxml(report)

    assert len(cases) == 2
    assert cases[0].nodeid == "tests.test_alpha.AlphaTests::test_a"
    assert cases[0].setup_seconds == 0.0
    assert cases[0].call_seconds == 0.4
    assert cases[0].teardown_seconds == 0.0
    assert cases[0].total_seconds == 0.4


def test_merge_phase_rows_combines_setup_call_teardown() -> None:
    rows = [
        PhaseTimingRow(nodeid="t::a", classname="tests.test_alpha.Alpha", when="setup", duration=0.4),
        PhaseTimingRow(nodeid="t::a", classname="tests.test_alpha.Alpha", when="call", duration=1.0),
        PhaseTimingRow(nodeid="t::a", classname="tests.test_alpha.Alpha", when="teardown", duration=0.1),
    ]

    cases = merge_phase_rows(rows)

    assert len(cases) == 1
    assert cases[0].setup_seconds == 0.4
    assert cases[0].call_seconds == 1.0
    assert cases[0].teardown_seconds == 0.1
    assert cases[0].total_seconds == 1.5


def test_aggregate_by_module_sums_module_durations() -> None:
    rows = [
        PhaseTimingRow(nodeid="a::1", classname="tests.test_alpha.Alpha", when="call", duration=1.2),
        PhaseTimingRow(nodeid="a::2", classname="tests.test_alpha.Alpha", when="call", duration=0.3),
        PhaseTimingRow(nodeid="b::1", classname="tests.test_beta.Beta", when="call", duration=2.0),
    ]

    module_totals = aggregate_by_module(merge_phase_rows(rows))

    assert module_totals[0].module == "tests.test_beta"
    assert module_totals[0].time_seconds == 2.0
    assert module_totals[1].module == "tests.test_alpha"
    assert module_totals[1].time_seconds == 1.5


def test_concentration_reports_top_n_share() -> None:
    rows = [
        PhaseTimingRow(nodeid="a", classname="tests.test_alpha", when="call", duration=5.0),
        PhaseTimingRow(nodeid="b", classname="tests.test_beta", when="call", duration=3.0),
        PhaseTimingRow(nodeid="c", classname="tests.test_gamma", when="call", duration=2.0),
    ]

    top_1, top_2 = concentration(merge_phase_rows(rows), [1, 2])

    assert top_1.top_n == 1
    assert top_1.share == 0.5
    assert top_2.top_n == 2
    assert top_2.share == 0.8


def test_aggregate_by_module_keeps_function_style_module_names() -> None:
    rows = [
        PhaseTimingRow(
            nodeid="tests.test_profile_pytest_timings::test_a",
            classname="tests.test_profile_pytest_timings",
            when="call",
            duration=0.5,
        ),
        PhaseTimingRow(
            nodeid="tests.test_profile_pytest_timings::test_b",
            classname="tests.test_profile_pytest_timings",
            when="call",
            duration=0.2,
        ),
    ]

    module_totals = aggregate_by_module(merge_phase_rows(rows))

    assert module_totals[0].module == "tests.test_profile_pytest_timings"
    assert module_totals[0].time_seconds == 0.7
