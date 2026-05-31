"""Integration smoke for photo storage against local Azurite (Azure Blob emulator). Ensures
the container exists, mints a SAS PUT URL, uploads bytes through it, and confirms the blob
landed. No Azure account needed.

    docker compose up -d azurite
    DP_DATABASE_URL=... PYTHONPATH=. python scripts/smoke_storage.py
"""
from __future__ import annotations

import time
import urllib.request

from azure.core.exceptions import ResourceExistsError, ServiceRequestError
from azure.storage.blob import BlobServiceClient

from app.config import Settings
from app.services.storage import AzureBlobStorage


def main() -> None:
    s = Settings()
    svc = BlobServiceClient.from_connection_string(s.azure_storage_connection_string)

    # Azurite may take a moment to accept connections; retry container creation until ready.
    for _ in range(20):
        try:
            try:
                svc.create_container(s.azure_storage_container, public_access="blob")
                print(f"created container {s.azure_storage_container!r}")
            except ResourceExistsError:
                print(f"container {s.azure_storage_container!r} exists")
            break
        except ServiceRequestError:
            time.sleep(1)
    else:
        raise SystemExit("Azurite not reachable")

    storage = AzureBlobStorage(s)
    key = "photos/smoke-test.jpg"
    upload = storage.presign_put(key, "image/jpeg")
    payload = b"\xff\xd8\xff\xe0\x00\x10JFIF-fake-jpeg-bytes-for-smoke"

    req = urllib.request.Request(upload.url, data=payload, method="PUT", headers=upload.headers)
    with urllib.request.urlopen(req) as resp:  # noqa: S310 (local Azurite)
        print(f"SAS PUT -> HTTP {resp.status}")
        assert 200 <= resp.status < 300

    props = svc.get_blob_client(s.azure_storage_container, key).get_blob_properties()
    print(f"blob stored: {props.size} bytes  public_url={storage.public_url(key)}")
    assert props.size == len(payload)
    print("\nSTORAGE SMOKE OK — SAS presign -> upload -> blob verified on Azurite.")


if __name__ == "__main__":
    main()
