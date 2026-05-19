"""Tests for database migrations and schema validation."""

import subprocess
from pathlib import Path

import pytest


class TestAlembicConfiguration:
    """Test Alembic configuration and setup."""

    def test_alembic_ini_exists(self):
        """Verify alembic.ini configuration file exists."""
        alembic_ini = Path(__file__).parent.parent / "alembic.ini"
        assert alembic_ini.exists(), "alembic.ini not found"

    def test_alembic_versions_directory_exists(self):
        """Verify alembic versions directory exists."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"
        assert versions_dir.exists(), "alembic/versions directory not found"

    def test_alembic_env_exists(self):
        """Verify alembic env.py exists."""
        env_py = Path(__file__).parent.parent / "alembic" / "env.py"
        assert env_py.exists(), "alembic/env.py not found"

    def test_migration_files_exist(self):
        """Verify all expected migration files exist."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        expected_migrations = [
            "001_create_compliance_cases_table.py",
            "002_create_documents_table.py",
            "003_create_risk_assessments_table.py",
            "004_create_extracted_evidences_table.py",
            "005_create_review_decisions_table.py",
            "006_create_generated_reports_table.py",
            "007_create_jobs_table.py",
        ]

        for migration in expected_migrations:
            migration_file = versions_dir / migration
            assert migration_file.exists(), f"Migration file {migration} not found"


class TestMigrationHistory:
    """Test migration history and revision chain."""

    @pytest.mark.unit
    def test_migration_files_have_revision_ids(self):
        """Verify each migration file has a revision ID."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        for migration_file in sorted(versions_dir.glob("*.py")):
            if migration_file.name == "__init__.py":
                continue

            content = migration_file.read_text()
            assert 'revision: str = "' in content, f"{migration_file.name} missing revision ID"

    @pytest.mark.unit
    def test_migration_files_have_upgrade_function(self):
        """Verify each migration file has an upgrade function."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        for migration_file in sorted(versions_dir.glob("*.py")):
            if migration_file.name == "__init__.py":
                continue

            content = migration_file.read_text()
            assert "def upgrade()" in content, f"{migration_file.name} missing upgrade function"

    @pytest.mark.unit
    def test_migration_files_have_downgrade_function(self):
        """Verify each migration file has a downgrade function."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        for migration_file in sorted(versions_dir.glob("*.py")):
            if migration_file.name == "__init__.py":
                continue

            content = migration_file.read_text()
            assert "def downgrade()" in content, f"{migration_file.name} missing downgrade function"

    @pytest.mark.unit
    def test_migration_revision_chain(self):
        """Verify migrations form a linear revision chain."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        migration_files = sorted([f for f in versions_dir.glob("*.py") if f.name != "__init__.py"])

        # Expected chain: None -> 001 -> 002 -> 003 -> 004 -> 005 -> 006 -> 007 -> 008 -> 009
        expected_chain = [None, "001", "002", "003", "004", "005", "006", "007", "008", "009"]

        for i, migration_file in enumerate(migration_files):
            content = migration_file.read_text()

            expected_down_revision = expected_chain[i]
            expected_revision = expected_chain[i + 1]

            assert f'revision: str = "{expected_revision}"' in content, (
                f"{migration_file.name} has wrong revision ID"
            )

            if expected_down_revision is None:
                assert "down_revision: Union[str, None] = None" in content or (
                    "down_revision" in content and "None" in content
                ), f"{migration_file.name} should have no down_revision"
            else:
                assert (
                    f'down_revision: Union[str, None] = "{expected_down_revision}"' in content
                    or f'down_revision: str | None = "{expected_down_revision}"' in content
                ), f"{migration_file.name} has wrong down_revision"


