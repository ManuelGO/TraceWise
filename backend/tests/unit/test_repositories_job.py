"""Unit tests for JobRepository."""

from app.db.repositories.job import JobRepository
from app.models import Job


class TestJobRepositoryInitialization:
    """Tests for JobRepository initialization and configuration."""

    def test_repository_has_filterable_fields(self):
        """Test that JobRepository defines FILTERABLE_FIELDS."""
        repo = JobRepository()
        assert hasattr(repo, "FILTERABLE_FIELDS")
        assert repo.FILTERABLE_FIELDS == {"case_id", "status", "job_type"}

    def test_repository_has_protected_fields(self):
        """Test that JobRepository has PROTECTED_FIELDS from BaseRepository."""
        repo = JobRepository()
        assert hasattr(repo, "PROTECTED_FIELDS")
        assert repo.PROTECTED_FIELDS == {"id", "created_at", "updated_at"}

    def test_repository_model_is_job(self):
        """Test that repository is initialized with Job model."""
        repo = JobRepository()
        assert repo.model == Job

    def test_repository_inherits_from_base_repository(self):
        """Test that JobRepository inherits from BaseRepository."""
        from app.db.repository import BaseRepository

        repo = JobRepository()
        assert isinstance(repo, BaseRepository)


class TestJobRepositoryFilterFields:
    """Tests for allowed filter fields configuration."""

    def test_case_id_is_filterable(self):
        """Test that case_id is in FILTERABLE_FIELDS."""
        repo = JobRepository()
        assert "case_id" in repo.FILTERABLE_FIELDS

    def test_status_is_filterable(self):
        """Test that status is in FILTERABLE_FIELDS."""
        repo = JobRepository()
        assert "status" in repo.FILTERABLE_FIELDS

    def test_job_type_is_filterable(self):
        """Test that job_type is in FILTERABLE_FIELDS."""
        repo = JobRepository()
        assert "job_type" in repo.FILTERABLE_FIELDS

    def test_id_is_not_filterable(self):
        """Test that id is NOT in FILTERABLE_FIELDS (use read() instead)."""
        repo = JobRepository()
        assert "id" not in repo.FILTERABLE_FIELDS

    def test_error_message_is_not_filterable(self):
        """Test that error_message is NOT filterable."""
        repo = JobRepository()
        assert "error_message" not in repo.FILTERABLE_FIELDS

    def test_metadata_is_not_filterable(self):
        """Test that metadata is NOT filterable."""
        repo = JobRepository()
        assert "metadata" not in repo.FILTERABLE_FIELDS


class TestJobRepositoryProtectedFields:
    """Tests for protected field enforcement."""

    def test_protected_fields_include_id(self):
        """Test that id is protected."""
        repo = JobRepository()
        assert "id" in repo.PROTECTED_FIELDS

    def test_protected_fields_include_created_at(self):
        """Test that created_at is protected."""
        repo = JobRepository()
        assert "created_at" in repo.PROTECTED_FIELDS

    def test_protected_fields_include_updated_at(self):
        """Test that updated_at is protected."""
        repo = JobRepository()
        assert "updated_at" in repo.PROTECTED_FIELDS

    def test_protected_fields_immutable(self):
        """Test that PROTECTED_FIELDS is a set of exactly 3 fields."""
        repo = JobRepository()
        assert len(repo.PROTECTED_FIELDS) == 3
        assert {"id", "created_at", "updated_at"} == repo.PROTECTED_FIELDS


class TestJobRepositorySpecializedMethods:
    """Tests for JobRepository specialized query methods (without DB)."""

    def test_find_by_case_method_exists(self):
        """Test that find_by_case method exists."""
        repo = JobRepository()
        assert hasattr(repo, "find_by_case")
        assert callable(repo.find_by_case)

    def test_find_pending_jobs_method_exists(self):
        """Test that find_pending_jobs method exists."""
        repo = JobRepository()
        assert hasattr(repo, "find_pending_jobs")
        assert callable(repo.find_pending_jobs)

    def test_find_by_case_signature(self):
        """Test that find_by_case has correct parameters."""
        import inspect

        repo = JobRepository()
        sig = inspect.signature(repo.find_by_case)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "case_id" in params

    def test_find_pending_jobs_signature(self):
        """Test that find_pending_jobs has correct parameters."""
        import inspect

        repo = JobRepository()
        sig = inspect.signature(repo.find_pending_jobs)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "skip" in params or "limit" in params


class TestJobRepositoryInheritedMethods:
    """Tests for inherited BaseRepository methods."""

    def test_create_method_exists(self):
        """Test that create method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "create")
        assert callable(repo.create)

    def test_read_method_exists(self):
        """Test that read method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "read")
        assert callable(repo.read)

    def test_update_method_exists(self):
        """Test that update method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "update")
        assert callable(repo.update)

    def test_delete_method_exists(self):
        """Test that delete method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "delete")
        assert callable(repo.delete)

    def test_list_method_exists(self):
        """Test that list method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "list")
        assert callable(repo.list)

    def test_list_by_filter_method_exists(self):
        """Test that list_by_filter method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "list_by_filter")
        assert callable(repo.list_by_filter)

    def test_count_method_exists(self):
        """Test that count method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "count")
        assert callable(repo.count)

    def test_exists_method_exists(self):
        """Test that exists method is inherited."""
        repo = JobRepository()
        assert hasattr(repo, "exists")
        assert callable(repo.exists)
