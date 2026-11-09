# sysml-kit: your team's SysML v2 model (SYS 5100)

From Week 4 your team keeps **one small SysML v2 model** in this repository: context, stakeholder
concerns, requirements, structure, trace (satisfy / verify) and allocation. The course is
*model-literate, not model-first*: the model is evidence for your gates, not the goal. Every push
runs the course checks **C1–C8** and regenerates the tables for your gate package.

You write SysML v2 as text. The checker is the free OMG SysML v2 Pilot Implementation plus a
course layer (`./kit`). One check takes about **20 seconds**.

---

## 1. Set up (once)

**In GitHub Codespaces (recommended)**

1. Accept the GitHub Classroom assignment link and join (or create) your team.
2. In your team repository: **Code → Codespaces → Create codespace on main**.
3. Wait for the setup script to finish (first time 3–5 min: it installs Java 21 and Graphviz and
   downloads the 124 MB pilot implementation). The terminal ends with `Ready.`
4. Pick your situation's starter and check it:

```bash
./kit init robot          # or: microgrid, sensornet, gnssnav, partner
./kit check
```

5. Rename the package (first line of `model/<starter>.sysml`) to your team's system, commit, push.

**On your own machine** (optional): Java 21 (Temurin), Python 3.10+, then

```bash
pip install zstandard && python tools/fetch_pilot.py --dest ext/kernel
pip install -e tools/vendor/reqlint
./kit check
```

---

## 2. The daily loop

```text
edit model/*.sysml  ->  ./kit check  ->  fix the FIRST problem  ->  ./kit check  ->  git commit + push
                                                                               ->  CI runs the same checks
```

- **Before you write requirements:** `./kit lint` runs `reqlint` on every requirement's `doc` text.
- **Before a gate:** set the gate in `gates/CURRENT` (one word: `G2`, `G3`, `G4`), run
  `./kit gen-table`, and commit the tables with your gate tag.
- **On GitHub:** open **Actions → model-ci → latest run**. The job summary shows the results
  table; the `gate-tables` artifact holds the generated tables.

One person edits a given file at a time, or use branches and pull requests (the checks run on PRs
too). Never commit interview notes or names into the model: refer to evidence by id
(`INT-03`, `OBS-02`, `DOC-01`, `HYP-01`).

---

## 3. Reading errors

If the model does not parse (check C1), nothing else runs. The kit shows at most **12 errors**
and a hint, and tells you to **fix the first one first**: one missing `;` can cause 150 errors,
and all the later ones disappear when you fix it.

```text
C1 FAILED: the SysML v2 parser found 3 error(s) in 1 file(s).
Fix the FIRST error first, then re-run ./kit check: later errors are usually knock-on effects of it.

  1. model/robot.sysml:9:9  no viable alternative at input 'attribute'
     hint: Most likely a missing ';' (or '}') at the end of the PREVIOUS line ...
```

| Message (start) | Usual cause | Fix |
|---|---|---|
| `no viable alternative at input 'part'` (or `attribute`, `port`, ...) | missing `;` or `}` on the line **before** | add it |
| `no viable alternative at input 'frame'` | you used a keyword as a name (`frame`, `state`, `item`, `in`, `end`, ...) | rename (`radioFrame`) |
| `Couldn't resolve reference to Type 'MassValue'` | missing import or misspelt name | `private import ISQ::*;` and `private import SI::*;` |
| `Couldn't resolve reference to Element 'mW'` | unit not in the SI library | use a library unit: `0.02 [W]`, not `20 [mW]` |
| subject / type conformance error on a `satisfy` | a system requirement satisfied by a subsystem | write a derived requirement whose subject is the subsystem |
| `mismatched input` / `extraneous input '}'` | braces do not balance | count `{` and `}` in the block |

Units the kit can evaluate: `[kg] [g] [m] [km] [mm] [s] [min] [h] [d] [Hz] [W] [kW] [J] [kJ] [W*h]
[kW*h] [m/s] [m/s^2] [V] [A] [N]` and combinations such as `[W*h/(kg*km)]`.

---

## 4. What each check means

Results are `PASS`, `WARN`, `FAIL` or `INFO`. **Any FAIL gives a non-zero exit code** (the CI run
turns red). Computed results carry a **basis label** from their *weakest input*: `Calculated`
(all inputs specified, measured or calculated), `Predicted`, `Estimated` or `Assumed`. A result
that rests on an assumed value is labelled **Assumed** however exact the arithmetic looks: expect
the board to ask about it.

| Check | What it checks | How to pass | Severity by gate |
|---|---|---|---|
| **C1 parse** | the model parses and validates against the SysML v2 standard library | fix errors, first one first | FAIL always |
| **C2 requirements & trace** | every requirement has an id `<'REQ-04'>`, `doc` text, at least one `satisfy` and one `verify`; an upward trace (`@Evidence { source = "INT-05"; }`, a framed concern, or a parent id like `REQ-04.1`); no `TODO`/`TBD` | add the missing piece | no id / no text: FAIL always. Missing satisfy or verify: WARN at G1–G2, FAIL from G3. TODO/TBD: WARN until G3, FAIL at G4. No upward trace: WARN. |
| **C3 constraints** | each `require constraint { ... }` evaluates TRUE on each satisfying part | change the design value or (with a CR) the requirement | FALSE: FAIL. Cannot evaluate (e.g. no value yet): WARN |
| **C4 budgets** | for a requirement attribute named `<x>Max` (e.g. `massMax`, `latencyMax`, `peakPowerMax`), the kit adds up attribute `<x>` over every part of the satisfier, **independently of your own roll-up**, adds each part's `@Budget` growth, then the system margin (`systemMargin` on the requirement, else 10 %) | keep the current estimate under the limit, and with growth and margin too | current estimate over the limit: FAIL. Over only with growth + margin: WARN. Your own roll-up expression (e.g. `grossMass`) disagrees with the part tree: FAIL |
| **C5 resource balance** | a requirement with attributes `supply`, `demand` and `marginMin`: margin = (supply − demand) / demand ≥ marginMin | more supply, less demand, or a justified floor | below the floor: FAIL |
| **C6 interfaces** | every internal port is connected (`interface`, `connect` or `bind`); interface ends are conjugate (`PowerPort` to `~PowerPort`) | connect or delete the port; type one end with `~` | dangling port or non-conjugate ends: FAIL. Unbound boundary port: WARN |
| **C7 states** | (if you have a `state def`) every state is reachable from the initial state; no dead ends | add the transition | unreachable: FAIL. No way out: WARN |
| **C8 test verdicts** | every `verification` usage carries `@TestVerdict { verdict = ...; asRun = "TD-03/run2"; ncr = "none"; }` after Test Day | add the verdict; a `fail` needs an NCR id | INFO until G3; FAIL at G4 |

