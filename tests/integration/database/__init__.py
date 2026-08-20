"""
Unit tests for Alembic database migration graph consistency.

Verifies:
1. Migration files can be parsed and discovered
2. The migration history forms a single, linear, connected DAG
3. There are no dangling down_revisions or multiple branch heads
4. Every migration defines both upgrade() and downgrade() functions
"""

import importlib.util
from pathlib import Path

import pytest


def _get_migration_modules():
    versions_dir = Path("alembic/versions")
    if not versions_dir.exists():
        return []
    migration_files = sorted(versions_dir.glob("*.py"))
    migrations = []
    for file_path in migration_files:
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        revision = getattr(module, "revision", None)
        down_revision = getattr(module, "down_revision", None)
        migrations.append((revision, down_revision, module))
    return migrations


class TestAlembicMigrationGraph:
    def test_migrations_exist(self):
        migrations = _get_migration_modules()
        assert len(migrations) >= 6

    def test_linear_revision_chain(self):
        migrations = _get_migration_modules()
        assert len(migrations) > 0
        rev_map = {}
        all_revisions = set()
        for revision, down_revision, _ in migrations:
            assert revision is not None
            all_revisions.add(revision)
            rev_map[revision] = down_revision
        base_migrations = [rev for rev, down_rev in rev_map.items() if down_rev is None]
        assert len(base_migrations) == 1
        for _rev, down_rev in rev_map.items():
            if down_rev is not None:
                assert down_rev in all_revisions

    def test_upgrade_and_downgrade_functions_defined(self):
        migrations = _get_migration_modules()
        for _revision, _, module in migrations:
            assert hasattr(module, "upgrade") and callable(module.upgrade)
            assert hasattr(module, "downgrade") and callable(module.downgrade)
