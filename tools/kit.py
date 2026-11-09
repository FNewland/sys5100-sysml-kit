#!/usr/bin/env python3
"""sysml-kit: SYS 5100 SysML v2 course kit (check, gen-table, lint, viz, init).

Run it through the ./kit wrapper at the repository root. See README.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kit_core import ROOT, OUT, LIB, GATES, KitError, model_files, run_parser, short, _rel  # noqa: E402
from kit_checks import run_checks, Row, CHECK_TITLES  # noqa: E402
import kit_tables  # noqa: E402

STARTERS = ("robot", "microgrid", "sensornet", "gnssnav", "partner")
MAX_SHOWN = 12

USAGE = """./kit <command> [options]

commands:
  check [--gate G1|G2|G3|G4] [FILE ...]   parse the model and run checks C1-C8 (exit 1 on any FAIL)
  gen-table [--gate G] [--out DIR] [FILE ...]
                                          write requirements, trace and verification tables (Markdown + CSV)
                                          to gates/tables/ for your gate package
  lint [--format text|json] [FILE ...]    run reqlint on the requirement doc text in the model
  viz [--out DIR] [FILE ...]              optional diagrams (SVG) via the pilot implementation
  init STARTER [--force]                  copy a starter model into model/ (robot, microgrid, sensornet,
                                          gnssnav, partner)

