"""Read-only check for knowledge-base names that collide under the new rule."""

import json
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import make_database
from app.models.knowledge_base import KnowledgeBase
from app.services.knowledge_base_service import normalize_name


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    engine, sessions = make_database(Settings())
    try:
        groups = {}
        with sessions() as db:
            for row in db.execute(
                select(KnowledgeBase.id, KnowledgeBase.user_id, KnowledgeBase.name)
            ):
                key = (str(row.user_id), normalize_name(row.name))
                groups.setdefault(key, []).append({"id": str(row.id), "name": row.name})
        conflicts = [
            {"user_id": user_id, "normalized_name": key, "records": records}
            for (user_id, key), records in groups.items()
            if len(records) > 1
        ]
        print(json.dumps({"conflict_groups": conflicts}, ensure_ascii=False, indent=2))
        return 1 if conflicts else 0
    except SQLAlchemyError:
        print("Database check failed. Verify the local database and migration status.")
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
