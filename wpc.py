#!/usr/bin/env python3
"""word-pattern-checker：词格（字数 + 分句）校验器，供 agent 填词时调用。

契约见 DESIGN.md。核心是纯函数 check()，CLI 只是薄壳。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

__all__ = [
    "check",
    "parse_spec",
    "parse_draft",
    "count_cells",
    "syllable_cells",
    "syllables",
    "Report",
    "WpcError",
]

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2
EXIT_DRIFT = 3

KIND_TOO_MANY = "too_many"
KIND_TOO_FEW = "too_few"
KIND_SEG_COUNT = "seg_count_mismatch"
KIND_UNCLASSIFIED = "unclassified"
KIND_ESTIMATED = "estimated"

VIOLATION_KINDS = (KIND_TOO_MANY, KIND_TOO_FEW, KIND_SEG_COUNT, KIND_UNCLASSIFIED)

LANGS = ("zh", "ja", "ko", "en", "mixed")
LATIN_MODES = ("syllable", "letter", "word")
PUNCT_MODES = ("ignore", "count")
DIGITS_MODES = ("each", "word")

DEFAULT_OPTIONS = {
    "lang": "mixed",
    "latin": "syllable",
    "punct": "ignore",
    "digits": "each",
}


# --------------------------------------------------------------------------
# 错误
# --------------------------------------------------------------------------


class WpcError(Exception):
    """解析或用法的错误。CLI 捕获后一律 exit 2。"""

    def __init__(self, message: str, line: int | None = None):
        self.message = message
        self.line = line
        text = f"第 {line} 行：{message}" if line else message
        super().__init__(text)


# --------------------------------------------------------------------------
# 字符分类
# --------------------------------------------------------------------------

_HAN_RANGES = (
    (0x3007, 0x3007),  # 〇
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF),
    (0x2A700, 0x2EBEF),
    (0x2F800, 0x2FA1F),
    (0x30000, 0x323AF),
)
_KANA_RANGES = ((0x3040, 0x309F), (0x30A0, 0x30FF), (0x31F0, 0x31FF))
_HANGUL_SYLLABLES = (0xAC00, 0xD7A3)
_JAMO_RANGES = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xD7B0, 0xD7FF))
_HALFWIDTH_KANA = (0xFF61, 0xFF9F)
_IVS_RANGES = ((0xFE00, 0xFE0F), (0xE0100, 0xE01EF))

# DESIGN.md 列出的合并字符；片假名同形一并处理。
_SMALL_KANA = set("ぁぃぅぇぉゃゅょゎゕゖァィゥェォャュョヮヵヶ")

_VOWELS = set("aeiouy")
_APOSTROPHES = {"'", "\u2019", "\u02bc"}
_HYPHENS = {"-", "\u2010", "\u2011"}
_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}


def _in_ranges(ch: str, ranges: Iterable[tuple[int, int]]) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in ranges)


def is_han(ch: str) -> bool:
    return _in_ranges(ch, _HAN_RANGES) or ch in ("々", "〆")


def is_kana(ch: str) -> bool:
    return _in_ranges(ch, _KANA_RANGES)


def is_hangul_syllable(ch: str) -> bool:
    return _HANGUL_SYLLABLES[0] <= ord(ch) <= _HANGUL_SYLLABLES[1]


def is_jamo(ch: str) -> bool:
    return _in_ranges(ch, _JAMO_RANGES)


_LATIN_RANGES = (
    (0x0041, 0x005A),
    (0x0061, 0x007A),
    (0x00C0, 0x02AF),  # Latin-1 字母、Extended-A/B
    (0x1E00, 0x1EFF),  # Latin Extended Additional
    (0xFF21, 0xFF3A),  # 全角大写
    (0xFF41, 0xFF5A),  # 全角小写
)


def is_latin(ch: str) -> bool:
    if ch in _APOSTROPHES or ch in _HYPHENS:
        return False
    return _in_ranges(ch, _LATIN_RANGES)


def _is_ivs(ch: str) -> bool:
    return _in_ranges(ch, _IVS_RANGES)


# --------------------------------------------------------------------------
# 切格：音节
# --------------------------------------------------------------------------

# 例外表用「切分」表示而不是计数：计数 = 切分段数，cells 与 actual 才不会打架。
# 发现切错的词就补进来，key 一律小写。
_SYLLABLE_EXCEPTIONS = {
    # 单音节高频词
    "a": "a",
    "i": "i",
    "the": "the",
    "one": "one",
    "two": "two",
    "three": "three",
    "four": "four",
    "five": "five",
    "six": "six",
    "eight": "eight",
    "nine": "nine",
    "ten": "ten",
    "twelve": "twelve",
    "fire": "fire",
    "hour": "hour",
    "our": "our",
    "year": "year",
    "here": "here",
    "where": "where",
    "there": "there",
    "sure": "sure",
    "more": "more",
    "store": "store",
    "clothes": "clothes",
    "world": "world",
    "word": "word",
    "work": "work",
    # 常见切错
    "every": "ev|ery",
    "evening": "eve|ning",
    "eleven": "e|lev|en",
    "seven": "sev|en",
    "business": "busi|ness",
    "science": "sci|ence",
    "quiet": "qui|et",
    "poem": "po|em",
    "cruel": "cru|el",
    "people": "peo|ple",
    "little": "lit|tle",
    "table": "ta|ble",
    "flower": "flow|er",
    "power": "pow|er",
    "idea": "i|de|a",
    "area": "ar|e|a",
    "radio": "ra|di|o",
    "video": "vid|e|o",
    "piano": "pi|an|o",
    "create": "cre|ate",
    "real": "re|al",
    "being": "be|ing",
    "doing": "do|ing",
    "going": "go|ing",
    "seeing": "see|ing",
    "using": "us|ing",
    "family": "fam|i|ly",
    "beautiful": "beau|ti|ful",
    "chocolate": "choc|o|late",
    "vegetable": "veg|e|ta|ble",
    "restaurant": "res|tau|rant",
    "comfortable": "com|fort|a|ble",
    "interesting": "in|ter|est|ing",
    "different": "dif|fer|ent",
    "favorite": "fa|vor|ite",
    "memory": "mem|o|ry",
    "history": "his|to|ry",
    "delicious": "de|li|cious",
    "because": "be|cause",
    "before": "be|fore",
    "again": "a|gain",
    "above": "a|bove",
    "about": "a|bout",
    "away": "a|way",
    "always": "al|ways",
    "maybe": "may|be",
    "music": "mu|sic",
    "only": "on|ly",
    "also": "al|so",
    "into": "in|to",
    "onto": "on|to",
    "upon": "up|on",
    "very": "ver|y",
    "body": "bod|y",
    "city": "cit|y",
    "baby": "ba|by",
    "lady": "la|dy",
    "lonely": "lone|ly",
    "heaven": "heav|en",
    "given": "giv|en",
    "even": "e|ven",
    "open": "o|pen",
    "over": "o|ver",
    "ever": "ev|er",
    "never": "nev|er",
    "under": "un|der",
    "water": "wa|ter",
    "after": "af|ter",
    "other": "oth|er",
    "mother": "moth|er",
    "father": "fa|ther",
    "brother": "broth|er",
    "sister": "sis|ter",
    "winter": "win|ter",
    "summer": "sum|mer",
    "sugar": "sug|ar",
    "money": "mon|ey",
    "honey": "hon|ey",
    "journey": "jour|ney",
    "country": "coun|try",
}


def _silent_e(chunk: str, word: str) -> bool:
    """末段只有一个元音 e 且落在段尾，且不是 -le 结尾（-le 自成音节）。"""
    low = chunk.lower()
    if not low.endswith("e") or len(word) <= 2:
        return False
    if sum(1 for ch in low if ch in _VOWELS) != 1:
        return False
    prev = word[-2]
    return prev.isalpha() and prev.lower() not in _VOWELS


def _ends_with_le(word: str) -> bool:
    low = word.lower()
    return len(low) > 2 and low.endswith("le") and low[-3].isalpha() and low[-3] not in _VOWELS


def _drops_suffix(chunk: str, word: str) -> bool:
    """-ed / -es 在非 d/t、非 s/x/z/ch/sh 之后不单独成音节。"""
    low = word.lower()
    if len(low) <= 2 or len(chunk) < 2:
        return False
    if sum(1 for ch in chunk.lower() if ch in _VOWELS) != 1:
        return False
    if low.endswith("ed"):
        return low[-3] not in ("d", "t")
    if low.endswith("es"):
        if low[-4:-2] in ("ch", "sh"):
            return False
        return low[-3] not in ("s", "x", "z")
    return False


def _split_by_vowel_runs(word: str) -> list[str]:
    low = word.lower()
    runs: list[tuple[int, int]] = []
    i = 0
    n = len(low)
    while i < n:
        if low[i] in _VOWELS:
            j = i
            while j < n and low[j] in _VOWELS:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    if not runs:
        return [word]
    cuts = []
    for k in range(1, len(runs)):
        start = runs[k][0]
        prev_end = runs[k - 1][1]
        cuts.append(start - 1 if start - 1 >= prev_end else start)
    bounds = [0] + cuts + [len(word)]
    chunks = [word[bounds[k]:bounds[k + 1]] for k in range(len(bounds) - 1)]
    chunks = [c for c in chunks if c]
    if len(chunks) > 1 and _ends_with_le(low):
        return chunks
    if len(chunks) > 1 and _silent_e(chunks[-1], low):
        chunks[-2] += chunks[-1]
        chunks.pop()
    elif len(chunks) > 1 and _drops_suffix(chunks[-1], low):
        chunks[-2] += chunks[-1]
        chunks.pop()
    return chunks


def syllable_cells(word: str) -> list[str]:
    """把一个拉丁词切成音节，返回逐音节字符串。计数 = len(结果)。"""
    if not word:
        return []
    key = word.lower().strip("'\u2019\u02bc")
    if key and key in _SYLLABLE_EXCEPTIONS:
        out: list[str] = []
        pos = 0
        for seg in _SYLLABLE_EXCEPTIONS[key].split("|"):
            out.append(word[pos:pos + len(seg)])
            pos += len(seg)
        if pos < len(word):
            out[-1] += word[pos:]
        return [c for c in out if c]
    return _split_by_vowel_runs(word)


def syllables(word: str) -> int:
    """一个词（可含连字符）的音节数。"""
    total = 0
    for part in re.split(r"[-\u2010\u2011]", word):
        total += len(syllable_cells(part))
    return total


def _latin_cells(run: str, mode: str) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[-\u2010\u2011]", run):
        if not part:
            continue
        if mode == "letter":
            out.extend([c for c in part if c.isalpha()])
        elif mode == "word":
            out.append(part)
        else:
            out.extend(syllable_cells(part))
    return out


# --------------------------------------------------------------------------
# 切格：主入口
# --------------------------------------------------------------------------


def _normalize_for_count(text: str) -> str:
    """半角片假名逐字 NFKC，再整体 NFC。只用于计数，不改原文。"""
    buf = []
    for ch in text:
        if _HALFWIDTH_KANA[0] <= ord(ch) <= _HALFWIDTH_KANA[1]:
            buf.append(unicodedata.normalize("NFKC", ch))
        else:
            buf.append(ch)
    return unicodedata.normalize("NFC", "".join(buf))


def count_cells(
    text: str,
    lang: str = "mixed",
    *,
    latin: str = "syllable",
    punct: str = "ignore",
    digits: str = "each",
) -> tuple[list[str], list[dict]]:
    """把一段文本切成格，返回 (cells, warnings)。

    cells 里每个元素是「一格」的原文片段：合并的拗音是一个元素，英文音节是一个元素。
    """
    if lang not in LANGS:
        raise WpcError(f"未知语言 {lang}")
    if latin not in LATIN_MODES:
        raise WpcError(f"未知 latin 模式 {latin}")
    if punct not in PUNCT_MODES:
        raise WpcError(f"未知 punct 模式 {punct}")
    if digits not in DIGITS_MODES:
        raise WpcError(f"未知 digits 模式 {digits}")

    s = _normalize_for_count(text)
    merge_kana = lang in ("ja", "mixed")
    cells: list[str] = []
    warnings: list[dict] = []
    i = 0
    n = len(s)

    while i < n:
        ch = s[i]
        cat = unicodedata.category(ch)

        if _is_ivs(ch) or ch in _ZERO_WIDTH or cat == "Cf":
            i += 1
            continue
        if ch.isspace() or ch == "\u3000":
            i += 1
            continue
        if cat in ("Mn", "Mc", "Me"):
            if cells:
                cells[-1] += ch
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            run = s[i:j]
            if digits == "word":
                cells.append(run)
            else:
                cells.extend(run)
            i = j
            continue
        if is_latin(ch) or ch in _APOSTROPHES:
            j = i
            while j < n and (is_latin(s[j]) or s[j] in _APOSTROPHES or s[j] in _HYPHENS):
                j += 1
            cells.extend(_latin_cells(s[i:j], latin))
            i = j
            continue
        if cat.startswith("P"):
            if punct == "count":
                cells.append(ch)
            i += 1
            continue
        if is_han(ch):
            cells.append(ch)
            i += 1
            continue
        if is_kana(ch):
            if merge_kana and ch in _SMALL_KANA and cells and is_kana(cells[-1][-1]):
                cells[-1] += ch
            else:
                cells.append(ch)
            i += 1
            continue
        if is_hangul_syllable(ch):
            cells.append(ch)
            i += 1
            continue
        if is_jamo(ch):
            warnings.append({"kind": KIND_UNCLASSIFIED, "cell": ch})
            cells.append(ch)
            i += 1
            continue

        warnings.append({"kind": KIND_UNCLASSIFIED, "cell": ch})
        cells.append(ch)
        i += 1

    return cells, warnings


# --------------------------------------------------------------------------
# spec 解析
# --------------------------------------------------------------------------


@dataclass
class SpecLine:
    section: str
    number: str
    cells: list[int]
    lang: str
    lineno: int


@dataclass
class SpecSection:
    name: str
    lines: list[SpecLine] = field(default_factory=list)


@dataclass
class Spec:
    options: dict
    sections: list[SpecSection]


_SPEC_LINE_RE = re.compile(r"^(\S+)\s*\|\s*([0-9]+(?:\s*/\s*[0-9]+)*)\s*(?:\|\s*([A-Za-z_]+)\s*)?$")


def parse_spec(text: str) -> Spec:
    options = dict(DEFAULT_OPTIONS)
    sections: list[SpecSection] = []
    current: SpecSection | None = None

    for lineno, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            name = line[3:].strip()
            if not name:
                raise WpcError("段名为空", lineno)
            if any(s.name == name for s in sections):
                raise WpcError(f"段名重复：{name}", lineno)
            current = SpecSection(name)
            sections.append(current)
            continue
        if line.startswith("#"):
            continue
        if current is None:
            if ":" not in line:
                raise WpcError("全局键应写成 key: value", lineno)
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().lower()
            if key not in DEFAULT_OPTIONS:
                raise WpcError(f"未知全局键：{key}", lineno)
            options[key] = value
            continue

        m = _SPEC_LINE_RE.match(line)
        if not m:
            raise WpcError(f"句行格式应为 <句号> | <格数> | <语言>：{line}", lineno)
        number, cells_text, lang = m.group(1), m.group(2), m.group(3)
        if any(l.number == number for l in current.lines):
            raise WpcError(f"段 {current.name} 内句号重复：{number}", lineno)
        cells = [int(x.strip()) for x in cells_text.split("/")]
        if not cells:
            raise WpcError("格数不能为空", lineno)
        if lang is None:
            lang = options["lang"]
        if lang not in LANGS:
            raise WpcError(f"未知语言：{lang}", lineno)
        current.lines.append(SpecLine(current.name, number, cells, lang, lineno))

    _validate_options(options)
    if not sections:
        raise WpcError("spec 里没有任何段")
    if not any(s.lines for s in sections):
        raise WpcError("spec 里没有任何句行")
    return Spec(options, sections)


def _validate_options(options: dict) -> None:
    checks = (
        ("lang", LANGS),
        ("latin", LATIN_MODES),
        ("punct", PUNCT_MODES),
        ("digits", DIGITS_MODES),
    )
    for key, allowed in checks:
        if options[key] not in allowed:
            raise WpcError(f"{key} 只能取 {'/'.join(allowed)}，拿到 {options[key]}")


# --------------------------------------------------------------------------
# draft 解析
# --------------------------------------------------------------------------

_DRAFT_HEADER_RE = re.compile(r"^#\s*spec:\s*(\S+)\s+sha256=([0-9a-fA-F]{64})\s*$")
_VERSION_HEAD_RE = re.compile(r"^##\s+(\S+)(?:\s+.*)?$")
_SECTION_RE = re.compile(r"^\[([^\]]+)\]\s*$")
_DRAFT_LINE_RE = re.compile(r"^(\S+?)\s*[|｜]\s*(.*)$")


@dataclass
class DraftVersion:
    label: str
    lineno: int
    sections: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class Draft:
    spec_file: str
    spec_sha256: str
    versions: dict[str, DraftVersion]
    order: list[str]


def parse_draft(text: str) -> Draft:
    lines = text.split("\n")
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        raise WpcError("draft 为空，第一行必须是 # spec: <文件名> sha256=<hex>")
    header = lines[idx].strip()
    m = _DRAFT_HEADER_RE.match(header)
    if not m:
        raise WpcError("第一行必须是 # spec: <文件名> sha256=<64 位 hex>", idx + 1)
    spec_file, spec_sha = m.group(1), m.group(2).lower()

    versions: dict[str, DraftVersion] = {}
    order: list[str] = []
    current: DraftVersion | None = None
    section: str | None = None

    for lineno, raw in enumerate(lines[idx + 1:], idx + 2):
        line = raw.strip()
        if not line:
            continue
        vm = _VERSION_HEAD_RE.match(line)
        if vm:
            label = vm.group(1)
            if label in versions:
                raise WpcError(f"版本标签重复：{label}", lineno)
            current = DraftVersion(label, lineno)
            versions[label] = current
            order.append(label)
            section = None
            continue
        if current is None:
            raise WpcError("版本头 ## <标签> 之前出现了内容", lineno)
        if line.startswith("#"):
            continue
        sm = _SECTION_RE.match(line)
        if sm:
            name = sm.group(1).strip()
            if name in current.sections:
                raise WpcError(f"版本 {current.label} 内段 [{name}] 重复", lineno)
            current.sections[name] = {}
            section = name
            continue
        lm = _DRAFT_LINE_RE.match(line)
        if lm:
            if section is None:
                raise WpcError("句行出现在段标记 [<段名>] 之前", lineno)
            number, body = lm.group(1), lm.group(2)
            if number in current.sections[section]:
                raise WpcError(f"版本 {current.label} 段 [{section}] 内句号重复：{number}", lineno)
            current.sections[section][number] = body
            continue
        raise WpcError(f"无法解析的行：{line}", lineno)

    if not order:
        raise WpcError("draft 里没有任何版本头 ## <标签>")
    return Draft(spec_file, spec_sha, versions, order)


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------


@dataclass
class Report:
    ok: bool
    spec: dict
    version: str | None
    violations: list[dict]
    warnings: list[dict]
    summary: dict
    error: str | None = None
    lines: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        out = {
            "ok": self.ok,
            "spec": self.spec,
            "version": self.version,
            "violations": self.violations,
            "warnings": self.warnings,
            "summary": self.summary,
        }
        if self.error:
            out["error"] = self.error
        return out


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _segments(text: str) -> list[str]:
    return re.split(r"[|｜]", text)


def check(
    spec_text: str,
    draft_text: str,
    version: str | None = None,
    *,
    strict: bool = False,
) -> Report:
    """纯函数：给两份文本，给出结论。不读文件、不写文件、无全局状态。"""
    spec = parse_spec(spec_text)
    draft = parse_draft(draft_text)
    sha = sha256_text(spec_text)
    spec_info = {
        "file": draft.spec_file,
        "sha256": sha,
        "drift": draft.spec_sha256 != sha,
    }

    if spec_info["drift"]:
        return Report(
            ok=False,
            spec=spec_info,
            version=version,
            violations=[],
            warnings=[],
            summary={"lines_checked": 0, "lines_ok": 0, "violations": 0},
            error="spec_drift",
        )

    label = version or draft.order[-1]
    if label not in draft.versions:
        raise WpcError(f"版本不存在：{label}（有 {', '.join(draft.order)}）")
    ver = draft.versions[label]

    spec_names = [s.name for s in spec.sections]
    for name in ver.sections:
        if name not in spec_names:
            raise WpcError(f"版本 {label} 里的段 [{name}] 不在 spec 中")
    for name in spec_names:
        if name not in ver.sections:
            raise WpcError(f"版本 {label} 缺少段 [{name}]")

    spec_by_section = {s.name: s for s in spec.sections}
    for name, lines in ver.sections.items():
        known = {l.number for l in spec_by_section[name].lines}
        for number in lines:
            if number not in known:
                raise WpcError(f"版本 {label} 段 [{name}] 的句号 {number} 不在 spec 中")

    violations: list[dict] = []
    warnings: list[dict] = []
    detail: list[dict] = []
    checked = 0
    ok_lines = 0

    for section in spec.sections:
        draft_lines = ver.sections[section.name]
        for sl in section.lines:
            checked += 1
            lang = sl.lang
            expected = sl.cells
            if sl.number not in draft_lines:
                violations.append({
                    "section": section.name,
                    "line": sl.number,
                    "lang": lang,
                    "kind": KIND_TOO_FEW,
                    "segment": None,
                    "expected": sum(expected),
                    "actual": 0,
                    "cells": [],
                    "text": "",
                })
                detail.append({
                    "section": section.name, "line": sl.number, "lang": lang,
                    "expected": expected, "cells": [], "seg_ok": [],
                    "ok": False, "text": "",
                })
                continue

            raw_text = draft_lines[sl.number]
            segs = _segments(raw_text)
            if len(segs) != len(expected):
                violations.append({
                    "section": section.name,
                    "line": sl.number,
                    "lang": lang,
                    "kind": KIND_SEG_COUNT,
                    "segment": None,
                    "expected": len(expected),
                    "actual": len(segs),
                    "cells": [],
                    "text": raw_text.strip(),
                })
                detail.append({
                    "section": section.name, "line": sl.number, "lang": lang,
                    "expected": expected, "cells": [], "seg_ok": [],
                    "ok": False, "text": raw_text.strip(),
                })
                continue

            all_cells: list[list[str]] = []
            seg_ok: list[bool] = []
            line_ok = True
            estimated = False
            for k, seg in enumerate(segs):
                text = seg.strip()
                cells, warns = count_cells(
                    text,
                    lang,
                    latin=spec.options["latin"],
                    punct=spec.options["punct"],
                    digits=spec.options["digits"],
                )
                all_cells.append(cells)
                for w in warns:
                    entry = {"section": section.name, "line": sl.number, **w}
                    if strict and w["kind"] == KIND_UNCLASSIFIED:
                        violations.append({
                            "section": section.name,
                            "line": sl.number,
                            "lang": lang,
                            "kind": KIND_UNCLASSIFIED,
                            "segment": k + 1,
                            "expected": expected[k],
                            "actual": len(cells),
                            "cells": cells,
                            "text": text,
                        })
                        line_ok = False
                    else:
                        warnings.append(entry)
                if spec.options["latin"] == "syllable" and any(is_latin(ch) for ch in text):
                    estimated = True

                want = expected[k]
                got = len(cells)
                if got == want:
                    seg_ok.append(True)
                    continue
                seg_ok.append(False)
                line_ok = False
                violations.append({
                    "section": section.name,
                    "line": sl.number,
                    "lang": lang,
                    "kind": KIND_TOO_MANY if got > want else KIND_TOO_FEW,
                    "segment": k + 1,
                    "expected": want,
                    "actual": got,
                    "cells": cells,
                    "text": text,
                })

            if estimated:
                warnings.append({"section": section.name, "line": sl.number, "kind": KIND_ESTIMATED})
            if line_ok:
                ok_lines += 1
            detail.append({
                "section": section.name, "line": sl.number, "lang": lang,
                "expected": expected, "cells": all_cells, "seg_ok": seg_ok,
                "ok": line_ok, "text": raw_text.strip(),
            })

    return Report(
        ok=not violations,
        spec=spec_info,
        version=label,
        violations=violations,
        warnings=warnings,
        summary={"lines_checked": checked, "lines_ok": ok_lines, "violations": len(violations)},
        lines=detail,
    )


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------


def format_human(report: Report, *, explain: bool = False) -> str:
    out: list[str] = []
    sha = report.spec.get("sha256", "")
    out.append(f"spec: {report.spec.get('file', '?')} sha256={sha[:12]}… drift={'yes' if report.spec.get('drift') else 'no'}")
    if report.error == "spec_drift":
        out.append("ERROR spec_drift：spec 的 sha256 与 draft 头部记录不符，停止校验。让 agent 回来问人。")
        return "\n".join(out)
    out.append(f"version: {report.version}")
    for item in report.lines:
        status = "OK" if item["ok"] else "FAIL"
        exp = "/".join(str(c) for c in item["expected"])
        out.append(f"[{item['section']}] {item['line']} {item['lang']} {exp} {status}")
        if explain or not item["ok"]:
            if not item["cells"]:
                out.append("    (未填写)")
                continue
            for k, cells in enumerate(item["cells"], 1):
                body = "·".join(cells) if cells else "(空)"
                mark = "" if item["seg_ok"][k - 1] else "  <<"
                out.append(f"    seg{k} {len(cells)}格 {body}{mark}")
    for v in report.violations:
        seg = f"seg{v['segment']}" if v.get("segment") else "-"
        out.append(f"VIOLATION {v['kind']} [{v['section']}] {v['line']} {seg} expected={v['expected']} actual={v['actual']}")
    for w in report.warnings:
        if w["kind"] == KIND_ESTIMATED:
            out.append(f"WARNING estimated [{w['section']}] {w['line']} 音节数为估算")
        else:
            out.append(f"WARNING {w['kind']} [{w['section']}] {w['line']} 字符 {w.get('cell')!r}")
    s = report.summary
    out.append(f"summary: {s['lines_checked']} 句，{s['lines_ok']} 通过，{s['violations']} 处违例")
    return "\n".join(out)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _read_text(path: str) -> str:
    try:
        raw = open(path, "rb").read()
    except OSError as exc:
        raise WpcError(f"读不到 {path}：{exc.strerror}") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise WpcError(f"{path} 不是合法的 UTF-8：{exc}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _cmd_check(args) -> int:
    spec_text = _read_text(args.spec)
    draft_text = _read_text(args.draft)
    draft = parse_draft(draft_text)

    if args.version == "all":
        reports = [check(spec_text, draft_text, label, strict=args.strict) for label in draft.order]
        if args.json:
            payload = {
                "ok": all(r.ok for r in reports),
                "spec": reports[0].spec if reports else {},
                "versions": [
                    {
                        "version": r.version,
                        "ok": r.ok,
                        "violations": r.violations,
                        "warnings": r.warnings,
                        "summary": r.summary,
                    }
                    for r in reports
                ],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("\n\n".join(format_human(r, explain=args.explain) for r in reports))
        if any(r.error == "spec_drift" for r in reports):
            return EXIT_DRIFT
        return EXIT_OK if all(r.ok for r in reports) else EXIT_VIOLATION

    report = check(spec_text, draft_text, args.version, strict=args.strict)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_human(report, explain=args.explain))
    if report.error == "spec_drift":
        return EXIT_DRIFT
    return EXIT_OK if report.ok else EXIT_VIOLATION


def _cmd_list(args) -> int:
    draft = parse_draft(_read_text(args.draft))
    for label in draft.order:
        print(label)
    return EXIT_OK


def _cmd_hash(args) -> int:
    print(sha256_text(_read_text(args.spec)))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wpc.py", description="词格校验器：字数与分句，中文/日语/韩语/英语。")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="校验 draft 的某一版")
    c.add_argument("--spec", required=True)
    c.add_argument("--draft", required=True)
    c.add_argument("--version", default=None, help="版本标签；all 表示查全部")
    c.add_argument("--json", action="store_true")
    c.add_argument("--explain", action="store_true", help="逐格列出每个分句")
    c.add_argument("--strict", action="store_true", help="无法归类的字符升级为违例")
    c.set_defaults(func=_cmd_check)

    l = sub.add_parser("list", help="列出 draft 里的版本标签")
    l.add_argument("--draft", required=True)
    l.set_defaults(func=_cmd_list)

    h = sub.add_parser("hash", help="算 spec 的 sha256，供写 draft 头")
    h.add_argument("--spec", required=True)
    h.set_defaults(func=_cmd_hash)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except WpcError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
