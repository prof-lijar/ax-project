#!/bin/sh
set -eu
# One backend service owns its schema migrations before accepting requests.
alembic upgrade head
exec "$@"
