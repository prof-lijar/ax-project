#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-${script_dir}/../../.venv/bin/python}"

for arg in "$@"; do
  if [[ "$arg" == "--help" || "$arg" == "-h" ]]; then
    exec "$python_bin" "${script_dir}/fix.py" "$@"
  fi
done

if ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required to open the production SSH tunnel." >&2
  exit 1
fi

# Reuse connection settings as data; do not invoke or modify the migration tool.
tunnel_config="$("$python_bin" - "$script_dir" <<'PY'
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(sys.argv[1]).parent / 'weekly-reporter/.env', override=False)
for key in ('TARGET_DB_USER', 'TARGET_DB_PASSWORD', 'SSH_PASSWORD'):
    if not os.environ.get(key, '').strip():
        sys.exit(f'Missing {key}; configure playground/weekly-reporter/.env')
try:
    port = int(os.environ.get('TARGET_DB_PORT', '15432'))
    if not 1 <= port <= 65535:
        raise ValueError
except ValueError:
    sys.exit('TARGET_DB_PORT must be between 1 and 65535')
if os.environ.get('TARGET_DB_HOST', '127.0.0.1') not in ('127.0.0.1', 'localhost'):
    sys.exit('TARGET_DB_HOST must use the local SSH tunnel: 127.0.0.1 or localhost')
print(port)
for key, default, pattern in (
    ('SSH_HOST', '211.188.52.211', r'[A-Za-z0-9][A-Za-z0-9.-]*'),
    ('SSH_ID', 'root', r'[A-Za-z0-9_][A-Za-z0-9_.-]*'),
):
    value = os.environ.get(key, default)
    if not re.fullmatch(pattern, value):
        sys.exit(f'Invalid {key}')
    print(value)
PY
)"
mapfile -t tunnel_settings <<< "$tunnel_config"
tunnel_port="${tunnel_settings[0]}"
ssh_destination="${tunnel_settings[2]}@${tunnel_settings[1]}"
control_dir="$(mktemp -d /tmp/weekly-count-fix-ssh.XXXXXXXX)"
control_socket="${control_dir}/control"
cleanup() {
  ssh -S "$control_socket" -O exit "$ssh_destination" >/dev/null 2>&1 || true
  rm -rf -- "$control_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Opening SSH tunnel on 127.0.0.1:${tunnel_port}..."
sshpass -d 3 ssh -F /dev/null -M -S "$control_socket" -fNT \
  -o StrictHostKeyChecking=accept-new \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o NumberOfPasswordPrompts=1 \
  -o ExitOnForwardFailure=yes \
  -o ConnectTimeout=15 \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "127.0.0.1:${tunnel_port}:pg-34le5q.vpc-cdb-kr.ntruss.com:5432" \
  "$ssh_destination" 3< <("$python_bin" - "$script_dir" <<'PY'
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(sys.argv[1]).parent / 'weekly-reporter/.env', override=False)
sys.stdout.write(os.environ['SSH_PASSWORD'] + '\n')
PY
)

"$python_bin" "${script_dir}/fix.py" "$@"
