"""kit_core: run the SysML v2 pilot parser, read its facts JSON, evaluate expressions.

Shared by `./kit check`, `./kit gen-table` and `./kit viz`. Standard library only (Python >= 3.10).
"""
from __future__ import annotations

import ast
import json
import operator
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the kit / team repository root
LIB = ROOT / "lib" / "SYS5100Lib.sysml"
BUILD = ROOT / "build"
OUT = ROOT / "out"
JAVA_SRC = ROOT / "tools" / "SysMLCheck.java"
DEFAULT_KERNEL = ROOT / "ext" / "kernel" / "pkg" / "share" / "jupyter" / "kernels" / "sysml"
GATES = ("G1", "G2", "G3", "G4")


class KitError(Exception):
    """A setup problem the student can fix (exit code 2)."""


# ------------------------------------------------------------------ setup ---- #
def kernel_dir() -> Path:
    k = Path(os.environ.get("SYSML_KERNEL_DIR", DEFAULT_KERNEL))
    if not k.is_absolute():
        k = ROOT / k
    jars = sorted(k.glob("jupyter-sysml-kernel-*-all.jar")) if k.is_dir() else []
    if not jars or not (k / "sysml.library").is_dir():
        raise KitError(
            f"SysML v2 pilot implementation not found in {k}.\n"
            "  Fetch it once with:  python tools/fetch_pilot.py --dest ext/kernel\n"
            "  (Codespaces does this for you when the container is built.)")
    return k


