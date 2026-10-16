import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


def migrate(url, *arguments):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=30,
    )


def seed(url, names):
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User

    engine = create_engine(url)
    with Session(engine) as db:
        user = User(email="migration@example.com", password_hash="not-used-in-this-test")
        db.add(user)
        db.flush()
        rows = [
            KnowledgeBase(user_id=user.id, name=name, name_key=name.casefold()) for name in names
        ]
        db.add_all(rows)
        db.commit()
        identifiers = [str(row.id) for row in rows]
    engine.dispose()
    return identifiers


def test_migration_rekeys_existing_names_without_changing_display_or_ids(tmp_path):
    from app.models.knowledge_base import KnowledgeBase

    url = f"sqlite:///{tmp_path / 'migration.db'}"
    assert migrate(url, "upgrade", "0002_knowledge_bases").returncode == 0
    identifiers = seed(url, ["Python 学习", "React\u3000学习"])
    result = migrate(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = create_engine(url)
    with Session(engine) as db:
        rows = db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.name)).all()
        assert {str(row.id) for row in rows} == set(identifiers)
        assert {row.name for row in rows} == {"Python 学习", "React\u3000学习"}
        assert {row.name_key for row in rows} == {"python学习", "react学习"}
    assert migrate(url, "downgrade", "0002_knowledge_bases").returncode == 0
    with Session(engine) as db:
        assert {row.name_key for row in db.scalars(select(KnowledgeBase))} == {
            "python 学习",
            "react\u3000学习",
        }
    engine.dispose()


def test_conflict_stops_migration_before_changing_any_record(tmp_path):
    from app.models.knowledge_base import KnowledgeBase

    url = f"sqlite:///{tmp_path / 'conflict.db'}"
    assert migrate(url, "upgrade", "0002_knowledge_bases").returncode == 0
    identifiers = seed(url, ["Python 学习", "Python学习"])
    result = migrate(url, "upgrade", "head")
    assert result.returncode != 0
    assert all(identifier in result.stderr for identifier in identifiers)
    engine = create_engine(url)
    with Session(engine) as db:
        assert {row.name_key for row in db.scalars(select(KnowledgeBase))} == {
            "python 学习",
            "python学习",
        }
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0002_knowledge_bases"
    engine.dispose()
