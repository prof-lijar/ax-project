#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-${script_dir}/../../.venv/bin/python}"
for arg in "$@"; do
  case "$arg" in
    --migrate-to-live|-target|--target|-target=*|--target=*)
      exec "$python_bin" "${script_dir}/migrate-to-live.py" "$@"
      ;;
  esac
done
exec "$python_bin" "${script_dir}/migrate_weekly_risk_counts.py" "$@"
