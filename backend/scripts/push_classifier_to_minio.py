"""Push trained classifier artifacts to MinIO.

One-shot developer script. Run from backend/ after training:

    uv run python scripts/push_classifier_to_minio.py

Reads MinIO credentials from `.env` (developer-side). Uploads:
  - classifier.pt           -> classifier-artifacts/v1/classifier.pt
  - tokenizer/*             -> classifier-artifacts/v1/tokenizer/*
  - model_card.json         -> classifier-artifacts/v1/model_card.json

The prefix "v1" exists so we can publish v2 later without overwriting the
running modelserver's bytes mid-flight.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from minio import Minio
from minio.error import S3Error

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("push_classifier_to_minio")

# Configuration — from .env when run on the host
# (running on the host, we hit localhost:9000, not 'minio:9000')
MINIO_ENDPOINT = os.environ.get("MINIO_HOST_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin-dev-pw")
BUCKET = "classifier-artifacts"
VERSION_PREFIX = "v1"

ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "data" / "classifier_artifacts"


def _ensure_bucket(client: Minio, bucket: str) -> None:
    """Create the bucket if it doesn't exist."""
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("created bucket %s", bucket)
        else:
            logger.info("bucket %s already exists", bucket)
    except S3Error as exc:
        logger.error("failed to verify/create bucket %s: %s", bucket, exc)
        sys.exit(1)


def _upload_file(client: Minio, local: Path, key: str) -> None:
    full_key = f"{VERSION_PREFIX}/{key}"
    client.fput_object(BUCKET, full_key, str(local))
    logger.info("uploaded %s -> %s/%s", local.name, BUCKET, full_key)


def main() -> None:
    if not ARTIFACT_DIR.exists():
        logger.error("artifact dir not found: %s", ARTIFACT_DIR)
        logger.error("run notebooks/01_train_classifier.ipynb first")
        sys.exit(1)

    for required in ("classifier.pt", "tokenizer", "model_card.json"):
        if not (ARTIFACT_DIR / required).exists():
            logger.error("missing artifact: %s", ARTIFACT_DIR / required)
            sys.exit(1)

    logger.info("connecting to minio at %s", MINIO_ENDPOINT)
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )

    _ensure_bucket(client, BUCKET)

    _upload_file(client, ARTIFACT_DIR / "classifier.pt", "classifier.pt")
    _upload_file(client, ARTIFACT_DIR / "model_card.json", "model_card.json")

    # Upload the tokenizer directory contents.
    tokenizer_dir = ARTIFACT_DIR / "tokenizer"
    for f in sorted(tokenizer_dir.iterdir()):
        if f.is_file():
            _upload_file(client, f, f"tokenizer/{f.name}")

    logger.info("\ndone — artifacts at %s/%s/", BUCKET, VERSION_PREFIX)


if __name__ == "__main__":
    main()
