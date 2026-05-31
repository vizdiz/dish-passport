"""S3-compatible object storage for dish photos (boto3). Works against AWS S3 or local MinIO
by flipping config — the code is identical. boto3 is imported lazily.

Presigned PUT means the client uploads bytes straight to S3; the API never proxies the image.
Path-style addressing is used so `http://localhost:9000/<bucket>/<key>` works with MinIO.
"""
from __future__ import annotations

from app.config import Settings

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._client = None  # boto3 client, built lazily

    def _ensure_client(self):
        if self._client is None:
            import boto3
            from botocore.config import Config as BotoConfig

            self._client = boto3.client(
                "s3",
                endpoint_url=self._s.s3_endpoint_url or None,
                aws_access_key_id=self._s.s3_access_key,
                aws_secret_access_key=self._s.s3_secret_key,
                region_name=self._s.s3_region,
                config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    def presign_put(self, key: str, content_type: str, expires: int = 3600) -> str:
        return self._ensure_client().generate_presigned_url(
            "put_object",
            Params={"Bucket": self._s.s3_bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires,
        )

    def public_url(self, key: str) -> str:
        base = (self._s.s3_public_url_base or self._s.s3_endpoint_url or "").rstrip("/")
        return f"{base}/{self._s.s3_bucket}/{key}"
