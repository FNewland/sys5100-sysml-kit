"""reqlint command line.

Exit codes: 0 = no finding at or above --fail-on (default: error); 1 = at least one such finding;
2 = usage or input error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

USAGE = """reqlint [options] FILE [FILE ...]
       reqlint --text "The robot shall stop within 1.5 m." [--id REQ-04]
       reqlint --list-rules

FILE: .csv (columns id,text[,rationale,verification]), .md (tables or '- ID: text' lists),
      .sysml (requirement ids + doc text), or .txt (one requirement per line, 'ID: text')."""


def _parser():
    ap = argparse.ArgumentParser(prog="reqlint", usage=USAGE,
                                 description="Requirement wording checker (SYS 5100). Rules inspired by INCOSE GtWR "
                                             "characteristics; paraphrased, no GtWR text reproduced.")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--text", help="lint one requirement string instead of files")
    ap.add_argument("--id", default="R-1", help="id for --text (default R-1)")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--min-severity", choices=["info", "warning", "error"], default="info",
                    help="hide findings below this severity (default info: show all)")
    ap.add_argument("--fail-on", choices=["error", "warning", "never"], default="error",
                    help="exit 1 if any finding at or above this severity (default error)")
    ap.add_argument("--rules", help="comma-separated rule ids to run (default all)")
    ap.add_argument("--ignore", help="comma-separated rule ids to skip")
    ap.add_argument("--glossary", help="file of defined abbreviations, one per line (silences RL-ABBR for them)")
    ap.add_argument("--lang", choices=["en", "fr"], default="en", help="rule titles language (fr = stub)")
    ap.add_argument("--list-rules", action="store_true", help="print the rule catalogue and exit")
    ap.add_argument("--version", action="store_true")
    return ap


def _ids(s):
    return {x.strip().upper() for x in s.split(",") if x.strip()} if s else None


def list_rules(fmt: str, lang: str) -> str:
    from . import RULES, i18n
    if fmt == "json":
        return json.dumps([{"id": r.id, "severity": r.severity, "characteristic": r.characteristic,
                            "family": r.family, "title": i18n.title(r.id, r.title, lang),
                            "explanation": r.explanation, "fix": r.fix} for r in RULES], indent=1,
                          ensure_ascii=False)
    lines = [f"{len(RULES)} rules (severity / characteristic / family):", ""]
    for r in RULES:
        lines.append(f"{r.id:<13} {r.severity:<8} {r.characteristic} / {r.family}: {i18n.title(r.id, r.title, lang)}")
        lines.append(f"{'':<13} {r.explanation}")
        lines.append(f"{'':<13} Fix: {r.fix}")
    return "\n".join(lines)


def render_text(reqs, findings, lang="en") -> str:
    from . import i18n
    by_req: dict[str, list] = {}
    for f in findings:
        by_req.setdefault(f.req_id, []).append(f)
    out = []
    tag = {"error": "ERROR", "warning": "WARN ", "info": "info "}
    for r in reqs:
        fs = by_req.get(r.id, [])
        if not fs:
            continue
        out.append(f"{r.id}  ({r.source})  {r.text[:110]}{'...' if len(r.text) > 110 else ''}")
        seen = set()
        for f in fs:
            key = (f.rule, f.evidence.lower())
            if key in seen:
                continue
            seen.add(key)
            ev = f' "{f.evidence}"' if f.evidence and not f.evidence.startswith("(") else f" {f.evidence}"
            note = f" ({f.note})" if f.note else ""
            out.append(f"  {tag[f.severity]} {f.rule:<12} [{f.characteristic}]{ev}{note}: {f.title}. {f.explanation}")
            out.append(f"  {'':<19}Fix: {f.fix}")
        out.append("")
    c = Counter(f.severity for f in findings)
    out.append(i18n.ui("summary", lang).format(n=len(reqs), f=len(findings), e=c["error"], w=c["warning"],
                                               i=c["info"]))
    if findings:
        top = Counter(f.rule for f in findings).most_common(6)
        out.append("most frequent: " + ", ".join(f"{k} x{v}" for k, v in top))
    out.append(i18n.ui("note", lang))
    return "\n".join(out)


def main(argv=None) -> int:
    from . import (load, lint_requirements, InputError, Requirement, SEVERITY_ORDER, __version__)
    a = _parser().parse_args(argv)
    if a.version:
        print(f"reqlint {__version__}")
        return 0
    if a.list_rules:
        print(list_rules(a.format, a.lang))
        return 0
    reqs = []
    try:
        if a.text:
            reqs.append(Requirement(id=a.id, text=" ".join(a.text.split()), source="<text>"))
        if not a.files and not a.text:
            print(USAGE, file=sys.stderr)
            return 2
        for f in a.files:
            reqs += load(f)
        glossary = None
        if a.glossary:
            glossary = {ln.split()[0] for ln in Path(a.glossary).read_text().splitlines() if ln.strip()
                        and not ln.startswith("#")}
    except (InputError, OSError) as e:
        print(f"reqlint: {e}", file=sys.stderr)
        return 2
    findings = lint_requirements(reqs, _ids(a.rules), _ids(a.ignore), glossary, a.lang)
    shown = [f for f in findings if SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[a.min_severity]]
    if a.format == "json":
        c = Counter(f.severity for f in shown)
        print(json.dumps({"tool": "reqlint", "version": __version__, "requirements": len(reqs),
                          "summary": {"error": c["error"], "warning": c["warning"], "info": c["info"],
                                      "by_rule": dict(Counter(f.rule for f in shown))},
                          "findings": [f.as_dict() for f in shown]}, indent=1, ensure_ascii=False))
    else:
        print(render_text(reqs, shown, a.lang))
    if a.fail_on == "never":
        return 0
    threshold = SEVERITY_ORDER[a.fail_on]
    return 1 if any(SEVERITY_ORDER[f.severity] >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
