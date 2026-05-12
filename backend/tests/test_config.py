import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


class TestSettingsValidation:
    """Test configuration validation."""

    def test_database_url_required(self):
        """Database URL must be provided and valid."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(DATABASE_URL="")
        assert "DATABASE_URL" in str(exc_info.value)

    def test_database_url_must_start_with_postgresql(self):
        """Database URL must start with postgresql://."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(DATABASE_URL="mysql://user:pass@localhost:3306/db")
        assert "postgresql://" in str(exc_info.value)

    def test_valid_database_url(self):
        """Valid PostgreSQL URL should pass validation."""
        settings = Settings(
            DATABASE_URL="postgresql://user:pass@localhost:5432/testdb"
        )
        assert settings.DATABASE_URL == "postgresql://user:pass@localhost:5432/testdb"

    def test_log_level_validation(self, monkeypatch):
        """Log level must be one of valid values."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings(LOG_LEVEL="INVALID")
        assert "LOG_LEVEL" in str(exc_info.value)

    def test_valid_log_levels(self, monkeypatch):
        """All valid log levels should be accepted."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(LOG_LEVEL=level)
            assert settings.LOG_LEVEL == level

    def test_environment_validation(self, monkeypatch):
        """Environment must be one of: development, test, production."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings(ENVIRONMENT="staging")
        assert "ENVIRONMENT" in str(exc_info.value)

    def test_valid_environments(self, monkeypatch):
        """All valid environments should be accepted."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        for env in ["development", "test", "production"]:
            settings = Settings(ENVIRONMENT=env)
            assert settings.ENVIRONMENT == env

    def test_api_port_validation(self, monkeypatch):
        """API port must be between 1024 and 65535."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        with pytest.raises(ValidationError):
            Settings(API_PORT=80)  # Too low
        with pytest.raises(ValidationError):
            Settings(API_PORT=99999)  # Too high

    def test_valid_api_port(self, monkeypatch):
        """Valid API port should be accepted."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings(API_PORT=8000)
        assert settings.API_PORT == 8000


class TestSettingsDefaults:
    """Test configuration default values."""

    def test_default_environment(self, monkeypatch):
        """Default environment should be development."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings()
        assert settings.ENVIRONMENT == "development"

    def test_default_log_level(self, monkeypatch):
        """Default log level should be INFO."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings()
        assert settings.LOG_LEVEL == "INFO"

    def test_default_api_port(self, monkeypatch):
        """Default API port should be 8000."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings()
        assert settings.API_PORT == 8000

    def test_default_api_host(self, monkeypatch):
        """Default API host should be 0.0.0.0."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings()
        assert settings.API_HOST == "0.0.0.0"

    def test_default_cors_origins(self, monkeypatch):
        """Default CORS origins should be localhost:4200."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings()
        assert settings.CORS_ORIGINS == "http://localhost:4200"

    def test_default_redis_url(self, monkeypatch):
        """Default Redis URL can be overridden."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("REDIS_URL", "redis://custom:6379")
        settings = Settings()
        assert settings.REDIS_URL == "redis://custom:6379"


class TestCORSOriginsParsing:
    """Test CORS origins parsing and validation."""

    def test_single_origin(self, monkeypatch):
        """Single CORS origin should parse correctly."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings(CORS_ORIGINS="http://localhost:4200")
        origins = settings.get_cors_origins_list()
        assert origins == ["http://localhost:4200"]

    def test_multiple_origins(self, monkeypatch):
        """Multiple CORS origins should parse correctly."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings(
            CORS_ORIGINS="http://localhost:4200,https://example.com,https://app.example.com"
        )
        origins = settings.get_cors_origins_list()
        assert origins == [
            "http://localhost:4200",
            "https://example.com",
            "https://app.example.com",
        ]

    def test_origins_with_whitespace(self, monkeypatch):
        """CORS origins with whitespace should be trimmed."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings(CORS_ORIGINS="http://localhost:4200 , https://example.com")
        origins = settings.get_cors_origins_list()
        assert origins == ["http://localhost:4200", "https://example.com"]

    def test_cors_wildcard_rejected(self, monkeypatch):
        """CORS wildcard '*' should be rejected for security."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings(CORS_ORIGINS="*")
        assert "Wildcard" in str(exc_info.value)

    def test_cors_http_origin_in_production_allowed(self, monkeypatch):
        """CORS http://localhost is allowed in dev."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        settings = Settings(CORS_ORIGINS="http://localhost:4200")
        assert settings.CORS_ORIGINS == "http://localhost:4200"

    def test_cors_https_required_for_non_localhost(self, monkeypatch):
        """CORS origins must be https:// unless localhost."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        with pytest.raises(ValidationError) as exc_info:
            Settings(CORS_ORIGINS="http://example.com")
        assert "https://" in str(exc_info.value)


class TestGetSettings:
    """Test get_settings caching."""

    def test_get_settings_returns_instance(self, monkeypatch):
        """get_settings should return a Settings instance."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        # Clear the cache first
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_caching(self, monkeypatch):
        """get_settings should cache the same instance."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        # Clear the cache first
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2


class TestEnvironmentSpecificDefaults:
    """Test environment-specific behavior."""

    def test_development_defaults(self, monkeypatch):
        """Development environment should have appropriate defaults."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("ENVIRONMENT", "development")
        settings = Settings()
        assert settings.ENVIRONMENT == "development"

    def test_production_defaults(self, monkeypatch):
        """Production environment should have appropriate defaults."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("ENVIRONMENT", "production")
        settings = Settings()
        assert settings.ENVIRONMENT == "production"

    def test_test_defaults(self, monkeypatch):
        """Test environment should have appropriate defaults."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("ENVIRONMENT", "test")
        settings = Settings()
        assert settings.ENVIRONMENT == "test"
