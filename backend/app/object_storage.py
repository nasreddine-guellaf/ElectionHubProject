"""Adaptateurs de stockage privé. Les clés sont générées par le serveur."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.config import Settings


class StorageError(RuntimeError):
    pass


class ObjectStorage(Protocol):
    provider: str

    def put(self, key: str, content: bytes, media_type: str, metadata: dict[str, str]) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


def safe_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise StorageError("Clé de stockage invalide.")
    return path


@dataclass
class LocalObjectStorage:
    root: Path
    provider: str = "LOCAL"

    def _path(self, key: str) -> Path:
        path = self.root.joinpath(*safe_key(key).parts)
        path.resolve().relative_to(self.root.resolve())
        return path

    def put(self, key: str, content: bytes, media_type: str, metadata: dict[str, str]) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with path.open("xb") as output:
                output.write(content)
            path.chmod(0o600)
        except OSError as exc:
            raise StorageError("Stockage local indisponible.") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except OSError as exc:
            raise StorageError("Objet privé indisponible.") from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Suppression de l'objet impossible.") from exc


@dataclass
class S3ObjectStorage:
    bucket: str
    region: str
    endpoint_url: str | None = None
    provider: str = "S3"

    def __post_init__(self):
        import boto3

        self.client = boto3.client("s3", region_name=self.region, endpoint_url=self.endpoint_url)

    def put(self, key: str, content: bytes, media_type: str, metadata: dict[str, str]) -> None:
        safe_key(key)
        try:
            self.client.upload_fileobj(
                BytesIO(content),
                self.bucket,
                key,
                ExtraArgs={
                    "ContentType": media_type,
                    "ServerSideEncryption": "AES256",
                    "Metadata": metadata,
                },
            )
        except Exception as exc:
            raise StorageError("Stockage S3 indisponible.") from exc

    def get(self, key: str) -> bytes:
        safe_key(key)
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception as exc:
            raise StorageError("Objet privé S3 indisponible.") from exc

    def delete(self, key: str) -> None:
        safe_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StorageError("Suppression S3 impossible.") from exc


def create_object_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == "s3":
        return S3ObjectStorage(
            settings.s3_bucket or "", settings.aws_region, settings.s3_endpoint_url
        )
    return LocalObjectStorage(settings.local_object_directory)
