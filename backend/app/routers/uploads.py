from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends

from app.deps import get_current_user, get_storage
from app.ports import Storage
from app.schemas import PresignRequest, PresignResponse
from app.services.storage import ALLOWED_CONTENT_TYPES

router = APIRouter(tags=["uploads"])


@router.post("/uploads/presign", response_model=PresignResponse)
async def presign_upload(
    body: PresignRequest,
    user_id: int = Depends(get_current_user),
    storage: Storage = Depends(get_storage),
) -> PresignResponse:
    """Mint a presigned PUT URL for a dish photo. The client uploads straight to S3, then
    sends the returned public_url as `photo_url` on POST /logs."""
    ext = ALLOWED_CONTENT_TYPES[body.content_type]
    key = f"photos/{uuid4().hex}.{ext}"
    upload = storage.presign_put(key, body.content_type)
    return PresignResponse(
        upload_url=upload.url,
        public_url=storage.public_url(key),
        key=key,
        headers=upload.headers,
    )
