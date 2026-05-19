"""MinIO adapter — typed wrapper around the SDK for the rest of the app.

Layer: app/infra/
Used by: modelserver startup to fetch classifier artifacts.

Mirrors the pattern in app/infra/vault.py: a single typed init function,
no SDK leakage into services or routers.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from minio import Minio
from minio.error import S3Error

if TYPE_CHECKING:
    from app.infra.vault import MinioSecrets

logger = logging.getLogger(__name__)


class ObjectStorageError(RuntimeError):
    """Object storage operation failed."""


def build_client(secrets: MinioSecrets) -> Minio:
    """Construct a MinIO client from typed secrets.

    MinIO endpoint in dev is HTTP, not HTTPS. The `secure=False` is
    correct for the in-compose deployment.
    """
    # Strip protocol; the SDK wants host:port only.
    endpoint = secrets.endpoint.replace("http://", "").replace("https://", "")
    return Minio(
        endpoint=endpoint,
        access_key=secrets.access_key,
        secret_key=secrets.secret_key,
        secure=secrets.endpoint.startswith("https://"),
    )


def download_object(
    client: Minio,
    bucket: str,
    object_name: str,
    destination: Path,
) -> None:
    """Download one object to a local path, creating parent dirs."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        client.fget_object(bucket, object_name, str(destination))
    except S3Error as exc:
        raise ObjectStorageError(f"Failed to download {bucket}/{object_name}: {exc}") from exc
    logger.info("downloaded %s/%s -> %s", bucket, object_name, destination)


def download_prefix(
    client: Minio,
    bucket: str,
    prefix: str,
    destination_dir: Path,
) -> int:
    """Download every object under a prefix into a local directory.

    Returns the number of objects downloaded.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
            relative = obj.object_name[len(prefix) :].lstrip("/")
            dest = destination_dir / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            client.fget_object(bucket, obj.object_name, str(dest))
            count += 1
    except S3Error as exc:
        raise ObjectStorageError(f"Failed to list/download {bucket}/{prefix}*: {exc}") from exc
    logger.info("downloaded %d objects from %s/%s -> %s", count, bucket, prefix, destination_dir)
    return count


def sha256_of_file(path: Path) -> str:
    """Compute SHA-256 of a file. Used to verify downloaded artifacts."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
