"""Rekey names ignoring whitespace; stop safely if existing records collide."""

import sqlalchemy as sa
from alembic import op

revision = "0003_name_whitespace"
down_revision = "0002_knowledge_bases"
branch_labels = None
depends_on = None


def rekey(ignore_whitespace):
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("LOCK TABLE knowledge_bases IN SHARE ROW EXCLUSIVE MODE"))
    table = sa.table(
        "knowledge_bases",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String(80)),
        sa.column("name_key", sa.String(240)),
    )
    rows = bind.execute(sa.select(table.c.id, table.c.user_id, table.c.name)).mappings().all()
    keys = {}
    changes = []
    for row in rows:
        # Frozen migration rule: do not import mutable application normalization code.
        name_key = ("".join(row["name"].split()) if ignore_whitespace else row["name"]).casefold()
        if not name_key:
            raise RuntimeError(f"Empty normalized knowledge-base name: {row['id']}")
        keys.setdefault((row["user_id"], name_key), []).append(str(row["id"]))
        changes.append((row["id"], name_key))
    conflicts = [identifiers for identifiers in keys.values() if len(identifiers) > 1]
    if conflicts:
        identifiers = "; ".join(", ".join(group) for group in conflicts[:20])
        raise RuntimeError(
            "Knowledge-base name conflicts. Rename these record IDs before migration: "
            + identifiers
        )
    for identifier, name_key in changes:
        bind.execute(table.update().where(table.c.id == identifier).values(name_key=name_key))


def upgrade():
    rekey(ignore_whitespace=True)


def downgrade():
    rekey(ignore_whitespace=False)
