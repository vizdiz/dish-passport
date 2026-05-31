"""Azure Blob Storage for dish photos (azure-storage-blob). Works against a real storage
account or the local Azurite emulator by connection string alone — the code is identical.
The SDK is imported lazily.

Presigned upload = a blob SAS URL with create/write permission; the client PUTs bytes straight
to Blob storage with `x-ms-blob-type: BlockBlob`. Those required headers travel in the presign
response so the client never learns it's talking to Azure.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.ports import PresignedUpload

ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def _parse_connection_string(cs: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in cs.split(";") if "=" in part)


class AzureBlobStorage:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        parts = _parse_connection_string(settings.azure_storage_connection_string)
        self._account = parts["AccountName"]
        self._key = parts["AccountKey"]
        self._blob_endpoint = (
            parts.get("BlobEndpoint")
            or f"{parts.get('DefaultEndpointsProtocol', 'https')}://{self._account}.blob.core.windows.net"
        ).rstrip("/")
        self._container = settings.azure_storage_container

    def presign_put(self, key: str, content_type: str, expires: int = 3600) -> PresignedUpload:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        sas = generate_blob_sas(
            account_name=self._account,
            container_name=self._container,
            blob_name=key,
            account_key=self._key,
            permission=BlobSasPermissions(create=True, write=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expires),
        )
        return PresignedUpload(
            url=f"{self._blob_endpoint}/{self._container}/{key}?{sas}",
            headers={"x-ms-blob-type": "BlockBlob", "Content-Type": content_type},
        )

    def public_url(self, key: str) -> str:
        base = (self._s.azure_blob_public_base or self._blob_endpoint).rstrip("/")
        return f"{base}/{self._container}/{key}"
