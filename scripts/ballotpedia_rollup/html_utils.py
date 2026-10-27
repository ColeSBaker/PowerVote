"""String-based HTML helper utilities for raw Ballotpedia snapshots."""
from __future__ import annotations

import re

HEADING_RE = re.compile(r"<h([2-4])[^>]*>(.*?)</h\1>", flags=re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(value: str) -> str:
    return TAG_RE.sub("", value).strip()


def find_anchor_ids(html: str) -> set[str]:
    return set(re.findall(r'id="([^"]+)"', html, flags=re.IGNORECASE))


def contains_class(html: str, class_name: str) -> bool:
    escaped = re.escape(class_name)
    return bool(re.search(r'class="[^"]*\b' + escaped + r'\b[^"]*"', html, flags=re.IGNORECASE))


def find_heading_positions(html: str) -> list[tuple[int, int, str]]:
    positions: list[tuple[int, int, str]] = []
    for match in HEADING_RE.finditer(html):
        title = strip_tags(match.group(2))
        positions.append((match.start(), match.end(), title))
    return positions


def section_after_heading(html: str, heading_substring: str) -> str | None:
    headings = find_heading_positions(html)
    target_index = None
    for index, (_start, end, title) in enumerate(headings):
        if heading_substring.lower() in title.lower():
            target_index = (index, end)
            break
    if target_index is None:
        return None
    index, start_offset = target_index
    end_offset = headings[index + 1][0] if index + 1 < len(headings) else len(html)
    return html[start_offset:end_offset]
