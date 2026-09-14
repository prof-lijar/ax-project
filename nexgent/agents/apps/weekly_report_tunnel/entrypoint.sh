#!/bin/sh
set -eu
: "${WEEKLY_REPORT_SSH_HOST:?required}"
: "${WEEKLY_REPORT_SSH_USER:?required}"
: "${WEEKLY_REPORT_TARGET_HOST:?required}"
# Private bridge only, with no host port; only the sync worker joins it.
# Pin known_hosts outside the container after independently verifying the key.
exec ssh -NT \
    -o BatchMode=yes \
    -o ForwardAgent=no \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile=/run/secrets/known_hosts \
    -o IdentityFile=/run/secrets/ssh_key \
    -o IdentitiesOnly=yes \
    -o ExitOnForwardFailure=yes \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=3 \
    -p "${WEEKLY_REPORT_SSH_PORT:-22}" \
    -l "$WEEKLY_REPORT_SSH_USER" \
    -L "0.0.0.0:15432:${WEEKLY_REPORT_TARGET_HOST}:${WEEKLY_REPORT_TARGET_PORT:-5432}" \
    -- "$WEEKLY_REPORT_SSH_HOST"
