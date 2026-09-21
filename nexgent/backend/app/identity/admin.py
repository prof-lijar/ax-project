"""Operator bootstrap and password recovery. Passwords are read through getpass."""
import argparse
from getpass import getpass

from sqlalchemy import select

from app.identity.config import load_identity_settings
from app.identity.models import ADMIN_ROLE_ID, User
from app.identity.router import Username
from app.identity.store import AccessError, IdentityStore
from pydantic import TypeAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-admin")
    create.add_argument("--username", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--email", default="")
    reset = commands.add_parser("set-password")
    reset.add_argument("--username", required=True)
    args = parser.parse_args()
    store = IdentityStore(load_identity_settings())
    try:
        username = TypeAdapter(Username).validate_python(args.username)
        password = getpass("Password (4–12 characters): ")
        if password != getpass("Confirm password: "):
            raise ValueError("Passwords do not match")
        if args.command == "create-admin":
            if not args.name.strip() or len(args.name) > 200 or len(args.email) > 320:
                raise ValueError("Invalid name or email")
            store.create_user(None, username=username, name=args.name.strip(), email=args.email.strip(),
                              password=password, role_ids=[ADMIN_ROLE_ID], group_ids=[])
            print("Administrator created.")
        else:
            with store.sessions() as db:
                user_id = db.scalar(select(User.id).where(User.username == username))
            if user_id is None:
                raise ValueError("User not found")
            store.reset_password(None, user_id, password)
            print("Password updated; previous logins are invalid.")
    except (ValueError, AccessError) as error:
        parser.exit(1, f"{getattr(error, 'code', str(error))}\n")
    finally:
        store.engine.dispose()


if __name__ == "__main__":
    main()
