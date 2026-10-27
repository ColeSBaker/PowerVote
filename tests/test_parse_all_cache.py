from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ballotpedia_rollup.parse_all_cache import ParseAllCache, parse_cache_copy_mode_from_env


def test_parse_all_cache_reuses_underlying_call_for_identical_inputs(tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_parse_all(input_dir: Path, **kwargs):
        calls["count"] += 1
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all)

    first = cache(tmp_path, office="us_house")
    second = cache(tmp_path, office="us_house")

    assert calls["count"] == 1
    assert first == second


def test_parse_all_cache_returns_independent_copies(tmp_path: Path) -> None:
    def fake_parse_all(input_dir: Path, **kwargs):
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all)

    first = cache(tmp_path, office="us_house")
    first[0][0]["seat"] = "CHANGED"
    second = cache(tmp_path, office="us_house")

    assert second[0][0]["seat"] == "TX-01"


def test_parse_all_cache_skips_cache_for_incremental_runs(tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_parse_all(input_dir: Path, **kwargs):
        calls["count"] += 1
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all)

    cache(tmp_path, office="us_house", incremental=True)
    cache(tmp_path, office="us_house", incremental=True)

    assert calls["count"] == 2


def test_parse_all_cache_handles_unhashable_kwargs(tmp_path: Path) -> None:
    calls = {"count": 0}

    def fake_parse_all(input_dir: Path, **kwargs):
        calls["count"] += 1
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all)

    cache(tmp_path, office="us_house", kalshi_indexes={}, fec_rows=[{"id": 1}])
    cache(tmp_path, office="us_house", kalshi_indexes={}, fec_rows=[{"id": 1}])

    assert calls["count"] == 1


def test_parse_all_cache_handles_unhashable_objects(tmp_path: Path) -> None:
    class Obj:
        def __init__(self, value: str):
            self.value = value

        def __repr__(self) -> str:
            return f"Obj({self.value})"

    calls = {"count": 0}

    def fake_parse_all(input_dir: Path, **kwargs):
        calls["count"] += 1
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all)

    cache(tmp_path, office="us_house", fec_candidates=[Obj("A")])
    cache(tmp_path, office="us_house", fec_candidates=[Obj("A")])

    assert calls["count"] == 1



def test_parse_all_cache_enables_incremental_parser_cache_on_miss(tmp_path: Path) -> None:
    captured: list[dict] = []

    def fake_parse_all(input_dir: Path, **kwargs):
        captured.append(kwargs)
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all, default_cache_path=tmp_path / "parser-cache.json")

    cache(tmp_path, office="us_house")

    assert captured
    assert captured[0]["incremental"] is True
    assert str(captured[0]["cache_path"]).endswith("parser-cache.json")


def test_parse_all_cache_shared_readonly_returns_same_object(tmp_path: Path) -> None:
    def fake_parse_all(input_dir: Path, **kwargs):
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    cache = ParseAllCache(fake_parse_all, copy_mode="shared_readonly")

    first = cache(tmp_path, office="us_house")
    second = cache(tmp_path, office="us_house")

    assert first is second


def test_parse_all_cache_rejects_unsupported_copy_mode(tmp_path: Path) -> None:
    def fake_parse_all(input_dir: Path, **kwargs):
        return ([{"seat": "TX-01"}], [], [], {"district_detail": 1})

    with pytest.raises(ValueError, match="Unsupported copy_mode"):
        ParseAllCache(fake_parse_all, copy_mode="banana")


def test_parse_cache_copy_mode_from_env_defaults_to_deep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POWERVOTE_TEST_PARSE_CACHE_MODE", raising=False)
    assert parse_cache_copy_mode_from_env() == "deep"


def test_parse_cache_copy_mode_from_env_accepts_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWERVOTE_TEST_PARSE_CACHE_MODE", "fast")
    assert parse_cache_copy_mode_from_env() == "shared_readonly"
    monkeypatch.setenv("POWERVOTE_TEST_PARSE_CACHE_MODE", "shared")
    assert parse_cache_copy_mode_from_env() == "shared_readonly"


def test_parse_cache_copy_mode_from_env_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POWERVOTE_TEST_PARSE_CACHE_MODE", "invalid")
    with pytest.raises(ValueError, match="POWERVOTE_TEST_PARSE_CACHE_MODE"):
        parse_cache_copy_mode_from_env()
