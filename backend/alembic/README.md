# Database Migrations with Alembic

This directory contains database migrations for TraceWise using Alembic, a lightweight database migration tool for SQLAlchemy.

## Overview

Alembic manages schema changes to the PostgreSQL database in a version-controlled manner. Each migration is an atomic operation that can be applied (`upgrade`) or reverted (`downgrade`).

## Current Migrations

The following migrations are implemented:

1. **001** - Create `compliance_cases` table
   - Main table for compliance cases
   - Contains case metadata, status, and risk level
   - Includes indexes for efficient querying

2. **002** - Create `documents` table
   - Stores uploaded documents for cases
   - References compliance_cases via foreign key
   - Tracks document type and processing status

3. **003** - Create `risk_assessments` table
   - Risk assessment records linked to compliance cases
   - Contains risk metrics and analysis data

4. **004** - Create `extracted_evidences` table
   - Evidence extracted from documents
   - Linked to both documents and risk assessments
   - Includes evidence type and severity

5. **005** - Create `review_decisions` table
   - Review decisions for cases
   - Tracks reviewer decisions and timestamps

6. **006** - Create `generated_reports` table
   - Final compliance reports generated for cases
   - Multiple reports per case for audit trail
   - Tracks generation timestamp and agent/reviewer

## Running Migrations

### Prerequisites

- PostgreSQL database running and accessible
- `DATABASE_URL` environment variable set or `sqlalchemy.url` configured in alembic.ini
- Virtual environment activated with dependencies installed

### Upgrade to Latest Schema

Apply all pending migrations:

```bash
alembic upgrade head
```

Upgrade to a specific migration:

```bash
alembic upgrade 003
```

### Downgrade (Rollback)

Revert the last migration:

```bash
alembic downgrade -1
```

Revert to a specific migration:

```bash
alembic downgrade 001
```

Revert all migrations (returns to base state):

```bash
alembic downgrade base
```

### Check Current State

See the current migration revision:

```bash
alembic current
```

View full migration history:

```bash
alembic history
```

List all migration heads:

```bash
alembic heads
```

## Creating New Migrations

### Manual Migration (Recommended)

For explicit control over migration logic:

```bash
alembic revision -m "describe_your_change"
```

This creates a new migration file in `versions/` with `upgrade()` and `downgrade()` functions.

Edit the functions to:
1. **upgrade()**: Define the schema changes to apply
2. **downgrade()**: Define how to revert those changes

Example migration structure:

```python
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"

def upgrade() -> None:
    """Add new_column to compliance_cases table."""
    op.add_column('compliance_cases', 
                  sa.Column('new_column', sa.String(255), nullable=True))

def downgrade() -> None:
    """Remove new_column from compliance_cases table."""
    op.drop_column('compliance_cases', 'new_column')
```

### Auto-generated Migration (Use with Caution)

Alembic can detect schema changes, but this requires careful review:

```bash
alembic revision --autogenerate -m "describe_your_change"
```

**Important**: Always review auto-generated migrations before applying them to production. Auto-generation can miss nuances and may not generate optimal SQL.

## Migration Best Practices

### 1. Keep Migrations Atomic
Each migration should do one logical thing. Break complex changes into multiple migrations.

### 2. Test Migrations Thoroughly
Always test both `upgrade()` and `downgrade()` before committing:

```bash
# Test upgrade
alembic upgrade +1

# Test downgrade
alembic downgrade -1

# Test roundtrip
alembic upgrade +1
alembic downgrade -1
alembic upgrade +1
```

### 3. Write Clear Docstrings
Each migration should have a clear docstring describing the change:

```python
def upgrade() -> None:
    """Add user_id column to documents table for Phase 3 auth integration."""
    ...
```

### 4. Include Reversible Operations
Always implement `downgrade()` to revert all changes from `upgrade()`:

- If `upgrade()` creates a table, `downgrade()` must drop it
- If `upgrade()` adds a column, `downgrade()` must remove it
- Ensure the operations are properly ordered (especially for drops and deletes)

### 5. Data-Only Migrations
For data migrations (not schema changes), use raw SQL:

```python
from sqlalchemy import text

def upgrade() -> None:
    """Backfill existing records."""
    op.execute(text("UPDATE compliance_cases SET status = 'draft' WHERE status IS NULL"))

def downgrade() -> None:
    """Restore original state."""
    # Data migrations are typically not reversible; document the limitation
    pass
```

### 6. Handle Constraints Carefully
When removing columns with constraints:
1. Drop foreign keys first
2. Drop indexes
3. Drop the column
4. Reverse the order in `downgrade()`

### 7. Use Descriptive Filenames
Migration filenames should clearly describe the change:

