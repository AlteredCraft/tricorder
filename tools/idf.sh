#!/usr/bin/env bash
# Run ESP-IDF with the project-local toolchain, from any working directory.
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export IDF_TOOLS_PATH="$project_root/.tools/espressif"
export PATH="$project_root/.tools/python-env/bin:$PATH"
source "$project_root/.tools/esp-idf/export.sh" >&2
exec idf.py "$@"
