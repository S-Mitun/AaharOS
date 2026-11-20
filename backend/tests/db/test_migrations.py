"""MP02 gate: migrations go up from empty, down one step, and up again (and all the way down and back)."""

from alembic import command
from sqlalchemy import create_engine, inspect, text

from tests.db.conftest import alembic_config, owner_url, recreate_database

MIGRATION_DB = "aaharos_migtest"


def _snapshot(database: str) -> tuple[str | None, int, int, int]:
    engine = create_engine(owner_url(database))
    try:
        with engine.connect() as c:
            version = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
            tables = len([t for t in inspect(c).get_table_names() if t != "alembic_version"])
            roles = c.execute(text("SELECT count(*) FROM roles")).scalar_one() if tables else 0
            triggers = c.execute(
                text(r"SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'trg\_%'")
            ).scalar_one()
        return version, tables, roles, triggers
    finally:
        engine.dispose()


def test_upgrade_downgrade_one_step_upgrade(database_available: None) -> None:
    recreate_database(MIGRATION_DB)
    cfg = alembic_config(MIGRATION_DB)

    command.upgrade(cfg, "head")
    version, tables, roles, triggers = _snapshot(MIGRATION_DB)
    assert version == "0005"
    assert tables == 67
    assert roles == 5
    assert triggers > 30

    command.downgrade(cfg, "-1")  # removes the seed only
    assert _snapshot(MIGRATION_DB) == ("0004", 67, 0, triggers)

    command.upgrade(cfg, "head")
    assert _snapshot(MIGRATION_DB) == ("0005", 67, 5, triggers)


def test_full_downgrade_to_empty_and_back(database_available: None) -> None:
    recreate_database(MIGRATION_DB)
    cfg = alembic_config(MIGRATION_DB)
    command.upgrade(cfg, "head")

    command.downgrade(cfg, "base")
    version, tables, _roles, triggers = _snapshot(MIGRATION_DB)
    assert (version, tables, triggers) == (None, 0, 0)

    command.upgrade(cfg, "head")
    assert _snapshot(MIGRATION_DB)[:3] == ("0005", 67, 5)


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
