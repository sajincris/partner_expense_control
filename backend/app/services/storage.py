"""Document storage abstraction.

``LocalStorage`` is used for the MVP. ``S3Storage`` shows the extension point:
swap via STORAGE_BACKEND=s3 without touching business code.
"""
import hashlib
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import settings
from app.core.errors import ValidationFailedError


class StorageBackend(Protocol):
    def save(self, data: bytes, *, filename: str, content_type: str) -> str: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValidationFailedError("Invalid storage key.")
        return path

    def save(self, data: bytes, *, filename: str, content_type: str) -> str:
        suffix = Path(filename).suffix.lower()[:10]
        key = f"{uuid.uuid4().hex[:2]}/{uuid.uuid4().hex}{suffix}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:  # pragma: no cover - extension point
    def __init__(self, bucket: str):
        import boto3  # imported lazily: not an MVP dependency

        self.bucket = bucket
        self.client = boto3.client("s3")

    def save(self, data: bytes, *, filename: str, content_type: str) -> str:
        key = f"attachments/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")
        return key

    def open(self, key: str) -> BinaryIO:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _storage
    if _storage is None:
        _storage = S3Storage(settings.STORAGE_S3_BUCKET) if settings.STORAGE_BACKEND == "s3" else LocalStorage(settings.STORAGE_LOCAL_PATH)
    return _storage


def validate_upload(data: bytes, content_type: str) -> str:
    if not data:
        raise ValidationFailedError("Empty file.")
    if len(data) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise ValidationFailedError(f"File exceeds {settings.MAX_UPLOAD_MB} MB.")
    if content_type not in settings.allowed_upload_types:
        raise ValidationFailedError("File type not allowed.", details={"allowed": sorted(settings.allowed_upload_types)})
    return hashlib.sha256(data).hexdigest()
