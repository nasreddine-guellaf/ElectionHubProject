import re
import ssl
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

    app_env: Literal["local", "test", "cloud"] = "local"
    session_ttl_seconds: int = Field(default=3600, ge=300, le=86400)
    citizen_otp_enabled: bool = False
    otp_hmac_key: SecretStr | None = None
    mock_sms_directory: Path = ROOT / ".local/sms"
    otp_delivery_backend: Literal["local", "lambda"] = "local"
    otp_lambda_function_arn: str = ""
    otp_lambda_recipient_refs: dict[str, str] = Field(default_factory=dict)
    object_storage_backend: Literal["local", "s3"] = "local"
    local_object_directory: Path = ROOT / ".local/objects"
    object_upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    aws_region: str = "eu-north-1"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    postgres_user: str = "electionhub"
    postgres_password: SecretStr
    postgres_db: str = "electionhub"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5433, ge=1, le=65535)
    postgres_sslmode: Literal[
        "disable", "allow", "prefer", "require", "verify-ca", "verify-full"
    ] = "disable"
    postgres_sslrootcert: Path | None = None
    postgres_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    postgres_pool_size: int = Field(default=5, ge=1, le=20)
    postgres_max_overflow: int = Field(default=5, ge=0, le=20)
    postgres_pool_timeout_seconds: int = Field(default=5, ge=1, le=60)
    postgres_pool_recycle_seconds: int = Field(default=300, ge=30, le=3600)

    @model_validator(mode="after")
    def validate_otp(self):
        if self.citizen_otp_enabled and (
            self.otp_hmac_key is None or len(self.otp_hmac_key.get_secret_value()) < 32
        ):
            raise ValueError("La simulation OTP exige un secret HMAC d'au moins 32 caractères.")
        if self.otp_delivery_backend == "lambda":
            arn = r"arn:aws:lambda:[a-z0-9-]+:[0-9]{12}:function:[A-Za-z0-9_-]{1,64}"
            if not re.fullmatch(arn + r"(?::[A-Za-z0-9_-]{1,128})?", self.otp_lambda_function_arn):
                raise ValueError("OTP_LAMBDA_FUNCTION_ARN doit contenir un ARN Lambda complet.")
            if not self.otp_lambda_recipient_refs or any(
                not recipient or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", ref)
                for recipient, ref in self.otp_lambda_recipient_refs.items()
            ):
                raise ValueError("OTP_LAMBDA_RECIPIENT_REFS doit associer des références valides.")
        if self.object_storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET est obligatoire lorsque le stockage S3 est activé.")
        rds_host = self.postgres_host.lower().endswith(
            (".rds.amazonaws.com", ".rds.amazonaws.com.cn")
        )
        if (self.app_env == "cloud" or rds_host) and self.postgres_sslmode != "verify-full":
            raise ValueError("RDS et APP_ENV=cloud exigent POSTGRES_SSLMODE=verify-full.")
        if self.postgres_sslmode in {"verify-ca", "verify-full"}:
            if self.postgres_sslrootcert is None:
                raise ValueError(
                    "POSTGRES_SSLROOTCERT est obligatoire pour verify-ca et verify-full."
                )
            root_cert = self.postgres_sslrootcert
            if not root_cert.is_absolute():
                root_cert = (ROOT / root_cert).resolve()
            if not root_cert.is_file():
                raise ValueError("POSTGRES_SSLROOTCERT doit pointer vers un fichier CA existant.")
            try:
                ssl.create_default_context(cafile=str(root_cert))
            except (OSError, ssl.SSLError) as exc:
                raise ValueError("POSTGRES_SSLROOTCERT ne contient pas une CA valide.") from exc
            self.postgres_sslrootcert = root_cert
        elif self.postgres_sslrootcert is not None:
            raise ValueError(
                "POSTGRES_SSLROOTCERT ne doit être configuré qu'avec verify-ca ou verify-full."
            )
        return self

    @field_validator("postgres_sslrootcert", mode="before")
    @classmethod
    def normalize_empty_root_cert(cls, value):
        return None if value in (None, "") else value

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
