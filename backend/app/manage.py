"""Operational commands.

python -m app.manage set-password <username>            # prompts for the new password
NEW_PASSWORD=... python -m app.manage set-password admin  # non-interactive
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal, engine
from app.models import User
from app.models.enums import ActorType
from app.services import audit, sessions


async def set_password(username: str, password: str) -> int:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"user '{username}' not found", file=sys.stderr)
            return 1
        user.password_hash = hash_password(password)
        audit.record(db, audit.Actor(ActorType.SYSTEM, None, "manage-cli"), "PASSWORD_RESET", "user", user.id)
        await db.commit()
        await sessions.revoke_user_tokens(user.id)  # sign out every existing session
    await engine.dispose()
    print(f"password updated for '{username}'")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("set-password")
    sp.add_argument("username")
    args = parser.parse_args()
    if args.cmd == "set-password":
        password = os.getenv("NEW_PASSWORD") or getpass.getpass("New password: ")
        if not 8 <= len(password.encode()) <= 72:
            sys.exit("password must be 8-72 bytes")
        sys.exit(asyncio.run(set_password(args.username, password)))


if __name__ == "__main__":
    main()
