from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # Déploiement distant/TLS à préparer dans les phases cloud.
    app_env: Literal["local", "test", "cloud"] = "local"
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    citizen_otp_enabled: bool = False
    otp_hmac_key: SecretStr | None = None
    mock_sms_directory: Path = ROOT / ".local/sms"
    object_storage_backend: Literal["local", "s3"] = "local"
    local_object_directory: Path = ROOT / ".local/objects"
    object_upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    aws_region: str = "eu-west-3"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    postgres_user: str = "electionhub"
    postgres_password: SecretStr
    postgres_db: str = "electionhub"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5433, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_otp(self):
        if self.citizen_otp_enabled and (
            self.otp_hmac_key is None or len(self.otp_hmac_key.get_secret_value()) < 32
        ):
            raise ValueError("La simulation OTP exige un secret HMAC d'au moins 32 caractères.")
        if self.object_storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET est obligatoire lorsque le stockage S3 est activé.")
        return self

    @field_validator("postgres_password")
    @classmethod
    def require_configured_password(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16 or value.get_secret_value().startswith("replace-"):
            raise ValueError("Générez un mot de passe local d'au moins 16 caractères.")
        return value

    @property
    def database_url(self) -> URL:
        # URL.create échappe correctement les caractères réservés du mot de passe.
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