def java_classpath() -> str:
    k = kernel_dir()
    jar = sorted(k.glob("jupyter-sysml-kernel-*-all.jar"))[-1]
    cls = BUILD / "SysMLCheck.class"
    if not cls.exists() or JAVA_SRC.stat().st_mtime > cls.stat().st_mtime:
        if not shutil.which("javac"):
            raise KitError("javac (Java 21 JDK) not found. Use the Codespace, or install Temurin 21.")
        BUILD.mkdir(exist_ok=True)
        r = subprocess.run(["javac", "-cp", str(jar), "-d", str(BUILD), str(JAVA_SRC)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise KitError("could not compile tools/SysMLCheck.java:\n" + r.stderr)
    return f"{jar}{os.pathsep}{BUILD}"


def model_files(paths: list[str] | None) -> list[Path]:
    if paths:
        files: list[Path] = []
        for p in paths:
            pp = Path(p)
            files += sorted(pp.rglob("*.sysml")) if pp.is_dir() else [pp]
    else:
        files = sorted((ROOT / "model").rglob("*.sysml"))
    files = [f for f in files if f.resolve() != LIB.resolve()]
    if not files:
        raise KitError("no model files found in model/.\n"
                       "  Start from a starter:  ./kit init robot   (or microgrid, sensornet, gnssnav, partner)")
    for f in files:
        if not f.exists():
            raise KitError(f"file not found: {f}")
    return files


# ----------------------------------------------------------------- parser ---- #
ISSUE = re.compile(r"^(?P<file>.+?):(?P<line>-?\d+):(?P<col>-?\d+): (?P<sev>ERROR|WARNING): (?P<msg>.*)$")


@dataclass
class Issue:
    file: str
    line: int
    col: int
    severity: str
    message: str

    def hint(self) -> str:
        return hint_for(self.message)


@dataclass
class ParseResult:
    issues: list[Issue] = field(default_factory=list)
    facts: dict | None = None
    facts_by_file: dict[str, dict] = field(default_factory=dict)
    seconds: float = 0.0
    log: str = ""

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "ERROR"]


def _java_cmd(extra: list[str]) -> list[str]:
    k = kernel_dir()
    mem = os.environ.get("KIT_JAVA_XMX", "1g")
    return ["java", f"-Xmx{mem}", "-cp", java_classpath(), "SysMLCheck",
            "--lib", str(k / "sysml.library"), "--pre", str(LIB)] + extra


def _rel(p: Path | str) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def run_parser(files: list[Path], viz: list[str] | None = None, batch: bool = False) -> ParseResult:
    """Parse files with the pilot. batch=False: one model; batch=True: each file is its own model."""
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    if batch:
        bdir = OUT / "batch"
        bdir.mkdir(exist_ok=True)
        extra = ["--batch", str(bdir)]
    else:
        facts_path = OUT / "facts.json"
        if facts_path.exists():
            facts_path.unlink()
        extra = ["--json", str(facts_path)]
    for v in viz or []:
        extra += ["--viz", v]
    cmd = _java_cmd(extra) + [_rel(f) for f in files]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    res = ParseResult(seconds=time.time() - t0, log=r.stdout + r.stderr)
    for line in r.stdout.splitlines():
        m = ISSUE.match(line)
        if m:
            res.issues.append(Issue(m["file"], int(m["line"]), int(m["col"]), m["sev"], m["msg"]))
    if r.returncode not in (0, 1):
        raise KitError("the SysML v2 parser did not run:\n" + "\n".join(
            l for l in (r.stdout + r.stderr).splitlines() if not l.startswith("Picked up"))[-2000:])
    if batch:
        for f in files:
            p = OUT / "batch" / (f.name[:-6] + ".json")
            if p.exists():
                res.facts_by_file[str(f)] = json.loads(p.read_text())
    else:
        p = OUT / "facts.json"
        res.facts = json.loads(p.read_text()) if p.exists() else None
    return res


# A few SysML v2 keywords students trip over when they use them as names.
KEYWORDS = {"part", "port", "item", "action", "state", "requirement", "constraint", "interface", "connection",
            "flow", "end", "in", "out", "inout", "ref", "attribute", "calc", "case", "analysis", "verification",
            "view", "viewpoint", "rendering", "concern", "stakeholder", "subject", "objective", "verify", "satisfy",
            "allocate", "allocation", "use", "package", "import", "doc", "comment", "metadata", "enum", "occurrence",
            "event", "individual", "snapshot", "timeslice", "then", "first", "accept", "send", "via", "to", "from",
            "if", "else", "while", "loop", "until", "for", "decide", "merge", "fork", "join", "entry", "exit", "do",
            "exhibit", "perform", "include", "assert", "assume", "require", "frame", "expose", "render", "bind",
            "connect", "message", "succession", "transition", "variant", "variation", "abstract", "readonly",
            "derived", "default", "def", "all", "and", "or", "xor", "not", "implies", "true", "false", "null",
            "new", "return", "language", "locale", "dependency", "filter", "alias", "library", "standard",
            "private", "public", "protected", "about", "rep", "member", "featured", "by", "specializes",
            "subsets", "redefines", "references", "conjugates", "defined", "ordered", "nonunique", "hastype",
            "istype", "as", "meta", "after", "at", "when", "terminate", "parallel", "actor"}


STATEMENT_START = {"part", "attribute", "port", "item", "requirement", "interface", "connect", "satisfy", "verify",
                   "state", "transition", "doc", "package", "private", "public", "import", "action", "concern",
                   "verification", "allocate", "bind", "exhibit", "enum", "metadata", "subject", "require",
                   "frame", "stakeholder", "objective", "entry", "then", "in", "out", "end", "comment"}


def hint_for(msg: str) -> str:
    m = msg.lower()
    tok = re.search(r"input '([^']+)'", msg)
    if tok and tok.group(1) in STATEMENT_START:
        return (f"Most likely a missing ';' (or '}}') at the end of the PREVIOUS line: the parser tripped over "
                f"'{tok.group(1)}', which starts the next statement. (If you named something "
                f"'{tok.group(1)}', rename it: it is a keyword.)")
    if tok and tok.group(1) in KEYWORDS:
        return (f"'{tok.group(1)}' is a SysML v2 keyword; you cannot use it as a name. Rename it "
                f"(e.g. '{tok.group(1)}Value') or quote it as '{tok.group(1)}'.")
    if "missing ';'" in m or "expecting ';'" in m:
        return "Add the missing ';' at the end of the previous statement."
    if "missing '}'" in m or "expecting '}'" in m or "missing eof" in m or "extraneous input '}'" in m:
        return "Braces do not balance: check that every '{' has its '}' (count them in the block above)."
    if "mismatched input" in m or "extraneous input" in m or "no viable alternative" in m:
        return "Syntax: usually a missing ';' or '}' on this line or the line before, or a misspelt keyword."
    if "couldn't resolve reference" in m:
        name = re.search(r"reference to \w+ '([^']+)'", msg)
        n = name.group(1) if name else "the name"
        return (f"Name not found: check the spelling and case of {n}, that it is declared, "
                f"and that its package is imported (private import Pkg::*;). Units: use [kg], [m/s], [kW*h].")
    if "conform" in m and "subject" in m:
        return ("Subject type mismatch: a requirement whose subject is the system cannot be satisfied by a "
                "subsystem. Write a derived requirement with the subsystem as subject (or allocate).")
    if "conform" in m or "type" in m and "must" in m:
        return "Type mismatch: check the units and the declared types on both sides."
    if "duplicate" in m or "distinguishable" in m:
        return "Two elements share the same name in one scope; rename one."
    return "Read the message, look at the line it names (and the line before), then re-run."


# -------------------------------------------------------------- evaluator ---- #
# SI factors (to SI base) for the unit symbols the SysML v2 SI library provides.
UNITS = {
    "g": 1e-3, "kg": 1.0, "t": 1e3,
    "nm": 1e-9, "mm": 1e-3, "cm": 1e-2, "m": 1.0, "km": 1e3,
    "s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0,
    "W": 1.0, "kW": 1e3, "J": 1.0, "kJ": 1e3, "MJ": 1e6, "GJ": 1e9,
    "N": 1.0, "mN": 1e-3, "Hz": 1.0, "V": 1.0, "A": 1.0, "C": 1.0, "K": 1.0, "Pa": 1.0,
    "L": 1e-3, "mL": 1e-6, "rad": 1.0, "bit": 1.0, "B": 8.0, "one": 1.0,
}


def unit_factor(u: str) -> float:
    expr = u.replace("^", "**")
    names = set(re.findall(r"[A-Za-z]+", expr))
    unknown = names - UNITS.keys()
    if unknown:
        raise ValueError(f"unit(s) {sorted(unknown)} in [{u}] not known to the kit")
    return float(eval(expr, {"__builtins__": {}}, dict(UNITS)))  # names restricted to UNITS


QTY = re.compile(r"(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\[([^\]]+)\]")
NAME = re.compile(r"(?<![\w.])([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)")
RESERVED = {"and", "or", "not", "true", "false", "sqrt", "abs", "min", "max"}
LITERAL = re.compile(r"^\s*-?[\d.]+(?:[eE][-+]?\d+)?\s*(\[[^\]]+\])?\s*$")

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
        ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt,
        ast.GtE: operator.ge, ast.Eq: operator.eq, ast.NotEq: operator.ne}
