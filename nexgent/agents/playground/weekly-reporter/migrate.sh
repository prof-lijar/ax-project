#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-${script_dir}/../../.venv/bin/python}"

# Help and local coverage do not require production/SSH configuration.
for arg in "$@"; do
  if [[ "$arg" == "--help" || "$arg" == "-h" || "$arg" == "--coverage-output" || "$arg" == --coverage-output=* ]]; then
    exec "$python_bin" "${script_dir}/migrate.py" "$@"
  fi
done

if ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required for automatic SSH password login. Install it first." >&2
  exit 1
fi

# Parse dotenv as data, never as shell code. Fail before SSH if settings are missing.
tunnel_config="$("$python_bin" - "$script_dir" <<'PY'
import os
import re
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(sys.argv[1]).parent.parent / '.env', override=False)
sys.path.insert(0, sys.argv[1])
from migrate import source_database_dsn
try:
    source_database_dsn()
except ValueError as exc:
    sys.exit(str(exc))
for key in ('LIVE_PROD_DB_USER', 'LIVE_PROD_DB_PASSWORD', 'LIVE_PROD_SSH_PASSWORD'):
    if not os.environ.get(key, '').strip():
        sys.exit(f'Missing {key}; configure agents/.env first')
try:
    port = int(os.environ.get('LIVE_PROD_TUNNEL_PORT', '15432'))
    if not 1 <= port <= 65535:
        raise ValueError
except ValueError:
    sys.exit('LIVE_PROD_TUNNEL_PORT must be between 1 and 65535')
print(port)
for key, default, pattern in (
    ('LIVE_PROD_SSH_HOST', '', r'[A-Za-z0-9][A-Za-z0-9.-]*'),
    ('LIVE_PROD_SSH_ID', 'root', r'[A-Za-z0-9_][A-Za-z0-9_.-]*'),
):
    value = os.environ.get(key, default)
    if not re.fullmatch(pattern, value):
        sys.exit(f'Invalid {key}')
    print(value)
remote_host = os.environ.get('LIVE_PROD_DB_HOST', '')
if remote_host.isdecimal() or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', remote_host):
    sys.exit('Invalid or missing LIVE_PROD_DB_HOST; configure agents/.env')
try:
    remote_port = int(os.environ.get('LIVE_PROD_DB_PORT', '5432'))
    if not 1 <= remote_port <= 65535:
        raise ValueError
except ValueError:
    sys.exit('LIVE_PROD_DB_PORT must be between 1 and 65535')
print(remote_host)
print(remote_port)
PY
)"
mapfile -t tunnel_settings <<< "$tunnel_config"
tunnel_port="${tunnel_settings[0]}"
ssh_destination="${tunnel_settings[2]}@${tunnel_settings[1]}"
remote_host="${tunnel_settings[3]}"
remote_port="${tunnel_settings[4]}"

control_dir="$(mktemp -d /tmp/weekly-reporter-ssh.XXXXXXXX)"
control_socket="${control_dir}/control"
cleanup() {
  ssh -S "$control_socket" -O exit "$ssh_destination" >/dev/null 2>&1 || true
  rm -rf -- "$control_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Opening SSH tunnel on 127.0.0.1:${tunnel_port}..."
# -f backgrounds only after authentication; forwarding failure stops the script.
# A private control socket lets cleanup close only the tunnel owned by this run.
sshpass -d 3 ssh -F /dev/null -M -S "$control_socket" -fNT \
  -o StrictHostKeyChecking=accept-new \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o NumberOfPasswordPrompts=1 \
  -o ExitOnForwardFailure=yes \
  -o ConnectTimeout=15 \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "127.0.0.1:${tunnel_port}:${remote_host}:${remote_port}" \
  "$ssh_destination" 3< <("$python_bin" - "$script_dir" <<'PY'
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(sys.argv[1]).parent.parent / '.env', override=False)
sys.stdout.write(os.environ['LIVE_PROD_SSH_PASSWORD'] + '\n')
PY
)

"$python_bin" "${script_dir}/migrate.py" "$@"
