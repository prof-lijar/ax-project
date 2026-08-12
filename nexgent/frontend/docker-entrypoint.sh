#!/bin/sh

set -eu

cd /app

dependency_marker="node_modules/.nexgent-package-lock.sha256"
current_lock_hash="$(sha256sum package-lock.json | cut -d ' ' -f 1)"
installed_lock_hash=""

if [ -f "$dependency_marker" ]; then
  installed_lock_hash="$(cat "$dependency_marker")"
fi

if [ "$installed_lock_hash" != "$current_lock_hash" ]; then
  echo "package-lock.json changed; synchronizing frontend dependencies..."
  npm ci
  printf '%s\n' "$current_lock_hash" > "$dependency_marker"
fi

exec "$@"
