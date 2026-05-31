"""Integration smoke for photo storage against real MinIO (S3-compatible). Ensures the bucket
exists, presigns a PUT, uploads bytes through the presigned URL, and confirms the object
landed. No AWS account needed.

    docker compose up -d minio
    DP_DATABASE_URL=... PYTHONPATH=. python scripts/smoke_storage.py
"""
from __future__ import annotations

import time
import urllib.request

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, EndpointConnectionError

from app.config import Settings
from app.services.storage import S3Storage


def main() -> None:
    s = Settings()
    raw = boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    # MinIO may take a moment to accept connections after `docker compose up`.
    for attempt in range(20):
        try:
            buckets = [b["Name"] for b in raw.list_buckets().get("Buckets", [])]
            break
        except (EndpointConnectionError, ConnectionError):
            time.sleep(1)
    else:
        raise SystemExit("MinIO not reachable at " + str(s.s3_endpoint_url))
    if s.s3_bucket not in buckets:
        raw.create_bucket(Bucket=s.s3_bucket)
        print(f"created bucket {s.s3_bucket!r}")
    else:
        print(f"bucket {s.s3_bucket!r} exists")

    storage = S3Storage(s)
    key = "photos/smoke-test.jpg"
    upload_url = storage.presign_put(key, "image/jpeg")
    payload = b"\xff\xd8\xff\xe0\x00\x10JFIF-fake-jpeg-bytes-for-smoke"

    req = urllib.request.Request(
        upload_url, data=payload, method="PUT", headers={"Content-Type": "image/jpeg"}
    )
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (local MinIO)
        print(f"presigned PUT -> HTTP {resp.status}")
        assert 200 <= resp.status < 300

    try:
        head = raw.head_object(Bucket=s.s3_bucket, Key=key)
    except ClientError as exc:  # pragma: no cover
        raise AssertionError(f"object not found after PUT: {exc}") from exc

    print(f"object stored: {head['ContentLength']} bytes  public_url={storage.public_url(key)}")
    assert head["ContentLength"] == len(payload)
    print("\nSTORAGE SMOKE OK — presign -> upload -> object verified on MinIO.")


if __name__ == "__main__":
    main()
