"""kit_tables: generate gate-package tables from the model (never edit them by hand).

  requirements  id, text, subject, parent, satisfied_by, verified_by, constraint_status
  trace         id, concerns, evidence, risk, satisfied_by, allocated_to, verified_by, verdict, change, baseline
  verification  requirement, verification, method, subject, verdict, as_run, ncr
  changes       (only when @ChangeRecord / @Baseline metadata exist) element, kind, cr, status, decided_by, baseline
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from kit_core import meta, short, walk, sat_path
from kit_checks import Row

REQ_COLS = ["id", "text", "subject", "parent", "satisfied_by", "verified_by", "constraint_status"]
TRACE_COLS = ["id", "concerns", "evidence", "risk", "satisfied_by", "allocated_to", "verified_by", "verdict",
              "change", "baseline"]
VER_COLS = ["requirement", "verification", "method", "subject", "verdict", "as_run", "ncr"]
CHG_COLS = ["element", "kind", "cr", "status", "decided_by", "baseline"]

METHODS = [("inspection", "Inspection"), ("analysis", "Analysis"), ("demonstration", "Demonstration"),
           ("demo", "Demonstration"), ("review of design", "Review of design"), ("review", "Review of design"),
           ("test", "Test")]


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^\s*\*\s?", "", t or "", flags=re.M)).strip()


def _method(v: dict) -> str:
    for d in v.get("doc") or []:
        head = _clean(d).split(":")[0].lower()
        for k, name in METHODS:
            if head.startswith(k):
                return name
    names = " ".join(short(t) for t in v["types"]).lower() + " " + v["name"].lower()
    for k, name in METHODS:
        if k in names:
            return name
    return "?"


def _parent(r: dict, by_id: dict) -> str:
    rid = r["id"] or ""
    if "." in rid and rid.rsplit(".", 1)[0] in by_id:
        return rid.rsplit(".", 1)[0]
    m = re.search(r"[Dd]erived from ([A-Z]+-?[A-Z]*-?[\d.]+)", " ".join(r["text"] or []))
    if m and m.group(1).rstrip(".") in by_id:
        return m.group(1).rstrip(".")
    return ""


def build(facts: dict, rows: list[Row]) -> dict[str, tuple[list[str], list[list[str]]]]:
    reqs = facts["requirements"]
    by_id = {r["id"]: r for r in reqs if r["id"]}
    sat, ver = {}, {}
    for s in facts["satisfy"]:
        sat.setdefault(s["requirement"], []).append(sat_path(s["by"], facts["parts"]))
    for v in facts["verify"]:
        ver.setdefault(v["requirement"], []).append(v["by"])
    usages = facts.get("verifications", [])

    def usages_for(def_qname):
        return [u for u in usages if def_qname in u["types"] or u["qname"] == def_qname]

    # constraint status from C3 rows
    c3: dict[str, list[str]] = {}
    for row in rows:
        if row.check == "C3":
            rid = row.item.split(" on ")[0]
            word = "TRUE" if "->  TRUE" in row.detail else "FALSE" if "->  FALSE" in row.detail else \
                "not evaluated" if row.status in ("WARN", "INFO") else ""
            if word:
                c3.setdefault(rid, []).append(word + (f" [{row.basis}]" if row.basis else ""))
        elif row.check in ("C4", "C5") and " on " in row.item:
            rid = row.item.split(" ")[0]
            m = re.search(r"margin (-?[\d.]+ %)", row.detail)
            c3.setdefault(rid, []).append(f"{row.check} {row.status}" + (f" margin {m.group(1)}" if m else "")
                                          + (f" [{row.basis}]" if row.basis else ""))

    allocs = [(a["ends"][0], a["ends"][1]) for a in facts.get("allocations", []) if len(a["ends"]) == 2]

    req_rows, trace_rows, ver_rows = [], [], []
    for r in reqs:
        rid = r["id"] or f"({r['name']})"
        key = r["id"] or r["name"]
        text = _clean(" ".join(r["text"] or []))
        subj = f"{r['subject']} : {', '.join(short(t) for t in r['subjectTypes'])}" if r["subject"] else ""
        sats = sat.get(r["qname"], [])
        vdefs = ver.get(r["qname"], [])
        vnames = []
        for d in vdefs:
            us = usages_for(d)
            vnames += [u["name"] for u in us] or [short(d)]
        cons = "; ".join(c3.get(key, [])) or ("no executable constraint" if not r["constraints"] else "")
        req_rows.append([rid, text, subj, _parent(r, by_id), ", ".join(sats) or "OPEN", ", ".join(vnames) or "OPEN",
                         cons])

        ev = meta(r, "Evidence") or {}
        rl = meta(r, "RiskLink") or {}
        cr = meta(r, "ChangeRecord") or {}
        bl = meta(r, "Baseline") or {}
        targets = [f"{short(a)} -> {short(b)}" for a, b in allocs
                   if short(a) == r["name"] or any(short(b) == s_ for s_ in sats)]
        verdicts = []
        for d in vdefs:
            for u in usages_for(d):
                tv = meta(u, "TestVerdict")
                verdicts.append(f"{u['name']}: {tv.get('verdict') if tv else 'pending'}")
        evid = " ".join(x for x in [ev.get("source") or "", f"({ev['grade']})" if ev.get("grade") else ""] if x)
        trace_rows.append([rid, ", ".join(short(f) for f in r["frames"]), evid,
                           " ".join(x for x in [rl.get("riskId") or "", rl.get("threat") or ""] if x),
                           ", ".join(sats) or "OPEN", ", ".join(targets), ", ".join(vnames) or "OPEN",
                           "; ".join(verdicts) or "-", f"{cr.get('crId', '')} {cr.get('status', '')}".strip(),
                           bl.get("tag", "")])

        if not vdefs:
            ver_rows.append([rid, "OPEN", "", "", "not verified", "", ""])
        for d in vdefs:
            us = usages_for(d)
            if not us:
                ver_rows.append([rid, f"{short(d)} (def only)", _method({"doc": [], "types": [d], "name": ""}),
                                 "", "pending", "", ""])
            for u in us:
                tv = meta(u, "TestVerdict") or {}
                ver_rows.append([rid, u["name"], _method(u), u.get("subject") or "", tv.get("verdict", "pending"),
                                 tv.get("asRun", ""), tv.get("ncr", "")])

    out = {"requirements": (REQ_COLS, req_rows), "trace": (TRACE_COLS, trace_rows),
           "verification": (VER_COLS, ver_rows)}

    chg = []

    def note(elem_name, kind, e):
        cr, bl = meta(e, "ChangeRecord"), meta(e, "Baseline")
        if cr or bl:
            cr = cr or {}
            chg.append([elem_name, kind, cr.get("crId", ""), cr.get("status", ""), cr.get("decidedBy", ""),
                        (bl or {}).get("tag", "")])
    for root in facts["parts"]:
        for n in walk(root):
            note(n["path"], "part", n)
            for a in n["attributes"]:
                note(f"{n['path']}.{a['name']}", "attribute", a)
    for r in reqs:
        note(r["id"] or r["name"], "requirement", r)
    for u in usages:
        note(u["name"], "verification", u)
    if chg:
        out["changes"] = (CHG_COLS, chg)
    out["_allocations"] = (["from", "to"], [[short(a), short(b)] for a, b in allocs])
    return out


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


TITLES = {"requirements": "Requirements table", "trace": "Trace and allocation table",
          "verification": "Verification trace (VCD)", "changes": "Change records and baselines"}


def write(tables: dict, outdir: Path, provenance: str) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    for name in TITLES:                      # drop stale tables (e.g. changes.* after metadata removed)
        if name not in tables:
            for ext in (".md", ".csv"):
                (outdir / f"{name}{ext}").unlink(missing_ok=True)
    written = []
    allocs = tables.get("_allocations", ([], []))[1]
    for name, (cols, rows) in tables.items():
        if name.startswith("_"):
            continue
        csv_path = outdir / f"{name}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        md = [f"# {TITLES[name]}", "", f"_{provenance}. Generated by `./kit gen-table`: do not edit by hand; "
              "fix the model and regenerate._", "",
              "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        md += ["| " + " | ".join(_md_escape(c) for c in row) + " |" for row in rows]
        if name == "trace" and allocs:
            md += ["", "## Allocations (logical to physical)", "", "| from | to |", "|---|---|"]
            md += [f"| {a} | {b} |" for a, b in allocs]
        md_path = outdir / f"{name}.md"
        md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
        written += [md_path, csv_path]
    return written
