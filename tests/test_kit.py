"""sysml-kit tests. Needs Java 21 and the pilot (ext/kernel, or SYSML_KERNEL_DIR).

The parser is slow (~20 s, ~550 MB per JVM), so all fixture models are parsed ONCE in batch mode
(one JVM, library loaded once) and the gate-specific checks run in Python on the cached facts.
A few CLI tests run the real ./kit end to end.
"""
import csv
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import kit_core  # noqa: E402
from kit_checks import run_checks  # noqa: E402
import kit_tables  # noqa: E402

STARTERS = ["robot", "microgrid", "sensornet", "gnssnav", "partner"]
BROKEN = ROOT / "tests" / "broken"


def have_pilot():
    try:
        kit_core.kernel_dir()
        return shutil.which("java") is not None
    except kit_core.KitError:
        return False


needs_pilot = pytest.mark.skipif(not have_pilot(), reason="SysML v2 pilot / Java 21 not available")


def kit(*args, env=None, cwd=ROOT):
    e = dict(os.environ, **(env or {}))
    e.pop("GITHUB_STEP_SUMMARY", None)
    return subprocess.run([str(cwd / "kit"), *args], capture_output=True, text=True, cwd=cwd, env=e)


@pytest.fixture(scope="session")
def parsed():
    files = [ROOT / "starters" / f"{s}.sysml" for s in STARTERS] + \
            [BROKEN / "broken_robot.sysml", BROKEN / "syntax_error.sysml", BROKEN / "cascade.sysml",
             ROOT / "tests" / "fixtures" / "lib_smoke.sysml"]
    res = kit_core.run_parser(files, batch=True)
    return res


def facts_of(parsed, name):
    for k, v in parsed.facts_by_file.items():
        if Path(k).stem == name:
            return v
    raise KeyError(name)


def statuses(rows, status, check=None):
    return [r for r in rows if r.status == status and (check is None or r.check == check)]


# ------------------------------------------------------------- static checks -- #
def strip_comments(src):
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", src, flags=re.S))


@pytest.mark.parametrize("name", STARTERS)
def test_starter_shape(name):
    src = (ROOT / "starters" / f"{name}.sysml").read_text()
    assert len(src.splitlines()) <= 250
    assert "private import SYS5100Lib::*;" in src
    code = strip_comments(src)
    # Blueprint section 9 subset: no calc/analysis, action flows, variability, individuals.
    for kw in ("calc", "analysis", "action", "variation", "variant", "individual", "snapshot", "timeslice",
               "perform", "flow"):
        assert not re.search(rf"\b{kw}\b", code), f"{name}: '{kw}' is outside the SYS 5100 subset"


def test_library_matches_interfaces_doc():
    doc = ROOT.parent.parent / "docs" / "INTERFACES.md"
    if not doc.exists():
        pytest.skip("INTERFACES.md not present (template repo)")
    block = re.search(r"```\n(package SYS5100Lib \{.*?\n\})\n```", doc.read_text(), re.S).group(1)
    lib = strip_comments((ROOT / "lib" / "SYS5100Lib.sysml").read_text())
    norm = lambda s: re.sub(r"\s+", " ", strip_comments(s)).strip()  # noqa: E731
    assert norm(lib) == norm(block)


def test_interface_facts_in_starters():
    robot = (ROOT / "starters" / "robot.sysml").read_text()
    assert "<'REQ-04'>" in robot
    for mode in ("idle", "delivering", "degraded", "recovery", "safeStop"):
        assert re.search(rf"state {mode};", robot)
    mg = (ROOT / "starters" / "microgrid.sysml").read_text()
    assert "capacity = 180 [kW*h]" in mg and 'crId = "CR-004"' in mg
    sn = (ROOT / "starters" / "sensornet.sysml").read_text()
    assert "<'SN-007'>" in sn and "latencyMax : DurationValue = 10 [s]" in sn and "95th percentile" in sn
    gn = (ROOT / "starters" / "gnssnav.sysml").read_text()
    assert "part def GnssReceiver" in gn and "interface rxToNav" in gn and re.search(r"spoof", gn, re.I)
    assert "@RiskLink" in gn
    partner = (ROOT / "starters" / "partner.sysml").read_text()
    assert partner.count("TODO") >= 5


def test_vendored_reqlint_in_sync():
    src = ROOT.parent / "reqlint" / "reqlint"
    if not src.exists():
        pytest.skip("not in the course monorepo")
    dst = ROOT / "tools" / "vendor" / "reqlint" / "reqlint"
    for f in src.glob("*.py"):
        assert (dst / f.name).read_text() == f.read_text(), f"run tools/vendor_reqlint.sh ({f.name} differs)"


# ------------------------------------------------------ batch-parsed checks -- #
@needs_pilot
def test_library_and_smoke_model_parse(parsed):
    f = facts_of(parsed, "lib_smoke")
    assert f["errors"] == 0
    rows = run_checks(f, "G4")
    assert not statuses(rows, "FAIL"), [r for r in rows if r.status == "FAIL"]
    assert statuses(rows, "PASS", "C8")


