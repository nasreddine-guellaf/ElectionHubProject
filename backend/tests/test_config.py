from pathlib import Path

import certifi
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


def test_local_postgres_keeps_tls_disabled_by_default():
    settings = Settings(_env_file=None, postgres_password="test-only-long-password")

    assert settings.postgres_sslmode == "disable"
    assert settings.postgres_sslrootcert is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"app_env": "cloud"}, "verify-full"),
        (
            {"postgres_host": "electionhub.example.eu-north-1.rds.amazonaws.com"},
            "verify-full",
        ),
        ({"postgres_sslmode": "verify-full"}, "POSTGRES_SSLROOTCERT"),
    ],
)
def test_cloud_and_rds_fail_closed_without_verified_tls(overrides, message):
    with pytest.raises(ValidationError, match=message):
        Settings(
            _env_file=None,
            postgres_password="test-only-long-password",
            **overrides,
        )


def test_tls_rejects_missing_ca_file(tmp_path):
    with pytest.raises(ValidationError, match="fichier CA existant"):
        Settings(
            _env_file=None,
            postgres_password="test-only-long-password",
            postgres_sslmode="verify-full",
            postgres_sslrootcert=tmp_path / "missing.pem",
        )


def test_tls_rejects_invalid_ca_file(tmp_path):
    invalid = tmp_path / "invalid.pem"
    invalid.write_text("not a certificate", encoding="utf-8")

    with pytest.raises(ValidationError, match="CA valide"):
        Settings(
            _env_file=None,
            postgres_password="test-only-long-password",
            postgres_sslmode="verify-full",
            postgres_sslrootcert=invalid,
        )


def test_rds_accepts_verify_full_with_valid_ca_bundle():
    settings = Settings(
        _env_file=None,
        app_env="cloud",
        postgres_password="test-only-long-password",
        postgres_host="electionhub.example.eu-north-1.rds.amazonaws.com",
        postgres_sslmode="verify-full",
        postgres_sslrootcert=certifi.where(),
    )

    assert settings.postgres_sslrootcert == Path(certifi.where()).resolve()


def test_root_certificate_is_rejected_when_verification_is_disabled():
    with pytest.raises(ValidationError, match="verify-ca ou verify-full"):
        Settings(
            _env_file=None,
            postgres_password="test-only-long-password",
            postgres_sslmode="disable",
            postgres_sslrootcert=certifi.where(),
        )