- ✅ `007_add_user_id_to_documents_table.py`
- ❌ `007_changes.py`

## Database Configuration

### Environment Variables

Set the database connection string:

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/tracewise"
```

The DATABASE_URL is automatically converted from async (`postgresql+asyncpg://`) to sync (`postgresql+psycopg://`) format by env.py for Alembic compatibility.

### Supported URL Formats

- `postgresql://user:pass@host:5432/dbname` (standard)
- `postgres://user:pass@host:5432/dbname` (legacy, auto-converted)
- `postgresql+asyncpg://user:pass@host:5432/dbname` (async, converted to psycopg)

## Troubleshooting

### "Connection failed" Error

**Problem**: Database connection error when running alembic commands
**Solution**: Verify DATABASE_URL is set and database is running

```bash
echo $DATABASE_URL
psql $DATABASE_URL -c "SELECT 1"  # Test connection
```

### "No migration history" Error

**Problem**: `alembic_version` table doesn't exist (clean database)
**Solution**: This is normal for new databases. Run `alembic upgrade head` to initialize.

### Circular Import Error

**Problem**: Import errors when running alembic commands
**Solution**: Ensure env.py imports models directly, not via app.db (which has circular dependencies)

### Migration Conflicts

**Problem**: Two migrations with the same revision ID or inconsistent chain
**Solution**: Check the revision chain is linear:

```bash
alembic history --verbose
```

Ensure each migration's `down_revision` matches the previous migration's `revision`.

### Type Mismatch After Migration

**Problem**: Schema created by migration doesn't match ORM models
**Solution**: 
1. Review the migration file for correct column types
2. Verify it matches the ORM model definition
3. Create a new migration to fix the schema if needed

## Integration with Development

### During Development

1. Create models in `app/models/`
2. Create or update migrations
3. Run `alembic upgrade head` to sync database
4. Run tests to verify

### Before Deployment

1. Ensure all migrations are committed
2. Test full migration path: `alembic downgrade base && alembic upgrade head`
3. Verify no uncommitted changes in alembic/
4. Review migration files in pull request

### Production Deployment

1. Backup database before migration
2. Run migrations in maintenance window if possible
3. Monitor migration execution time
4. Verify application can connect after migration
5. Keep downgrade script ready in case of rollback

## Alembic Configuration

### alembic.ini

Main configuration file with important settings:

- `script_location`: Path to alembic scripts directory
- `sqlalchemy.url`: Database URL (override with DATABASE_URL env var)
- `version_path_separator`: Path separator for version locations

### env.py

Environment configuration for running migrations:

- `run_migrations_online()`: Runs migrations with a database connection
- Handles both async and sync database URLs
- Configures logging for migration operations
- Sets up transaction isolation

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy ORM Documentation](https://docs.sqlalchemy.org/en/20/orm/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

## Migration Naming Convention

Migration files follow this pattern:

```
NNN_description_of_change.py
```

Where:
- `NNN`: Zero-padded revision number (001, 002, etc.)
- `description_of_change`: Brief description in snake_case
  - Example: `create_compliance_cases_table`, `add_user_id_column`

## Testing Migrations

Run the migration test suite:

```bash
pytest tests/test_migrations.py -v
```

This validates:
- Migration files are properly structured
- Revision chain is correct
- All required functions exist
- Alembic commands work properly

## Common Tasks

### Add a Column to an Existing Table

```python
def upgrade() -> None:
    """Add email_verified column to users table."""
    op.add_column('users',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'))

def downgrade() -> None:
    """Remove email_verified column from users table."""
    op.drop_column('users', 'email_verified')
```

### Create an Index

```python
def upgrade() -> None:
    """Add index on users.email for faster lookups."""
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

def downgrade() -> None:
    """Remove email index from users table."""
    op.drop_index('ix_users_email', table_name='users')
```

### Add a Foreign Key

```python
def upgrade() -> None:
    """Add user_id foreign key to documents table."""
    op.add_column('documents',
        sa.Column('user_id', sa.Uuid(as_uuid=True), nullable=False))
    op.create_foreign_key('fk_documents_user_id',
        'documents', 'users',
        ['user_id'], ['id'], ondelete='CASCADE')

def downgrade() -> None:
    """Remove user_id foreign key and column."""
    op.drop_constraint('fk_documents_user_id', 'documents')
    op.drop_column('documents', 'user_id')
```

## Support

For issues or questions about migrations:
1. Check this README and the Alembic docs
2. Review existing migrations in `versions/` for examples
3. Run tests: `pytest tests/test_migrations.py -v`
4. Check database connectivity and environment variables
