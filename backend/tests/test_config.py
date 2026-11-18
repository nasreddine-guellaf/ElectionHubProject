import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("password", ["", "short", "replace-with-generated-local-password"])
def test_placeholder_password_is_rejected(password):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password=password)


def test_url_preserves_special_password_characters():
    password = "test-only:@/special%characters"
    settings = Settings(_env_file=None, postgres_password=password)
    assert settings.database_url.password == password
    assert password not in repr(settings)
    assert password not in str(settings.database_url)


def test_local_scaffold_rejects_production_mode():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", postgres_password="test-only-long-password")


def test_otp_requires_hmac_secret():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            citizen_otp_enabled=True,
            otp_hmac_key="short",
            postgres_password="test-only-long-password",
        )
