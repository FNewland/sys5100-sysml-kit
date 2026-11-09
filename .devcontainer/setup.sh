#!/usr/bin/env bash
# One-time Codespace setup: Graphviz (optional diagrams), Python helpers, the SysML v2 pilot (~124 MB).
set -euo pipefail
sudo apt-get update -q && sudo apt-get install -y -q graphviz > /dev/null
pip install --quiet zstandard pytest numpy pyyaml
pip install --quiet -e tools/vendor/reqlint
python tools/fetch_pilot.py --version "${SYSML_PILOT_VERSION:-0.62.0}" --dest ext/kernel
chmod +x kit
echo "Ready. Try:  ./kit init robot   then   ./kit check"