The check also prints a one-line `reqlint` summary. Wording findings never change the exit code
of `check`; run `./kit lint` to see them.

### Course conventions the checks rely on

```sysml
private import SYS5100Lib::*;                         // the course metadata library (lib/)
requirement <'SN-007'> alertLatency : NetworkRequirement {
    doc /* An alert shall reach the gateway within 10 s of the threshold crossing, at the 95th percentile. */
    @Evidence { grade = Basis::specified; source = "INT-01"; }   // upward trace
    frame timelyWarning;
    attribute latencyMax : DurationValue = 10 [s];                // C4 budget limit for 'latency'
    require constraint { net.alertLatency <= latencyMax }        // C3
}
part :>> node { attribute :>> latency = 4.0 [s] { @Budget { basis = Basis::estimated; growth = 0.20; } } }
satisfy alertLatency by ridgeNetwork;
verification latencyTest : LatencyTest { subject :>> net = ridgeNetwork;
    @TestVerdict { verdict = VerificationCases::VerdictKind::fail; asRun = "TD-03/run2"; ncr = "NCR-02"; } }
```

- Start every verification `doc` with its method: `Test:`, `Analysis:`, `Inspection:` or
  `Demonstration:` (the verification table uses it).
- Change control (Week 11): put `@ChangeRecord { crId = "CR-004"; status = CRStatus::approved;
  decidedBy = "CCB-07"; }` on each element a change touches and `@Baseline { tag = "ABL-1.1"; }`
  on baselined requirements. The tag must match your git tag.
- Do not edit `lib/SYS5100Lib.sysml`. The names in it are shared by every team and by the checks.
- Do the arithmetic for budgets in the kit or in `decision-lab`, not with `calc` in the model.
  The SYS 5100 subset leaves out `calc`, `analysis`, action flows and variants (they come in 51X2).

---

## 5. Tables for your gate package

```bash
./kit gen-table                 # writes gates/tables/*.md and *.csv
```

| File | Columns | Use |
|---|---|---|
| `requirements.md/.csv` | id, text, subject, parent, satisfied_by, verified_by, constraint_status | G2 requirements table |
| `trace.md/.csv` | id, concerns, evidence, risk, satisfied_by, allocated_to, verified_by, verdict, change, baseline (+ allocation list) | G3 model walk-through |
| `verification.md/.csv` | requirement, verification, method, subject, verdict, as_run, ncr | G4 verification cross-reference (VCD) |
| `changes.md/.csv` | element, kind, cr, status, decided_by, baseline (only when change metadata exists) | Week 11 CCB |

`OPEN` in a table means a missing satisfy or verify link: that is honest G2 evidence of what is
still open, not a failure. **Never edit the tables by hand.** Fix the model and regenerate, so the
tables and the model cannot disagree. Copy them into `gates/G2/` (etc.), commit, then tag
(`git tag G2-baseline && git push --tags`).

---

## 6. Command reference

```text
./kit check [--gate G1|G2|G3|G4] [FILE ...]      checks C1-C8; exit 0 OK, 1 any FAIL, 2 setup problem
./kit gen-table [--gate G] [--out DIR] [FILE ...] tables to gates/tables/ (Markdown + CSV)
./kit lint [--format text|json] [FILE ...]       reqlint on requirement doc text
./kit viz [--out DIR] [FILE ...]                 optional SVG diagrams (part trees, state machines)
./kit init STARTER [--force]                     copy a starter into model/
reqlint FILE.csv|.md|.sysml|.txt                 lint requirements outside the model (Lab 4)
reqlint --text "The robot shall stop within 1.5 m."
```

`FILE` defaults to every `.sysml` file under `model/`. The gate comes from `--gate`, else
`$KIT_GATE`, else `gates/CURRENT`, else `G2`. Results are also written to `out/check.md` and
`out/check.json`.

**Using AI to draft model text is allowed.** Record it in `AI-use.md`, then run `./kit check` and
`./kit lint` and read every line it wrote: the checks catch broken trace and arithmetic, not a
wrong requirement.

## Licence

**Licence.** CC0 1.0 Universal (see `LICENSE`). To the extent possible under law, Franz Newland has waived all copyright and related rights in this template (kit scripts, checks, course library `SYS5100Lib.sysml`, starters and tests). Exceptions: quoted third-party material, trademarks, standards cited by reference, and third-party dependencies, which keep their own licences (see `THIRD_PARTY.md`). Drafted with generative AI (Anthropic Claude) under the instructor's direction; see `docs/AI_DISCLOSURE.md` in the course package. The OMG SysML v2 Pilot Implementation (EPL-2.0) is downloaded at set-up time and is not part of this template or of the dedication.
