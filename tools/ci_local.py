#!/usr/bin/env python3
"""Run the `run:` steps of .github/workflows/model-ci.yml locally, in order (maintainer tool).

usage: python tools/ci_local.py [REPO_DIR]      (needs PyYAML; Java 21 and Python on PATH)

`uses:` steps are skipped (checkout/setup/cache), except upload-artifact, whose paths are
checked for existence. Simple `if:` expressions on step outputs are honoured.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

repo = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent).resolve()
wf = yaml.safe_load((repo / ".github" / "workflows" / "model-ci.yml").read_text())
job = next(iter(wf["jobs"].values()))
env = dict(os.environ)
env.update({k: str(v) for k, v in (wf.get("env") or {}).items() if "${{" not in str(v)})
outputs: dict[str, dict] = {}
summary = Path(tempfile.mkstemp(suffix=".md")[1])
env["GITHUB_STEP_SUMMARY"] = str(summary)
failed = False


def condition(expr: str | None) -> bool:
    if not expr:
        return not failed
    e = expr.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    e = re.sub(r"steps\.(\w+)\.outputs\.(\w+)", lambda m: repr(outputs.get(m[1], {}).get(m[2], "")), e)
    return bool(eval(e, {"__builtins__": {}}, {"True": True}))   # trusted local file


for step in job["steps"]:
    name = step.get("name") or step.get("uses")
    if "uses" in step:
        if step["uses"].startswith("actions/upload-artifact") and condition(step.get("if")):
            paths = [p for p in step["with"]["path"].split("\n") if p.strip()]
            missing = [p for p in paths if not (repo / p.strip()).exists()]
            print(f"[artifact] {name}: {len(paths) - len(missing)}/{len(paths)} paths present"
                  + (f"; missing {missing}" if missing else ""))
        else:
            print(f"[skip]     {name}")
        continue
    if not condition(step.get("if")):
        print(f"[skip-if]  {name}")
        continue
    out_file = Path(tempfile.mkstemp()[1])
    env["GITHUB_OUTPUT"] = str(out_file)
    t0 = time.time()
    r = subprocess.run(["bash", "-eo", "pipefail", "-c", step["run"]], cwd=repo, env=env,
                       capture_output=True, text=True)
    dt = time.time() - t0
    if step.get("id"):
        outputs[step["id"]] = dict(l.split("=", 1) for l in out_file.read_text().splitlines() if "=" in l)
    ok = r.returncode == 0 or step.get("continue-on-error")
    print(f"[{'ok' if r.returncode == 0 else 'FAIL' if not ok else 'fail-ok'}]{' ' * 6}{name} ({dt:.1f} s, exit {r.returncode})")
    tail = (r.stdout + r.stderr).strip().splitlines()[-4:]
    for line in tail:
        print(f"           | {line[:150]}")
    if not ok:
        failed = True
print(f"\nworkflow {'FAILED' if failed else 'succeeded'}; job summary: {summary} ({summary.stat().st_size} bytes)")
sys.exit(1 if failed else 0)
