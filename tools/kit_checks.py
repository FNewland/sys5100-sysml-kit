"""kit_checks: the SYS 5100 model checks C1-C8 (Blueprint section 8.1, docs/INTERFACES.md).

Input: the facts JSON written by SysMLCheck.java (names and links resolved by the OMG SysML v2
Pilot Implementation, plus metadata values). Output: a list of Row results, gate-aware.

  C1 parse         zero syntax/semantic errors from the pilot validator
  C2 requirements  id, text, >=1 satisfy, >=1 verify, upward evidence trace
  C3 constraints   every executable requirement constraint is TRUE on each satisfier
  C4 budgets       independent roll-up of a budgeted attribute vs its <name>Max limit, growth + margin policy
  C5 balance       supply vs demand (requirement attributes supply/demand/marginMin)
  C6 interfaces    no dangling ports; interface ends conjugate
  C7 states        every state reachable from the initial state; no dead ends
  C8 verdicts      every verification usage carries @TestVerdict (enforced at G4)
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, asdict

from kit_core import (sat_path, Scope, evaluate, label, walk, find_node, short, fmt, meta, basis_of, growth_of,
                      unit_factor, QTY)

CHECK_TITLES = {
    "C1": "parse", "C2": "requirements & trace", "C3": "constraints", "C4": "budgets",
    "C5": "resource balance", "C6": "interfaces", "C7": "states", "C8": "test verdicts",
}
EVIDENCE_ID = re.compile(r"\b(INT|OBS|DOC|HYP)-\d+\b")
TODO = re.compile(r"\b(TODO|TBD|TBC)\b")


@dataclass
class Row:
    status: str          # PASS WARN FAIL INFO SKIP
    check: str           # C1..C8
    item: str            # what was checked (requirement id, part path, ...)
    detail: str          # the result in plain words
    basis: str = ""      # Calculated / Estimated / Assumed / Predicted (for computed results)
    line: int | None = None

    def as_dict(self):
        return asdict(self)


def gate_num(gate: str) -> int:
    return int(gate[1])


def sev(gate: str, fail_from: str) -> str:
    """FAIL at or after gate `fail_from`, WARN before it."""
    return "FAIL" if gate_num(gate) >= gate_num(fail_from) else "WARN"


def display(value: float, unit_text: str | None) -> str:
    if unit_text:
        try:
            return f"{fmt(value / unit_factor(unit_text))} {unit_text}"
        except ValueError:
            pass
    return fmt(value)


def first_unit(*texts: str | None) -> str | None:
    for t in texts:
        if t:
            m = QTY.search(t)
            if m:
                return m.group(2)
    return None


def run_checks(facts: dict, gate: str = "G2", system_margin: float = 0.10) -> list[Row]:
    rows: list[Row] = []
    add = lambda *a, **k: rows.append(Row(*a, **k))  # noqa: E731

    # C1 ------------------------------------------------------------------ #
    if facts.get("errors"):
        add("FAIL", "C1", "model", f"{facts['errors']} error(s) from the SysML v2 validator: fix these first")
        add("SKIP", "C2", "-", "C2-C8 not run until the model parses (C1)")
        return rows
    add("PASS", "C1", "model", f"0 errors, {facts.get('warnings', 0)} warning(s) (OMG SysML v2 Pilot Implementation)")

    reqs = facts["requirements"]
    roots = facts["parts"]
    sat: dict[str, list[str]] = {}
    for s in facts["satisfy"]:
        sat.setdefault(s["requirement"], []).append(s["by"])
    ver: dict[str, list[str]] = {}
    for v in facts["verify"]:
        ver.setdefault(v["requirement"], []).append(v["by"])

    # C2 ------------------------------------------------------------------ #
    if not reqs:
        add("WARN", "C2", "model", "no requirements yet (write requirement <'ID-01'> name { doc /* ... shall ... */ })")
    ids = {r["id"] for r in reqs if r["id"]}
    for r in reqs:
        rid = r["id"] or "(no id)"
        item = f"{rid} {r['name']}"
        text = " ".join(r["text"] or [])
        fails, warns, infos = [], [], []
        if not r["id"]:
            fails.append("no id: declare it as requirement <'REQ-nn'> name")
        if not text.strip():
            fails.append("no text: add doc /* The <subject> shall ... */")
        if r["qname"] not in sat:
            (fails if sev(gate, "G3") == "FAIL" else warns).append("no satisfy link (open item)")
        if r["qname"] not in ver:
            (fails if sev(gate, "G3") == "FAIL" else warns).append("no verify link (open item)")
        if TODO.search(text):
            (fails if sev(gate, "G4") == "FAIL" else warns).append("text still contains TODO/TBD")
        ev = meta(r, "Evidence")
        src = (ev or {}).get("source") or ""
        derived = ("." in (r["id"] or "") and r["id"].rsplit(".", 1)[0] in ids) or "erived from" in text
        if not EVIDENCE_ID.search(src) and not r["frames"] and not derived:
            warns.append("no upward trace: add @Evidence { source = \"INT-nn\"; } or frame a concern")
        elif src.startswith("HYP-"):
            (warns if gate_num(gate) >= 3 else infos).append(f"rests on hypothesis {src}: validate it with people")
        if fails:
            add("FAIL", "C2", item, "; ".join(fails + warns), line=r["line"])
        elif warns:
            add("WARN", "C2", item, "; ".join(warns), line=r["line"])
        else:
            by = ", ".join(sat_path(b, roots) for b in sat[r["qname"]])
            vb = ", ".join(short(b) for b in ver[r["qname"]])
            add("PASS", "C2", item, f"satisfied by {by}; verified by {vb}" + (f"; {infos[0]}" if infos else ""),
                line=r["line"])

    # C3 ------------------------------------------------------------------ #
    for r in reqs:
        rid = r["id"] or r["name"]
        cons = [c for c in r["constraints"] if "allTrue(assumptions())" not in c]
        if not cons:
            continue
        sats = sat.get(r["qname"], [])
        if not sats:
            add("INFO", "C3", rid, "constraint not evaluated: nothing satisfies this requirement yet", line=r["line"])
        extra = {a["name"]: a["value"] for a in r["attributes"] if a["value"]}
        for by in sats:
            node = find_node(roots, by)
            if node is None:
                add("WARN", "C3", rid, f"satisfier {by} is not a part usage the kit can evaluate", line=r["line"])
                continue
            for c in cons:
                grades: list = []
                try:
                    ok = evaluate(c, Scope(node, extra, (r["subject"], node), roots), grades)
                    lab, weak = label(grades)
                    add("PASS" if ok else "FAIL", "C3", f"{rid} on {node['path']}",
                        f"{c}  ->  {'TRUE' if ok else 'FALSE'}" + (f"  (weakest: {', '.join(weak[:4])})" if weak else ""),
                        lab, r["line"])
                except Exception as e:  # noqa: BLE001
                    add("WARN", "C3", f"{rid} on {node['path']}", f"cannot evaluate '{c}': {e}", line=r["line"])

    # C4 budgets ------------------------------------------------------------ #
    for r in reqs:
        limits = [a for a in r["attributes"] if a["name"].endswith("Max") and a["value"]]
        for lim in limits:
            q = lim["name"][:-3]
            rid = r["id"] or r["name"]
            extra = {a["name"]: a["value"] for a in r["attributes"] if a["value"]}
            sm = system_margin
            if "systemMargin" in extra:
                try:
                    sm = float(evaluate(extra["systemMargin"], Scope({"attributes": [], "parts": [], "path": ""}), []))
                except Exception:  # noqa: BLE001
                    pass
            for by in sat.get(r["qname"], []):
                node = find_node(roots, by)
                if node is None:
                    continue
                try:
                    _budget(rows, r, rid, q, lim, node, extra, sm, roots)
                except Exception as e:  # noqa: BLE001
                    add("WARN", "C4", f"{rid} {q}", f"roll-up failed: {e}", line=r["line"])

    # C5 balance ------------------------------------------------------------ #
    for r in reqs:
        attrs = {a["name"]: a["value"] for a in r["attributes"] if a["value"]}
        if "supply" not in attrs or "demand" not in attrs:
            continue
        rid = r["id"] or r["name"]
        for by in sat.get(r["qname"], []):
            node = find_node(roots, by)
            if node is None:
                continue
            try:
                g: list = []
                sc = Scope(node, attrs, (r["subject"], node), roots)
                sup = evaluate(attrs["supply"], sc, g)
                dem = evaluate(attrs["demand"], sc, g)
                floor = float(evaluate(attrs["marginMin"], sc, [])) if "marginMin" in attrs else 0.0
                g = [x for x in g if x[0] not in ("supply", "demand", "marginMin")]
                margin = (sup - dem) / dem
                lab, weak = label(g)
                u = first_unit(attrs["supply"], attrs["demand"])
                if u is None:
                    u = _unit_of_paths(attrs["supply"], sc)
                add("PASS" if margin >= floor else "FAIL", "C5", f"{rid} on {node['path']}",
                    f"supply {display(sup, u)} vs demand {display(dem, u)}: margin {margin*100:.1f} % "
                    f"(floor {floor*100:.0f} %)" + (f"  (weakest: {', '.join(weak[:4])})" if weak else ""),
                    lab, r["line"])
            except Exception as e:  # noqa: BLE001
                add("WARN", "C5", rid, f"balance not evaluated: {e}", line=r["line"])

    # C6 interfaces ---------------------------------------------------------- #
    for d in facts.get("interfaceDefs", []):
        ends = d["ends"]
        if len(ends) == 2:
            conj = ["~" in (e.get("text") or "") for e in ends]
            if conj[0] == conj[1]:
                add("FAIL", "C6", short(d["qname"]),
                    "interface def ends are not a conjugate pair: type one end with ~PortDef", line=d.get("line"))
    for root in roots:
        nodes = walk(root)
        ports = {p["path"]: p for n in nodes for p in n["ports"]}
        if not ports:
            continue
        ends = set()
        for n in nodes:
            for c in n["connections"]:
                for e in c["ends"]:
                    e = e.split("::")[-1] if e and "::" in e else e
                    ends.add(f"{n['path']}.{e}")
        nfail = 0
        for n in nodes:
            for p in n["ports"]:
                if p["path"] in ends:
                    continue
                if n is root:
                    add("WARN", "C6", p["path"], "boundary port is not bound to any internal port")
                else:
                    nfail += 1
                    add("FAIL", "C6", p["path"], f"dangling port ({', '.join(short(t) for t in p['types'])}): "
                                                 "no interface, connection or binding uses it")
        for n in nodes:
            for c in n["connections"]:
                if c["kind"] != "InterfaceUsage":
                    continue
                ps = [ports.get(f"{n['path']}.{e}") for e in c["ends"]]
                if len(ps) != 2 or None in ps:
                    continue
                t = [short(p["types"][0]) if p["types"] else "?" for p in ps]
                conj = ["~" in x for x in t]
                base = [x.strip("'~") for x in t]
                if base[0] != base[1] or conj[0] == conj[1]:
                    nfail += 1
                    add("FAIL", "C6", f"{n['path']}.{c['name'] or 'interface'}",
                        f"{c['ends'][0]} ({t[0]}) to {c['ends'][1]} ({t[1]}) is not a conjugate pair")
        if not nfail:
            ncon = sum(len(n["connections"]) for n in nodes)
            add("PASS", "C6", root["path"], f"{len(ports)} ports, {ncon} connectors; no dangling ports; ends conjugate")

    # C7 states -------------------------------------------------------------- #
    for sd in facts["stateDefs"]:
        trans = sd["transitions"]
        init = [t["target"] for t in trans if t["source"] == "entry"]
        name = short(sd["qname"])
        if not init:
            add("FAIL", "C7", name, "no initial state: add 'entry; then <state>;'", line=sd.get("line"))
            continue
        seen, todo = set(init), deque(init)
        while todo:
            s = todo.popleft()
            for t in trans:
                if t["source"] == s and t["target"] not in seen:
                    seen.add(t["target"])
                    todo.append(t["target"])
        unreachable = [s for s in sd["states"] if s not in seen]
        dead = [s for s in sd["states"] if not any(t["source"] == s for t in trans)]
        if unreachable:
            add("FAIL", "C7", name, f"unreachable from '{init[0]}': {', '.join(unreachable)}", line=sd.get("line"))
        if dead:
            add("WARN", "C7", name, f"no way out of: {', '.join(dead)}", line=sd.get("line"))
        if not unreachable and not dead:
            add("PASS", "C7", name, f"{len(sd['states'])} states reachable from '{init[0]}'; "
                                    f"{len([t for t in trans if t['source'] != 'entry'])} transitions; no dead ends")

    # C8 verdicts ------------------------------------------------------------ #
    g4 = gate_num(gate) >= 4
    usages = facts.get("verifications", [])
    typed = {t for v in usages for t in v["types"]}
    vdefs = sorted({v["by"] for v in facts["verify"] if v["by"]})
    for d in vdefs:
        if d not in typed and not any(u["qname"] == d for u in usages):
            add("FAIL" if g4 else "INFO", "C8", short(d),
                "no verification usage applies this def yet: add verification x : "
                f"{short(d)} {{ subject :>> ... = <part>; @TestVerdict {{ ... }} }}")
    for v in usages:
        tv = meta(v, "TestVerdict")
        if tv is None:
            add("FAIL" if g4 else "INFO", "C8", v["name"],
                "no @TestVerdict yet" + ("" if g4 else " (required at G4, after Test Day)"), line=v["line"])
            continue
        verdict = (tv.get("verdict") or "").lower()
        ncr = (tv.get("ncr") or "").strip()
        asrun = (tv.get("asRun") or "").strip()
        msg = f"verdict {verdict or '?'}; as-run {asrun or '-'}; NCR {ncr or '-'}"
        if verdict not in ("pass", "fail", "inconclusive", "error"):
            add("FAIL", "C8", v["name"], f"verdict must be VerdictKind::pass|fail|inconclusive|error ({msg})", line=v["line"])
        elif not asrun:
            add("FAIL" if g4 else "WARN", "C8", v["name"], f"no as-run reference ({msg})", line=v["line"])
        elif verdict == "fail" and (not ncr or ncr.lower() == "none"):
            add("FAIL" if g4 else "WARN", "C8", v["name"], f"a failed verdict needs an NCR id ({msg})", line=v["line"])
        elif verdict in ("inconclusive", "error"):
            add("WARN", "C8", v["name"], msg, line=v["line"])
        else:
            add("PASS", "C8", v["name"], msg, line=v["line"])
    if not usages and not vdefs:
        add("FAIL" if g4 else "INFO", "C8", "model", "no verification cases yet")
    return rows


def _unit_of_paths(expr: str, sc: Scope) -> str | None:
    """Find a display unit by looking at the literal value of the first referenced attribute."""
    from kit_core import NAME
    for m in NAME.finditer(expr):
        try:
            node = sc.subject[1] if sc.subject else sc.node
            segs = m.group(1).split(".")
            if sc.subject and segs[0] == sc.subject[0]:
                segs = segs[1:]
            for s in segs[:-1]:
                node = next(p for p in node["parts"] if p["name"] == s)
            a = next(a for a in node["attributes"] if a["name"] == segs[-1])
            u = first_unit(a["value"])
            if u:
                return u
        except (StopIteration, IndexError, TypeError):
            continue
    return None


def _budget(rows, r, rid, q, lim, node, extra, sm, roots):
    """C4: independent roll-up of attribute q over the satisfier's part tree."""
    Q = q[0].upper() + q[1:]
    contrib, missing, grades = [], [], []
    unit = None
    for n in walk(node)[1:]:
        a = next((x for x in n["attributes"] if x["name"] == q), None)
        if a is None:
            continue
        if a["value"] is None:
            missing.append(n["path"])
            continue
        g: list = []
        v = evaluate(a["value"], Scope(n, roots=roots), g)
        grades.append((f"{n['path']}.{q}", basis_of(a)))
        contrib.append((n["path"], v, growth_of(a)))
        unit = unit or first_unit(a["value"])
    for a in node["attributes"]:     # system-level contributions, e.g. payloadMass (literal values only)
        if a["name"].endswith(Q) and a["value"] and QTY.fullmatch(a["value"].strip()):
            v = evaluate(a["value"], Scope(node, roots=roots), [])
            grades.append((f"{node['path']}.{a['name']}", basis_of(a)))
            contrib.append((f"{node['path']}.{a['name']}", v, growth_of(a)))
    if missing:
        rows.append(Row("FAIL", "C4", f"{rid} {q}", f"no {q} value on {', '.join(missing)}", line=r["line"]))
    if not contrib:
        rows.append(Row("WARN", "C4", f"{rid} {q}", f"no part under {node['path']} declares a {q} value", line=r["line"]))
        return
    cbe = sum(v for _, v, _ in contrib)
    alloc = sum(v * (1 + g) for _, v, g in contrib)
    policy = alloc * (1 + sm)
    limit = evaluate(lim["value"], Scope(node, extra, (r["subject"], node), roots), [])
    unit = first_unit(lim["value"]) or unit
    lab, weak = label(grades)
    margin = (limit - alloc) / limit if limit else float("nan")
    status = "FAIL" if cbe > limit else ("WARN" if policy > limit else "PASS")
    note = {"FAIL": "  over the limit", "WARN": "  margin policy not met", "PASS": ""}[status]
    rows.append(Row(status, "C4", f"{rid} {q} on {node['path']}",
                    f"roll-up {display(cbe, unit)} ({len(contrib)} items; with growth {display(alloc, unit)}; "
                    f"+{sm*100:.0f} % system margin {display(policy, unit)}) vs limit {display(limit, unit)}; "
                    f"margin {margin*100:.1f} %{note}" + (f"  (weakest: {', '.join(weak[:3])}{' ...' if len(weak) > 3 else ''})" if weak else ""),
                    lab, r["line"]))
    # Consistency: does the model's own roll-up expression (e.g. grossMass) agree with the part tree?
    for a in node["attributes"]:
        if not a["value"] or QTY.fullmatch(a["value"].strip()):
            continue
        refs = re.findall(rf"\b[\w.]*\.{q}\b", a["value"])
        if len(refs) < 2:
            continue
        expr_val = evaluate(a["value"], Scope(node, roots=roots), [])
        if abs(expr_val - cbe) > 1e-9 * max(1.0, abs(cbe)):
            rows.append(Row("FAIL", "C4", f"{node['path']}.{a['name']}",
                            f"model expression gives {display(expr_val, unit)} but the parts sum to "
                            f"{display(cbe, unit)}: the roll-up expression misses or double-counts a part",
                            line=a.get("line")))
        else:
            rows.append(Row("PASS", "C4", f"{node['path']}.{a['name']}",
                            f"model roll-up expression agrees with the part tree ({display(expr_val, unit)})",
                            line=a.get("line")))
