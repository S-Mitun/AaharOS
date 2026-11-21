"""MP02 gate: migrations go up from empty, down one step, and up again (and all the way down and back).

The checks are generic over the revision history, so every new migration is round-tripped automatically.
"""

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from tests.db.conftest import alembic_config, owner_url, recreate_database

MIGRATION_DB = "aaharos_migtest"

Snapshot = tuple[str | None, int, int, int, int, int]


def _snapshot(database: str) -> Snapshot:
    """(revision, tables, roles seeded, triggers, RLS policies, aahar_* functions)."""
    engine = create_engine(owner_url(database))
    try:
        with engine.connect() as c:
            version = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            tables = len([t for t in inspect(c).get_table_names() if t != "alembic_version"])
            roles = c.execute(text("SELECT count(*) FROM roles")).scalar_one() if tables else 0
            triggers = c.execute(
                text(r"SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'trg\_%'")
            ).scalar_one()
            policies = c.execute(text("SELECT count(*) FROM pg_policy")).scalar_one()
            functions = c.execute(text(r"SELECT count(*) FROM pg_proc WHERE proname LIKE 'aahar\_%'")).scalar_one()
        return version, tables, roles, triggers, policies, functions
    finally:
        engine.dispose()


def _head_and_previous() -> tuple[str, str]:
    script = ScriptDirectory.from_config(alembic_config(MIGRATION_DB))
    head = script.get_current_head()
    assert head is not None
    previous = script.get_revision(head).down_revision
    assert isinstance(previous, str)
    return head, previous


def test_upgrade_downgrade_one_step_upgrade(database_available: None) -> None:
    recreate_database(MIGRATION_DB)
    cfg = alembic_config(MIGRATION_DB)
    head, previous = _head_and_previous()

    command.upgrade(cfg, "head")
    at_head = _snapshot(MIGRATION_DB)
    assert at_head[0] == head
    assert at_head[2] == 5  # the five roles are seeded
    assert at_head[3] > 30 and at_head[4] > 60

    command.downgrade(cfg, "-1")
    one_down = _snapshot(MIGRATION_DB)
    assert one_down[0] == previous
    assert one_down != at_head  # the step really undid something

    command.upgrade(cfg, "head")
    assert _snapshot(MIGRATION_DB) == at_head


def test_every_revision_downgrades_and_reapplies(database_available: None) -> None:
    """Walk all the way down to empty one step at a time, then back up: each downgrade must work."""
    recreate_database(MIGRATION_DB)
    cfg = alembic_config(MIGRATION_DB)
    command.upgrade(cfg, "head")
    at_head = _snapshot(MIGRATION_DB)

    script = ScriptDirectory.from_config(cfg)
    for _ in script.walk_revisions():
        command.downgrade(cfg, "-1")
    version, tables, _roles, triggers, policies, functions = _snapshot(MIGRATION_DB)
    assert (version, tables, triggers, policies, functions) == (None, 0, 0, 0, 0)

    command.upgrade(cfg, "head")
    assert _snapshot(MIGRATION_DB) == at_head


def test_models_match_migrations(migrated: str) -> None:
    """No drift: the models and the migration history describe the same schema."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db_models import metadata

    engine = create_engine(owner_url(migrated))
    try:
        with engine.connect() as c:
            diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), metadata)
    finally:
        engine.dispose()
    assert diff == []
