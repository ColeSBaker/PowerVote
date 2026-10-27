from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Callable


ParseAllFn = Callable[..., tuple[list[dict], list[dict], list[dict], dict]]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze(item) for item in value))
    if isinstance(value, Path):
        return str(value.resolve())
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    try:
        hash(value)
        return repr(value)
    except TypeError:
        return repr(value)


class ParseAllCache:
    """In-memory cache wrapper for parser.parse_all results.

    Returns defensive deep copies so tests can mutate rows without
    contaminating cached shared state.
    """

    def __init__(
        self,
        parse_all_fn: ParseAllFn,
        *,
        default_cache_path: Path | None = None,
        copy_mode: str = "deep",
    ):
        self._parse_all = parse_all_fn
        self._default_cache_path = (
            default_cache_path
            if default_cache_path is not None
            else Path(".cache") / "ballotpedia-rollup-test-parse-cache.json"
        )
        if copy_mode not in {"deep", "shared_readonly"}:
            raise ValueError(f"Unsupported copy_mode={copy_mode!r}")
        self._copy_mode = copy_mode
        self._cache: dict[tuple[str, tuple[tuple[str, Any], ...]], tuple[list[dict], list[dict], list[dict], dict]] = {}

    def __call__(self, input_dir: Path, **kwargs: Any) -> tuple[list[dict], list[dict], list[dict], dict]:
        if kwargs.get("incremental"):
            return self._parse_all(input_dir, **kwargs)

        key = (
            str(Path(input_dir).resolve()),
            tuple(sorted((str(k), _freeze(v)) for k, v in kwargs.items())),
        )
        if key not in self._cache:
            parse_kwargs = dict(kwargs)
            parse_kwargs.setdefault("incremental", True)
            parse_kwargs.setdefault("cache_path", self._default_cache_path)
            self._cache[key] = self._parse_all(input_dir, **parse_kwargs)
        if self._copy_mode == "shared_readonly":
            return self._cache[key]
        return copy.deepcopy(self._cache[key])


def parse_cache_copy_mode_from_env() -> str:
    mode = os.getenv("POWERVOTE_TEST_PARSE_CACHE_MODE", "deep").strip().lower()
    if mode in {"", "deep"}:
        return "deep"
    if mode in {"shared", "shared_readonly", "no_deepcopy", "fast"}:
        return "shared_readonly"
    raise ValueError(
        "POWERVOTE_TEST_PARSE_CACHE_MODE must be one of: deep, shared_readonly, shared, no_deepcopy, fast"
    )
