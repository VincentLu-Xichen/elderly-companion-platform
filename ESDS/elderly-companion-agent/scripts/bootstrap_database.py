from __future__ import annotations

from alembic import command
from alembic.config import Config

from webapp.database import SessionLocal
from webapp.services import bootstrap_invites


def main() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as db:
        bootstrap_invites(db)
    print("Database migrations and invite bootstrap completed.")


if __name__ == "__main__":
    main()
