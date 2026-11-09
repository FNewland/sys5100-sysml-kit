#!/usr/bin/env bash
# Instructor/maintainer: refresh the vendored copy of reqlint from the course monorepo before
# publishing the template (students never need to run this). Lab answer keys are NOT copied.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-$HERE/../reqlint}"
DEST="$HERE/tools/vendor/reqlint"
rm -rf "$DEST" && mkdir -p "$DEST"
cp -r "$SRC/reqlint" "$SRC/pyproject.toml" "$SRC/README.md" "$SRC/LICENSE" "$DEST/"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +
echo "vendored reqlint $(grep -m1 version "$SRC/pyproject.toml")"
