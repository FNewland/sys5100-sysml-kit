"""Read requirements from CSV, Markdown (tables or lists), SysML v2 text, or plain text."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Requirement:
    id: str
    text: str
    rationale: str | None = None
    verification: str | None = None
    source: str = ""                       # file:line
    fields_present: dict = field(default_factory=dict)
    id_generated: bool = False


class InputError(Exception):
    pass


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


ID_COLS = ("id", "req id", "req_id", "requirement id", "identifier", "ref")
TEXT_COLS = ("text", "requirement", "requirement text", "statement", "shall statement", "description")
RAT_COLS = ("rationale", "why", "justification")
VER_COLS = ("verification", "verification method", "method", "v&v", "vm")


def _pick(header: list[str], names) -> int | None:
    low = [h.strip().lower() for h in header]
    for n in names:
        if n in low:
            return low.index(n)
    return None


def _from_rows(rows: list[list[str]], src: str, first_line: int) -> list[Requirement]:
    if not rows:
        return []
    header = rows[0]
    it, ii = _pick(header, TEXT_COLS), _pick(header, ID_COLS)
    ir, iv = _pick(header, RAT_COLS), _pick(header, VER_COLS)
    if it is None:
        raise InputError(f"{src}: no 'text' (or 'requirement') column in header {header}")
    out = []
    for n, row in enumerate(rows[1:], start=1):
        if not any(c.strip() for c in row):
            continue
        get = lambda i: row[i] if i is not None and i < len(row) else None  # noqa: E731
        rid = _norm(get(ii))
        out.append(Requirement(
            id=rid or f"row{n}", text=_norm(get(it)), rationale=get(ir), verification=get(iv),
            source=f"{src}:{first_line + n}", id_generated=not rid,
            fields_present={"rationale": ir is not None, "verification": iv is not None}))
    return out


def read_csv(text: str, src: str = "<csv>") -> list[Requirement]:
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    return _from_rows(rows, src, 1)


LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\*\*|__)?\[?([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[\d.]+)\]?(?:\*\*|__)?"
                       r"\s*[:–—-]?\s*(?:\*\*|__)?\s*(.+)$")


def read_markdown(text: str, src: str = "<md>") -> list[Requirement]:
    lines = text.splitlines()
    out: list[Requirement] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}", lines[i + 1]):
            block, start = [], i
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\s*\|?\s*:?-{2,}", lines[i]):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    block.append(cells)
                i += 1
            header = block[0] if block else []
            if _pick(header, TEXT_COLS) is not None:
                out += _from_rows(block, src, start)
            continue
        m = LIST_ITEM.match(line)
        if m and re.search(r"\bshall\b|\bshould\b|\bwill\b|\bmust\b", m.group(2), re.I):
            body = re.sub(r"(\*\*|__)", "", m.group(2))
            rat = None
            rm = re.search(r"\s*(?:\*|_)?Rationale(?:\*|_)?\s*:\s*(.*)$", body, re.I)
            if rm:
                rat, body = rm.group(1), body[:rm.start()]
            out.append(Requirement(id=m.group(1), text=_norm(body), rationale=rat, source=f"{src}:{i + 1}",
                                   fields_present={"rationale": rat is not None}))
        i += 1
    return out


REQ_DECL = re.compile(r"\brequirement\s+(?:def\s+)?(?:<'([^']+)'>\s*)?([A-Za-z_]\w*|'[^']+')?[^;{]*\{", re.S)
DOC = re.compile(r"\bdoc\s*/\*(.*?)\*/", re.S)


def _matching_brace(s: str, open_pos: int) -> int:
    depth = 0
    i = open_pos
    in_comment = False
    while i < len(s):
        if not in_comment and s.startswith("/*", i):
            in_comment, i = True, i + 2
            continue
        if in_comment:
            if s.startswith("*/", i):
                in_comment = False
                i += 2
                continue
            i += 1
            continue
        if s.startswith("//", i):
            j = s.find("\n", i)
            i = len(s) if j < 0 else j
            continue
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(s)


def _clean_doc(body: str) -> str:
    return _norm(re.sub(r"^\s*\*\s?", "", body, flags=re.M))


def read_sysml(text: str, src: str = "<sysml>") -> list[Requirement]:
    """Extract requirement ids and the first doc comment in each requirement body (usage or def)."""
    out = []
    for m in REQ_DECL.finditer(text):
        # skip 'satisfy requirement', 'require constraint', 'frame', etc. handled by the regex anchor
        pre = text[max(0, m.start() - 12):m.start()]
        if re.search(r"(satisfy|verify|#)\s*$", pre):
            continue
        brace = m.end() - 1
        end = _matching_brace(text, brace)
        body = text[brace + 1:end]
        # first doc at nesting depth 1 only
        doc = None
        for d in DOC.finditer(body):
            depth = body[:d.start()].count("{") - body[:d.start()].count("}")
            if depth == 0:
                doc = d
                break
        rid, name = m.group(1), (m.group(2) or "").strip("'")
        if rid is None and doc is None:
            continue                       # e.g. 'requirement def RobotRequirement { subject ... }'
        line = text.count("\n", 0, m.start()) + 1
        txt = _clean_doc(doc.group(1)) if doc else ""
        rat = None
        rm = re.search(r"\bRationale\s*:\s*(.*)$", txt, re.I)
        if rm:
            rat, txt = rm.group(1), txt[:rm.start()].strip()
        out.append(Requirement(id=rid or name, text=txt, rationale=rat, source=f"{src}:{line}",
                               id_generated=rid is None, fields_present={"rationale": rat is not None}))
    return out


def read_text(text: str, src: str = "<text>") -> list[Requirement]:
    out = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[\d.]+)\s*[:\t-]\s*(.+)$", line)
        if m:
            out.append(Requirement(id=m.group(1), text=_norm(m.group(2)), source=f"{src}:{n}"))
        else:
            out.append(Requirement(id=f"L{n}", text=_norm(line), source=f"{src}:{n}", id_generated=True))
    return out


def load(path: str | Path) -> list[Requirement]:
    p = Path(path)
    if not p.exists():
        raise InputError(f"file not found: {p}")
    text = p.read_text(encoding="utf-8-sig")
    suf = p.suffix.lower()
    if suf in (".csv", ".tsv"):
        return read_csv(text, str(p))
    if suf in (".md", ".markdown"):
        return read_markdown(text, str(p))
    if suf in (".sysml", ".kerml"):
        return read_sysml(text, str(p))
    if suf in (".txt", ""):
        return read_text(text, str(p))
    raise InputError(f"{p}: unsupported file type '{suf}' (use .csv, .md, .sysml or .txt)")