_FUNCS = {"sqrt": lambda x: x ** 0.5, "abs": abs, "min": min, "max": max}


def safe_eval(src: str, env: dict):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            return env[n.id]
        if isinstance(n, ast.BinOp):
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            if isinstance(n.op, ast.Not):
                return not ev(n.operand)
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            return all(vals) if isinstance(n.op, ast.And) else any(vals)
        if isinstance(n, ast.Compare):
            left = ev(n.left)
            for op, rhs in zip(n.ops, n.comparators):
                r = ev(rhs)
                if not _OPS[type(op)](left, r):
                    return False
                left = r
            return True
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        raise ValueError(f"the kit cannot evaluate '{type(n).__name__}' expressions")
    return ev(ast.parse(src, mode="eval"))


def meta(element: dict, mtype: str) -> dict | None:
    """Values of the first metadata annotation of the given type, quotes and enum prefixes stripped."""
    for m in element.get("metadata") or []:
        if m.get("type") == mtype:
            out = {}
            for k, v in (m.get("values") or {}).items():
                if v is None:
                    out[k] = None
                    continue
                v = v.strip()
                if v.startswith('"') and v.endswith('"'):
                    v = v[1:-1]
                elif "::" in v:
                    v = v.split("::")[-1]
                out[k] = v
            return out
    return None


def basis_of(attr: dict) -> str | None:
    """Evidence grade of a value: @Evidence.grade, else @Budget.basis."""
    ev = meta(attr, "Evidence")
    if ev and ev.get("grade"):
        return ev["grade"]
    b = meta(attr, "Budget")
    if b and b.get("basis"):
        return b["basis"]
    return attr.get("evidence")


def growth_of(attr: dict) -> float:
    b = meta(attr, "Budget")
    try:
        return float(b["growth"]) if b and b.get("growth") is not None else 0.0
    except ValueError:
        return 0.0