@needs_pilot
@pytest.mark.parametrize("name", STARTERS)
def test_starter_passes_G2_with_zero_fail(parsed, name):
    f = facts_of(parsed, name)
    assert f["errors"] == 0
    rows = run_checks(f, "G2")
    assert not statuses(rows, "FAIL"), [(r.check, r.item, r.detail) for r in statuses(rows, "FAIL")]
    assert statuses(rows, "PASS", "C1")
    assert statuses(rows, "PASS", "C2") or name == "partner"     # partner: TODO text WARNs


@needs_pilot
def test_starter_warnings_are_only_the_planted_ones(parsed):
    warns = {name: [(r.check, r.item) for r in statuses(run_checks(facts_of(parsed, name), "G2"), "WARN")]
             for name in STARTERS}
    assert warns["robot"] == [] and warns["sensornet"] == [] and warns["gnssnav"] == []
    assert warns["microgrid"] == [("C4", "MG-R07 peakPower on village")]      # growth eats the margin (lesson)
    assert [c for c, _ in warns["partner"]] == ["C2"]                          # TODO text


@needs_pilot
def test_results_carry_basis_labels(parsed):
    rows = run_checks(facts_of(parsed, "robot"), "G2")
    labelled = [r for r in rows if r.check in ("C3", "C4", "C5") and " on " in r.item]
    assert labelled and all(r.basis in ("Calculated", "Estimated", "Assumed", "Predicted") for r in labelled)
    c4 = [r for r in rows if r.check == "C4" and "roll-up 25.5 kg" in r.detail]
    assert c4 and c4[0].basis == "Assumed"
    c5 = [r for r in rows if r.check == "C5"]
    assert "183.6 W*h" in c5[0].detail and "22.5 %" in c5[0].detail


PLANTED = [  # (check, item substring, detail substring) at G4
    ("C2", "payloadCapacity", "no id"),
    ("C2", "REQ-05", "no text"),
    ("C2", "REQ-03", "TODO/TBD"),
    ("C2", "REQ-08", "no satisfy"),
    ("C2", "REQ-09", "no verify"),
    ("C3", "REQ-05", "FALSE"),
    ("C4", "grossMass", "misses or double-counts"),
    ("C5", "REQ-06", "margin -"),
    ("C6", "BadLink", "not a conjugate pair"),
    ("C6", "drive.cmdIn", "dangling"),
    ("C6", "compute.cmdOut", "dangling"),
    ("C7", "RobotModes", "unreachable"),
    ("C8", "rangeTest", "needs an NCR"),
    ("C8", "massInspection", "no @TestVerdict"),
]


@needs_pilot
def test_broken_model_parses_but_every_planted_fault_is_caught(parsed):
    f = facts_of(parsed, "broken_robot")
    assert f["errors"] == 0          # all faults are legal SysML: only the course checks catch them
    fails = statuses(run_checks(f, "G4"), "FAIL")
    missing = [p for p in PLANTED if not any(r.check == p[0] and p[1] in r.item and p[2] in r.detail for r in fails)]
    assert not missing, missing
    assert len({(p[0], p[1]) for p in PLANTED}) >= 8


@needs_pilot
def test_gate_aware_severities(parsed):
    f = facts_of(parsed, "broken_robot")
    g2 = run_checks(f, "G2")
    g3 = run_checks(f, "G3")
    pick = lambda rows, item: [r.status for r in rows if r.check == "C2" and item in r.item][0]  # noqa: E731
    assert pick(g2, "REQ-09") == "WARN" and pick(g3, "REQ-09") == "FAIL"     # verify link
    assert pick(g2, "REQ-08") == "WARN" and pick(g3, "REQ-08") == "FAIL"     # satisfy link
    assert pick(g3, "REQ-03") == "WARN" and pick(run_checks(f, "G4"), "REQ-03") == "FAIL"   # TBD
    assert not statuses(g3, "FAIL", "C8") and statuses(run_checks(f, "G4"), "FAIL", "C8")


@needs_pilot
def test_syntax_errors_reported_with_hint(parsed):
    errs = [i for i in parsed.errors if Path(i.file).name == "syntax_error.sysml"]
    assert errs and "missing ';'" in errs[0].hint()
    assert facts_of(parsed, "syntax_error")["errors"] > 0
    assert run_checks(facts_of(parsed, "syntax_error"), "G2")[0].status == "FAIL"