FILE defaults to every .sysml file under model/. The course library lib/SYS5100Lib.sysml is always loaded.
Gate: --gate, else $KIT_GATE, else the first line of gates/CURRENT, else G2.
"""


# ----------------------------------------------------------------- helpers -- #
def resolve_gate(arg: str | None) -> str:
    g = arg or os.environ.get("KIT_GATE")
    cur = ROOT / "gates" / "CURRENT"
    if not g and cur.exists():
        lines = cur.read_text().split()
        g = lines[0] if lines else None
    g = (g or "G2").upper()
    if g not in GATES:
        raise KitError(f"unknown gate '{g}': use one of {', '.join(GATES)}")
    return g


def inputs_hash(files) -> str:
    h = hashlib.sha256()
    for f in [LIB, *files]:
        h.update(str(_rel(f)).encode())
        h.update(Path(f).read_bytes())
    h.update((ROOT / "tools" / "SysMLCheck.java").read_bytes())
    return h.hexdigest()


def parse_cached(files):
    """Parse once per unique set of inputs (check and gen-table in CI share the result)."""
    stamp = OUT / "facts.inputs"
    digest = inputs_hash(files)
    facts_path = OUT / "facts.json"
    if stamp.exists() and facts_path.exists() and stamp.read_text() == digest:
        from kit_core import ParseResult
        cached = json.loads((OUT / "parse.json").read_text()) if (OUT / "parse.json").exists() else {}
        from kit_core import Issue
        res = ParseResult(facts=json.loads(facts_path.read_text()),
                          issues=[Issue(**i) for i in cached.get("issues", [])], seconds=0.0)
        return res, True
    res = run_parser(files)
    OUT.mkdir(exist_ok=True)
    (OUT / "parse.json").write_text(json.dumps({"issues": [i.__dict__ for i in res.issues]}))
    if res.facts is not None:
        stamp.write_text(digest)
    return res, False


def print_parse_errors(res, files) -> None:
    errs = res.errors
    nfiles = len({e.file for e in errs})
    print(f"\nC1 FAILED: the SysML v2 parser found {len(errs)} error(s) in {nfiles} file(s).")
    print("Fix the FIRST error first, then re-run ./kit check: later errors are usually knock-on effects of it.\n")
    seen_hints = set()
    for i, e in enumerate(errs[:MAX_SHOWN], 1):
        print(f"{i:>3}. {e.file}:{e.line}:{e.col}  {e.message}")
        h = e.hint()
        kind = h.split(":")[0][:30]
        if i == 1 or kind not in seen_hints:
            print(f"     hint: {h}")
            seen_hints.add(kind)
    if len(errs) > MAX_SHOWN:
        print(f"     ... and {len(errs) - MAX_SHOWN} more not shown (see out/parse.log).")
    lib_errs = [e for e in errs if Path(e.file).name == LIB.name]
    if lib_errs:
        print("\nNote: errors in lib/SYS5100Lib.sysml mean the course library was edited. Restore it with git.")


def table_text(rows: list[Row]) -> str:
    w_item = min(max((len(r.item) for r in rows), default=10), 36)
    out = [f"{'STATUS':<6} {'CHECK':<5} {'ITEM':<{w_item}}  RESULT  [BASIS]", "-" * (w_item + 40)]
    for r in rows:
        item = r.item if len(r.item) <= w_item else r.item[: w_item - 1] + "~"
        basis = f"  [{r.basis}]" if r.basis else ""
        line = f"  (line {r.line})" if r.line and r.status in ("FAIL", "WARN") else ""
        out.append(f"{r.status:<6} {r.check:<5} {item:<{w_item}}  {r.detail}{basis}{line}")
    return "\n".join(out)


def counts(rows):
    return {k: sum(1 for r in rows if r.status == k) for k in ("PASS", "WARN", "FAIL", "INFO", "SKIP")}


def markdown_report(rows: list[Row], gate: str, files) -> str:
    icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "**FAIL**", "INFO": "info", "SKIP": "skip"}
    n = counts(rows)
    md = [f"## SYS 5100 model check (gate {gate})", "",
          f"Files: {', '.join(_rel(f) for f in files)}. "
          f"Result: {n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail, {n['INFO']} info.", "",
          "| Status | Check | Item | Result | Basis |", "|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {icon[r.status]} | {r.check} {CHECK_TITLES.get(r.check, '')} | {r.item.replace('|', '/')} | "
                  f"{r.detail.replace('|', '/')} | {r.basis} |")
    return "\n".join(md) + "\n"


def reqlint_module():
    """Import reqlint: installed package, vendored copy, or the sibling folder in the course monorepo."""
    try:
        import reqlint  # noqa: F401
        return sys.modules["reqlint"]
    except ImportError:
        pass
    for cand in (ROOT / "tools" / "vendor" / "reqlint", ROOT.parent / "reqlint"):
        if (cand / "reqlint" / "__init__.py").exists():
            sys.path.insert(0, str(cand))
            import reqlint  # noqa: F811
            return reqlint
    return None


# ---------------------------------------------------------------- commands -- #
def cmd_check(a) -> int:
    gate = resolve_gate(a.gate)
    files = model_files(a.files)
    if a.each:
        return check_each(files, gate, a)
    print(f"sysml-kit check: gate {gate}; {len(files)} file(s): {', '.join(_rel(f) for f in files)}")
    print("parsing with the SysML v2 pilot implementation (about 20 s) ...", flush=True)
    res, cached = parse_cached(files)
    print("(parse result reused from out/: inputs unchanged)" if cached else f"parsed in {res.seconds:.1f} s")
    (OUT / "parse.log").write_text("\n".join(f"{i.file}:{i.line}:{i.col}: {i.severity}: {i.message}" for i in res.issues))
    if res.errors or res.facts is None:
        print_parse_errors(res, files)
        rows = [Row("FAIL", "C1", "model", f"{len(res.errors)} parser error(s): fix the first one first")]
    else:
        rows = run_checks(res.facts, gate, a.system_margin)
    print()
    print(table_text(rows))
    n = counts(rows)
    footer = []
    rl = reqlint_module()
    if rl is not None and not res.errors:
        try:
            reqs = [r for f in files for r in rl.load(f)]
            findings = rl.lint_requirements(reqs)
            nerr = sum(1 for x in findings if x.severity == "error")
            footer.append(f"reqlint: {len(findings)} wording finding(s) ({nerr} error) in {len(reqs)} requirement(s);"
                          f" run ./kit lint for details (does not affect this check's result)")
        except Exception as e:  # noqa: BLE001
            footer.append(f"reqlint: skipped ({e})")
    print(f"\nSUMMARY (gate {gate}): {n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail, {n['INFO']} info"
          f"  ->  {'FAILED' if n['FAIL'] else 'OK'}")
    for f in footer:
        print(f)
    if gate in ("G1", "G2"):
        print("Gate rule: missing satisfy/verify links WARN until G3; test verdicts (C8) are enforced at G4.")
    elif gate == "G3":
        print("Gate rule: every requirement needs a satisfy and a verify link; C8 verdicts are enforced at G4.")
    OUT.mkdir(exist_ok=True)
    md = markdown_report(rows, gate, files)
    (OUT / "check.md").write_text(md)
    (OUT / "check.json").write_text(json.dumps({"gate": gate, "rows": [r.as_dict() for r in rows], "counts": n},
                                               indent=1))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as fh:
            fh.write(md)
    if a.json:
        print(json.dumps([r.as_dict() for r in rows], indent=1))
    return 1 if n["FAIL"] else 0


def check_each(files, gate, a) -> int:
    """Each file is a separate model (one JVM, library loaded once). For tests and marking."""
    res = run_parser(files, batch=True)
    worst = 0
    summary = {}
    for f in files:
        facts = res.facts_by_file.get(str(f))
        errs = [i for i in res.errors if Path(i.file).name == f.name]
        if facts is None or errs:
            first = f"; first: line {errs[0].line}: {errs[0].message} (hint: {errs[0].hint()})" if errs else ""
            rows = [Row("FAIL", "C1", "model", f"{len(errs)} parser error(s){first}")]
        else:
            rows = run_checks(facts, gate, a.system_margin)
        n = counts(rows)
        summary[_rel(f)] = {"counts": n, "rows": [r.as_dict() for r in rows]}
        print(f"\n=== {_rel(f)} (gate {gate}) ===")
        print(table_text(rows))
        print(f"SUMMARY: {n['PASS']} pass, {n['WARN']} warn, {n['FAIL']} fail, {n['INFO']} info")
        worst = max(worst, 1 if n["FAIL"] else 0)
    OUT.mkdir(exist_ok=True)
    (OUT / "check_each.json").write_text(json.dumps(summary, indent=1))
    return worst


def provenance(files) -> str:
    sha = ""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=ROOT, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return f"Model: {', '.join(_rel(f) for f in files)}" + (f" at commit {sha}" if sha else "")


def cmd_gen_table(a) -> int:
    gate = resolve_gate(a.gate)
    files = model_files(a.files)
    print("sysml-kit gen-table: parsing (about 20 s unless unchanged since the last check) ...", flush=True)
    res, _ = parse_cached(files)
    if res.errors or res.facts is None:
        print_parse_errors(res, files)
        print("\nNo tables written: the model must parse first (C1).")
        return 1
    rows = run_checks(res.facts, gate)
    tables = kit_tables.build(res.facts, rows)
    outdir = Path(a.out) if a.out else ROOT / "gates" / "tables"
    written = kit_tables.write(tables, outdir, provenance(files))
    for p in written:
        print(f"  wrote {_rel(p)}")
    nreq = len(tables["requirements"][1])
    nopen = sum(1 for r in tables["requirements"][1] if "OPEN" in (r[4], r[5]))
    print(f"{nreq} requirement(s); {nopen} with an OPEN satisfy or verify link.")
    return 0


def cmd_lint(a) -> int:
    rl = reqlint_module()
    if rl is None:
        print("reqlint not found. Run: pip install -e tools/vendor/reqlint", file=sys.stderr)
        return 2
    files = model_files(a.files)
    argv = [str(f) for f in files] + ["--format", a.format]
    if a.min_severity:
        argv += ["--min-severity", a.min_severity]
    return rl.cli.main(argv)


def cmd_viz(a) -> int:
    if not shutil.which("dot") and not os.environ.get("GRAPHVIZ_DOT"):
        print("viz: Graphviz 'dot' not found; diagrams skipped (optional). In the Codespace it is installed.")
        return 0
    files = model_files(a.files)
    res, _ = parse_cached(files)
    if res.errors or res.facts is None:
        print("viz: the model does not parse yet; run ./kit check first. Diagrams skipped.")
        return 0
    outdir = Path(a.out) if a.out else ROOT / "diagrams"
    outdir.mkdir(parents=True, exist_ok=True)
    specs = []
    for sd in res.facts["stateDefs"]:
        specs.append(f"{outdir / short(sd['qname'])}.svg={sd['qname']}")
    for p in res.facts["parts"]:
        if p["parts"]:
            specs.append(f"{outdir / p['name']}_tree.svg={p['qname']}")
            if p["types"] and any(n["connections"] for n in [p]):
                specs.append(f"{outdir / short(p['types'][0])}_interconnection.svg={p['types'][0]}@INTERCONNECTION")
    if not specs:
        print("viz: nothing to draw yet (no part trees or state machines).")
        return 0
    print(f"viz: rendering {len(specs)} diagram(s) (about 30 s) ...", flush=True)
    try:
        run_parser(files, viz=specs)
    except KitError as e:
        print(f"viz: skipped ({e})")
        return 0
    made = sorted(outdir.glob("*.svg"))
    for m in made:
        print(f"  {_rel(m)}")
    if not made:
        print("viz: the pilot produced no diagrams (skipped; this is optional).")
    return 0


def cmd_init(a) -> int:
    src = ROOT / "starters" / f"{a.starter}.sysml"
    if not src.exists():
        raise KitError(f"no starter '{a.starter}': choose one of {', '.join(STARTERS)}")
    dest_dir = ROOT / "model"
    dest_dir.mkdir(exist_ok=True)
    existing = list(dest_dir.rglob("*.sysml"))
    if existing and not a.force:
        raise KitError(f"model/ already has {len(existing)} .sysml file(s); use --force to add the starter anyway")
    dest = dest_dir / src.name
    shutil.copy(src, dest)
    print(f"copied {_rel(src)} -> {_rel(dest)}. Rename the package for your team, then run ./kit check")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="kit", usage=USAGE, add_help=True)
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="parse and run checks C1-C8")
    c.add_argument("--gate", choices=GATES, type=str.upper)
    c.add_argument("--system-margin", type=float, default=0.10,
                   help="default system margin for C4 when a requirement declares none (0.10)")
    c.add_argument("--json", action="store_true", help="also print the result rows as JSON")
    c.add_argument("--each", action="store_true", help="treat each file as a separate model (instructor use)")
    c.add_argument("files", nargs="*")
    g = sub.add_parser("gen-table", help="write gate tables (Markdown + CSV)")
    g.add_argument("--gate", choices=GATES, type=str.upper)
    g.add_argument("--out", help="output folder (default gates/tables)")
    g.add_argument("files", nargs="*")
    lt = sub.add_parser("lint", help="reqlint on requirement doc text")
    lt.add_argument("--format", choices=["text", "json"], default="text")
    lt.add_argument("--min-severity", choices=["info", "warning", "error"])
    lt.add_argument("files", nargs="*")
    v = sub.add_parser("viz", help="optional SVG diagrams")
    v.add_argument("--out")
    v.add_argument("files", nargs="*")
    i = sub.add_parser("init", help="copy a starter model into model/")
    i.add_argument("starter", choices=STARTERS)
    i.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        print(USAGE)
        return 2
    try:
        return {"check": cmd_check, "gen-table": cmd_gen_table, "lint": cmd_lint, "viz": cmd_viz,
                "init": cmd_init}[a.cmd](a)
    except KitError as e:
        print(f"kit: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
