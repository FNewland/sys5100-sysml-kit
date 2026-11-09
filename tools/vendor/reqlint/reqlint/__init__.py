"""reqlint: requirement-wording checker for SYS 5100 (Week 4 AI-drafted requirements audit).

    >>> from reqlint import lint_text
    >>> [f.rule for f in lint_text("The robot shall be able to stop quickly.")]
    ['RL-INFIN', 'RL-TIME']

Rules are inspired by the characteristics of well-formed requirements in the INCOSE Guide to
Writing Requirements; explanations are the course's own paraphrase. A clean reqlint run does
not make a requirement necessary, correct, feasible or traced: those need people and evidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict

from .readers import Requirement, InputError, load, read_csv, read_markdown, read_sysml, read_text
from .rules import RULES, RULES_BY_ID, Rule, SEVERITY_ORDER, ERROR, WARNING, INFO
from . import i18n

__version__ = "0.2.0"
__all__ = ["Finding", "Requirement", "InputError", "RULES", "RULES_BY_ID", "Rule", "lint_requirements",
           "lint_text", "load", "read_csv", "read_markdown", "read_sysml", "read_text", "__version__"]


@dataclass
class Finding:
    req_id: str
    rule: str
    severity: str
    characteristic: str
    family: str
    title: str
    explanation: str
    fix: str
    evidence: str
    start: int
    end: int
    source: str
    note: str = ""

    def as_dict(self):
        return asdict(self)


def lint_requirements(reqs: list[Requirement], select: set[str] | None = None, ignore: set[str] | None = None,
                      glossary: set[str] | None = None, lang: str = "en") -> list[Finding]:
    ids = Counter(r.id for r in reqs if r.id and not r.id_generated)
    ctx = {"glossary": glossary or set(), "duplicate_ids": {i for i, n in ids.items() if n > 1}}
    out: list[Finding] = []
    for req in reqs:
        for rule in RULES:
            if select and rule.id not in select:
                continue
            if ignore and rule.id in ignore:
                continue
            if not req.text and rule.id not in ("RL-ID", "RL-SHALL"):
                continue
            for h in rule.check(req, ctx):
                out.append(Finding(
                    req_id=req.id, rule=rule.id, severity=h.severity or rule.severity,
                    characteristic=rule.characteristic, family=rule.family,
                    title=i18n.title(rule.id, rule.title, lang), explanation=rule.explanation, fix=rule.fix,
                    evidence=h.evidence, start=h.start, end=h.end, source=req.source, note=h.note))
    return out


def lint_text(text: str, req_id: str = "R-1", **fields) -> list[Finding]:
    """Lint one requirement string. fields: rationale=..., verification=... (marks those fields present)."""
    req = Requirement(id=req_id, text=" ".join(text.split()), rationale=fields.get("rationale"),
                      verification=fields.get("verification"), source="<text>",
                      fields_present={k: k in fields for k in ("rationale", "verification")})
    return lint_requirements([req])


from . import cli  # noqa: E402,F401  (exposes reqlint.cli.main for sysml-kit)