@needs_pilot
def test_gen_table_columns_and_rows(parsed, tmp_path):
    f = facts_of(parsed, "robot")
    tables = kit_tables.build(f, run_checks(f, "G2"))
    written = kit_tables.write(tables, tmp_path, "test")
    names = {p.name for p in written}
    assert {"requirements.md", "requirements.csv", "trace.md", "trace.csv", "verification.md",
            "verification.csv"} <= names
    rows = list(csv.reader((tmp_path / "requirements.csv").open()))
    assert rows[0] == ["id", "text", "subject", "parent", "satisfied_by", "verified_by", "constraint_status"]
    by_id = {r[0]: r for r in rows[1:]}
    assert by_id["REQ-04.1"][3] == "REQ-04" and by_id["REQ-04.1"][4] == "campusRobot.drive"
    assert by_id["REQ-04"][6].startswith("TRUE [Assumed]")
    trace = list(csv.reader((tmp_path / "trace.csv").open()))
    assert trace[0] == kit_tables.TRACE_COLS
    ver = list(csv.reader((tmp_path / "verification.csv").open()))
    assert ver[0] == ["requirement", "verification", "method", "subject", "verdict", "as_run", "ncr"]
    assert any(r[0] == "REQ-04" and r[2] == "Test" and r[4] == "pending" for r in ver[1:])
    md = (tmp_path / "requirements.md").read_text()
    assert "do not edit by hand" in md and "| REQ-01 |" in md


@needs_pilot
def test_gen_table_changes_and_verdicts(parsed, tmp_path):
    mg = facts_of(parsed, "microgrid")
    t = kit_tables.build(mg, run_checks(mg, "G2"))
    assert ["village.battery", "part", "CR-004", "approved", "CCB-07", ""] in t["changes"][1]
    br = facts_of(parsed, "broken_robot")
    v = kit_tables.build(br, run_checks(br, "G4"))["verification"][1]
    assert any(r[1] == "rangeTest" and r[4] == "fail" and r[5] == "TD-01/run1" for r in v)
    assert any(r[0] == "REQ-09" and r[1] == "OPEN" for r in v)


# ------------------------------------------------------------- CLI end to end -- #
@needs_pilot
def test_cli_check_starter_ok_then_gen_table_reuses_parse(tmp_path):
    r = kit("check", "starters/robot.sysml")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "SUMMARY (gate G2)" in r.stdout and "->  OK" in r.stdout
    assert "[Assumed]" in r.stdout and "reqlint:" in r.stdout
    assert (ROOT / "out" / "check.md").exists()
    g = kit("gen-table", "--out", str(tmp_path), "starters/robot.sysml")
    assert g.returncode == 0 and (tmp_path / "trace.csv").exists()
    assert "unchanged" in g.stdout or "wrote" in g.stdout


@needs_pilot
def test_cli_broken_exits_nonzero_at_G4():
    r = kit("check", "--gate", "G4", "tests/broken/broken_robot.sysml")
    assert r.returncode == 1
    assert "FAILED" in r.stdout and "C7" in r.stdout


@needs_pilot
def test_cli_cascade_shows_first_12_and_says_fix_first():
    r = kit("check", "tests/broken/cascade.sysml")
    assert r.returncode == 1
    assert "Fix the FIRST error first" in r.stdout
    assert " 12. " in r.stdout and " 13. " not in r.stdout and "more not shown" in r.stdout


def test_cli_missing_pilot_is_a_setup_error():
    r = kit("check", "starters/robot.sysml", env={"SYSML_KERNEL_DIR": "/nonexistent"})
    assert r.returncode == 2 and "fetch_pilot.py" in r.stderr


def test_cli_lint_uses_reqlint():
    r = kit("lint", "starters/partner.sysml")
    assert r.returncode == 0 and "RL-TBD" in r.stdout


def test_cli_init(tmp_path):
    repo = tmp_path / "team"
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns("ext", "out", "build", "diagrams", "__pycache__",
                                                              ".pytest_cache"))
    for f in (repo / "model").glob("*.sysml"):
        f.unlink()
    r = kit("init", "gnssnav", cwd=repo)
    assert r.returncode == 0 and (repo / "model" / "gnssnav.sysml").exists()
    r = kit("init", "robot", cwd=repo)
    assert r.returncode == 2 and "--force" in r.stderr
    r = kit("check", cwd=repo, env={"SYSML_KERNEL_DIR": "/nonexistent"})
    assert r.returncode == 2


def test_gate_resolution(monkeypatch, tmp_path):
    import kit as kitcli
    monkeypatch.delenv("KIT_GATE", raising=False)
    assert kitcli.resolve_gate("g3") == "G3"
    monkeypatch.setenv("KIT_GATE", "G4")
    assert kitcli.resolve_gate(None) == "G4"
    monkeypatch.delenv("KIT_GATE")
    assert kitcli.resolve_gate(None) in kitcli.GATES
    with pytest.raises(kit_core.KitError):
        kitcli.resolve_gate("G9")


def test_unit_evaluator():
    from kit_core import evaluate, Scope
    node = {"path": "x", "attributes": [{"name": "m", "value": "2 [kg]", "metadata": []}], "parts": []}
    assert abs(evaluate("m * 3", Scope(node), []) - 6.0) < 1e-12
    assert abs(evaluate("180 [kW*h]", Scope(node), []) - 180 * 3.6e6) < 1e-3
    assert evaluate("m <= 2.5 [kg]", Scope(node), []) is True
    with pytest.raises(ValueError):
        evaluate("3 [furlong]", Scope(node), [])