class Scope:
    """Resolves dotted names against the part tree extracted by the pilot.

    extra: requirement attributes {name: value_text}; subject: (name, node) so 'robot.x' -> satisfier.x.
    """

    def __init__(self, node: dict, extra: dict | None = None, subject: tuple[str, dict] | None = None,
                 roots: list | None = None):
        self.node, self.extra, self.subject, self.roots = node, extra or {}, subject, roots or []

    def child(self, node: dict) -> "Scope":
        return Scope(node, None, None, self.roots)

    def lookup(self, path: str, grades: list, depth: int = 0):
        if depth > 25:
            raise ValueError("circular attribute definitions")
        segs = path.split(".")
        if segs[0] in self.extra and len(segs) == 1:
            grades.append((path, "specified"))
            return evaluate(self.extra[segs[0]], self, grades, depth + 1)
        node = self.node
        if self.subject and segs[0] == self.subject[0]:
            node, segs = self.subject[1], segs[1:]
            if not segs:
                raise LookupError(f"'{path}' is a part, not a value")
        elif not _has(node, segs[0]):
            root = next((r for r in self.roots if r["name"] == segs[0]), None)
            if root is not None:
                node, segs = root, segs[1:]
        for i, s in enumerate(segs):
            attr = next((a for a in node["attributes"] if a["name"] == s), None)
            if attr is not None and i == len(segs) - 1:
                if attr["value"] is None:
                    raise LookupError(f"{node['path']}.{s} has no value yet")
                if LITERAL.match(attr["value"]):
                    grades.append((f"{node['path']}.{s}", basis_of(attr)))
                return evaluate(attr["value"], self.child(node), grades, depth + 1)
            child = next((p for p in node["parts"] if p["name"] == s), None)
            if child is None:
                raise LookupError(f"cannot find '{s}' in {node['path']}")
            node = child
        raise LookupError(f"'{path}' is a part, not a value")


def _has(node: dict, name: str) -> bool:
    return any(a["name"] == name for a in node["attributes"]) or any(p["name"] == name for p in node["parts"])


def evaluate(expr: str, scope: Scope, grades: list, depth: int = 0):
    expr = expr.replace("RealFunctions::", "").replace("NumericalFunctions::", "")
    env: dict = {}

    def qty(m):
        key = f"U_{len(env)}"
        env[key] = unit_factor(m.group(2))
        return f"({m.group(1)}*{key})"
    src = QTY.sub(qty, expr)

    def repl(m):
        name = m.group(1)
        if name in RESERVED or name.startswith("U_"):
            return name
        key = "v_" + name.replace(".", "__")
        env[key] = scope.lookup(name, grades, depth)
        return key
    src = NAME.sub(repl, src)
    src = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", src))
    return safe_eval(src, env)


GRADE_ORDER = ["specified", "measured", "calculated", "predicted", "estimated", "assumed", None]
LABEL = {"specified": "Calculated", "measured": "Calculated", "calculated": "Calculated",
         "predicted": "Predicted", "estimated": "Estimated", "assumed": "Assumed", None: "Assumed"}


def label(grades: list) -> tuple[str, list]:
    """Weakest-input label for a computed result, and the weakest inputs (by path)."""
    if not grades:
        return "Calculated", []
    worst = max((g for _, g in grades), key=lambda g: GRADE_ORDER.index(g) if g in GRADE_ORDER else 6)
    lab = LABEL.get(worst, "Assumed")
    if lab == "Calculated":
        return lab, []
    weak = sorted({p for p, g in grades if GRADE_ORDER.index(g if g in GRADE_ORDER else None)
                   >= GRADE_ORDER.index("predicted")})
    if worst is None:
        lab = "Assumed (ungraded input)"
    return lab, weak


def walk(node, out=None):
    out = [] if out is None else out
    out.append(node)
    for k in node["parts"]:
        walk(k, out)
    return out


def find_node(roots, path):
    if path is None:
        return None
    tail = path.split("::")[-1]
    for r in roots:
        for n in walk(r):
            if n["path"] in (path, tail) or n["qname"] == path:
                return n
    return None


def sat_path(by, roots):
    """Satisfier as a dotted part path (campusRobot.drive) rather than a qualified name."""
    n = find_node(roots, by)
    return n["path"] if n else short(by)


def short(q):
    return q.split("::")[-1] if q else q


def fmt(x: float) -> str:
    if x == 0:
        return "0"
    a = abs(x)
    if a >= 1000 or a < 0.01:
        return f"{x:.3g}"
    return f"{x:.4g}"