class TestMigrationStructure:
    """Test individual migration file structure."""

    @pytest.mark.unit
    def test_001_migration_creates_compliance_cases_table(self):
        """Verify 001 migration creates compliance_cases table."""
        migration_file = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "001_create_compliance_cases_table.py"
        )
        content = migration_file.read_text()

        assert "compliance_cases" in content, "Missing compliance_cases table reference"
        assert "op.create_table" in content, "Missing table creation"
        assert "op.drop_table" in content, "Missing table drop in downgrade"

    @pytest.mark.unit
    def test_002_migration_creates_documents_table(self):
        """Verify 002 migration creates documents table."""
        migration_file = (
            Path(__file__).parent.parent / "alembic" / "versions" / "002_create_documents_table.py"
        )
        content = migration_file.read_text()

        assert "documents" in content, "Missing documents table reference"
        assert "op.create_table" in content, "Missing table creation"
        assert "op.drop_table" in content, "Missing table drop in downgrade"

    @pytest.mark.unit
    def test_003_migration_creates_risk_assessments_table(self):
        """Verify 003 migration creates risk_assessments table."""
        migration_file = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "003_create_risk_assessments_table.py"
        )
        content = migration_file.read_text()

        assert "risk_assessments" in content, "Missing risk_assessments table reference"
        assert "op.create_table" in content, "Missing table creation"
        assert "op.drop_table" in content, "Missing table drop in downgrade"

    @pytest.mark.unit
    def test_004_migration_creates_extracted_evidences_table(self):
        """Verify 004 migration creates extracted_evidences table."""
        migration_file = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "004_create_extracted_evidences_table.py"
        )
        content = migration_file.read_text()

        assert "extracted_evidences" in content, "Missing extracted_evidences table reference"
        assert "op.create_table" in content, "Missing table creation"
        assert "op.drop_table" in content, "Missing table drop in downgrade"

    @pytest.mark.unit
    def test_005_migration_creates_review_decisions_table(self):
        """Verify 005 migration creates review_decisions table."""
        migration_file = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "005_create_review_decisions_table.py"
        )
        content = migration_file.read_text()

        assert "review_decisions" in content, "Missing review_decisions table reference"
        assert "op.create_table" in content, "Missing table creation"
        assert "op.drop_table" in content, "Missing table drop in downgrade"

    @pytest.mark.unit
    def test_006_migration_creates_generated_reports_table(self):
        """Verify 006 migration creates generated_reports table."""
        migration_file = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "006_create_generated_reports_table.py"
        )
        content = migration_file.read_text()

        assert "generated_reports" in content, "Missing generated_reports table reference"
        assert "op.create_table" in content, "Missing table creation"
        assert "op.drop_table" in content, "Missing table drop in downgrade"


class TestMigrationSyntax:
    """Test migration file syntax and imports."""

    @pytest.mark.unit
    def test_migrations_have_proper_imports(self):
        """Verify migrations have required imports."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        for migration_file in sorted(versions_dir.glob("*.py")):
            if migration_file.name == "__init__.py":
                continue

            content = migration_file.read_text()
            # Check for either old or new style imports (ruff may upgrade them)
            has_sequence_import = (
                "from typing import Sequence" in content
                or "from collections.abc import Sequence" in content
            )
            has_sqlalchemy = "import sqlalchemy as sa" in content
            has_alembic = "from alembic import op" in content

            assert has_sequence_import, f"{migration_file.name} missing Sequence import"
            assert has_sqlalchemy, f"{migration_file.name} missing sqlalchemy import"
            assert has_alembic, f"{migration_file.name} missing alembic import"

    @pytest.mark.unit
    def test_migrations_use_uuid_for_primary_keys(self):
        """Verify migrations use UUID for primary keys."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        for migration_file in sorted(versions_dir.glob("*.py")):
            if migration_file.name == "__init__.py" or "enhance" in migration_file.name:
                continue

            content = migration_file.read_text()
            assert "sa.Uuid(as_uuid=True)" in content, (
                f"{migration_file.name} should use UUID primary keys"
            )

    @pytest.mark.unit
    def test_migrations_have_timestamps(self):
        """Verify migrations have created_at and updated_at timestamps."""
        versions_dir = Path(__file__).parent.parent / "alembic" / "versions"

        for migration_file in sorted(versions_dir.glob("*.py")):
            if migration_file.name == "__init__.py" or "enhance" in migration_file.name:
                continue

            content = migration_file.read_text()
            assert "created_at" in content, f"{migration_file.name} missing created_at timestamp"
            assert "updated_at" in content, f"{migration_file.name} missing updated_at timestamp"
            assert "sa.DateTime(timezone=True)" in content, (
                f"{migration_file.name} should use DateTime with timezone"
            )


class TestAlembicCommand:
    """Test alembic commands work properly."""

    @pytest.mark.unit
    def test_alembic_history_command(self):
        """Verify alembic history command works."""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            ["alembic", "history"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"alembic history failed: {result.stderr}"
        assert "006" in result.stdout, "Migration 006 not in history"
        assert "001" in result.stdout, "Migration 001 not in history"

    @pytest.mark.unit
    def test_alembic_heads_command(self):
        """Verify alembic heads command works."""
        backend_dir = Path(__file__).parent.parent
        result = subprocess.run(
            ["alembic", "heads"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"alembic heads failed: {result.stderr}"
        assert "009" in result.stdout, "Migration 009 should be head"
