"""Retry only committed private-file deletion tasks, never scan or delete arbitrary files."""

from sqlalchemy import func, select

from app.core.config import Settings
from app.db.session import make_database
from app.models.document import StorageCleanupTask
from app.services.document_storage import drain_cleanup


def main():
    settings = Settings()
    engine, sessions = make_database(settings)
    try:
        with sessions() as db:
            removed = drain_cleanup(db, settings)
            remaining = db.scalar(select(func.count()).select_from(StorageCleanupTask))
            print(f"Cleaned: {removed}; pending: {remaining}")
            return 1 if remaining else 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
