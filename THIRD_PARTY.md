# Third-party components: sysml-kit

These are **not** part of the CC0 1.0 dedication of this tool. Each keeps its own licence; none is copied into this folder unless the row says so. Licences were identified on 20 Oct 2026 from the projects' own metadata; re-check before a release ([check] where marked).

| Component | Used for | Licence | Distributed here? |
|---|---|---|---|
| OMG SysML v2 Pilot Implementation (`jupyter-sysml-kernel` all-in-one jar, incl. the SysML v2 / KerML standard model library `sysml.library`) | parsing and validating models (`tools/SysMLCheck.java` calls its public API) | EPL-2.0 (verified from the project's LICENSE and the conda-forge metadata, 20 Oct 2026) | **No.** `tools/fetch_pilot.py` downloads it from conda-forge into `ext/` (git-ignored) at Codespace or CI set-up. If you publish an image or archive that contains the jar, ship the EPL-2.0 notice and say where its source is available. |
| Eclipse Temurin JDK 21 (devcontainer feature, `actions/setup-java`) | running the pilot | GPL-2.0 with Classpath Exception | No |
| Python 3.12 (devcontainer image `mcr.microsoft.com/devcontainers/python`) | kit scripts and checks | PSF License; image: MIT definitions, Debian packages under their own licences | No |
| zstandard | unpacking the `.conda` archive in `fetch_pilot.py` | BSD-3-Clause | No |
| PyYAML | `tools/ci_local.py` (local CI replay) only | MIT | No |
| pytest | tests | MIT | No |
| Graphviz (optional) | rendering diagrams | EPL-1.0 [check current licence] | No |
| Syside Editor VS Code extension (Sensmetry, free tier) | syntax highlighting in Codespaces (optional; not used by any check) | proprietary, free tier [check terms] | No |
| GitHub Actions `actions/checkout`, `setup-java`, `setup-python`, `cache`, `upload-artifact` | CI workflow | MIT | No (referenced by tag) |
| reqlint (`tools/vendor/reqlint/`) | `./kit lint` | CC0 1.0 (course's own tool, vendored copy) | Yes; course-owned |

**Vendored and copied code.** The only vendored code is the course's own `reqlint`. `SysMLCheck.java` is the course's own thin wrapper, adapted from the Claude-built October 2026 MBSE prototype for this course; it imports the pilot's classes but contains no copied pilot source. `fetch_pilot.py` is the course's own downloader (Python standard library + zstandard). No standard-library `.sysml`/`.kerml` files from the pilot are included: `lib/SYS5100Lib.sysml`, the starters and the test models were written for the course.

**Standards.** SysML v2 and KerML are OMG specifications, cited by reference; the kit reproduces no specification text. "SysML" and "OMG" are trademarks of the Object Management Group.
