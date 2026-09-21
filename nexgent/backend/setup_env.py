"""Generate a missing login signing key in the backend environment file."""
import argparse
import os
from pathlib import Path
import secrets

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--env-file", choices=("dev.env", "prod.env"), default="dev.env")
args = parser.parse_args()
target = Path(__file__).resolve().parent / args.env_file
if target.is_symlink():
    raise SystemExit("Refusing to write through a symlink.")
existing = target.read_text() if target.exists() else ""
values = {line.partition("=")[0].strip(): line.partition("=")[2].strip().strip("\"'")
          for line in existing.splitlines() if "=" in line and not line.lstrip().startswith("#")}
if not values.get("NEXGENT_AUTH_SIGNING_KEY"):
    lines = [line for line in existing.splitlines() if line.partition("=")[0].strip() != "NEXGENT_AUTH_SIGNING_KEY"]
    fd = os.open(target, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "a") as output:
        if lines:
            output.write("\n".join(lines) + "\n")
        output.write(f"NEXGENT_AUTH_SIGNING_KEY={secrets.token_urlsafe(48)}\n")
    print(f"Added login signing key to backend/{args.env_file}.")
else:
    print("Existing login signing key preserved.")
print("Set NEXGENT_DATABASE_URL and NEXGENT_PUBLIC_URL in the same file.")
