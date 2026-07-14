"""Shared parsing of visible heading prefixes.

The detector needs the same understanding of prefixes in scoring, title
stripping, and heading-number validation. Keep this module independent from
the rest of the engine to avoid import cycles.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HeadingPrefix:
    kind: str
    number: str
    tokens: tuple[int, ...]
    level: int
    title: str
    word: str | None = None


_NUMBER = r"\d+(?:\.\d+){0,3}"
_ROMAN = r"[ivxlcdm]+"

_CHAPTER_PREFIX_RE = re.compile(
    rf"^\s*(?P<word>глава|раздел|часть|chapter|section|part)\s+"
    rf"(?P<number>{_NUMBER}|{_ROMAN})(?:[.)])?"
    rf"(?:\s*[:\-–—]\s*|\s+)?(?P<title>.*)$",
    re.IGNORECASE,
)
_NUMERIC_PREFIX_RE = re.compile(
    rf"^\s*(?P<number>{_NUMBER})(?P<trailing>[.)]?)(?P<rest>.*)$",
    re.IGNORECASE,
)
_VALID_ROMAN_RE = re.compile(
    r"^m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$",
    re.IGNORECASE,
)


def _roman_to_int(raw: str) -> int | None:
    if not raw or not _VALID_ROMAN_RE.match(raw):
        return None
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    prev = 0
    for ch in reversed(raw.lower()):
        value = values[ch]
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total if total > 0 else None


def _tokens_from_number(raw: str) -> tuple[int, ...] | None:
    if raw.isdigit() or "." in raw:
        try:
            return tuple(int(part) for part in raw.split("."))
        except ValueError:
            return None
    roman = _roman_to_int(raw)
    if roman is None:
        return None
    return (roman,)


def _prefix_from_match(match: re.Match[str], kind: str) -> HeadingPrefix | None:
    raw = match.group("number")
    tokens = _tokens_from_number(raw)
    if not tokens:
        return None
    if kind == "number":
        trailing = match.group("trailing") or ""
        rest = match.group("rest") or ""
        if not trailing and rest and not rest[0].isspace():
            return None
        title = rest.strip()
    else:
        title = (match.group("title") or "").strip()
    if kind == "number" and not title:
        return None
    number = ".".join(str(part) for part in tokens)
    return HeadingPrefix(
        kind=kind,
        number=number,
        tokens=tokens,
        level=max(1, min(len(tokens), 3)),
        title=title,
        word=(match.groupdict().get("word") or None),
    )


def parse_heading_prefix(text: str) -> HeadingPrefix | None:
    stripped = text.strip()
    if not stripped:
        return None
    chapter = _CHAPTER_PREFIX_RE.match(stripped)
    if chapter:
        parsed = _prefix_from_match(chapter, "chapter_word")
        if parsed is not None:
            return parsed
    numeric = _NUMERIC_PREFIX_RE.match(stripped)
    if numeric:
        return _prefix_from_match(numeric, "number")
    return None


def strip_heading_prefix(text: str) -> str:
    prefix = parse_heading_prefix(text)
    return prefix.title if prefix is not None else text.strip()
