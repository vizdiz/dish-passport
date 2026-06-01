from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_current_user, get_repo
from app.ports import DishRepository, ImpressionRow
from app.schemas import ImpressionIn, ImpressionsResponse

router = APIRouter(tags=["impressions"])


@router.post("/impressions", response_model=ImpressionsResponse)
async def ingest_impressions(
    body: list[ImpressionIn],
    user_id: int = Depends(get_current_user),
    repo: DishRepository = Depends(get_repo),
) -> ImpressionsResponse:
    # user_id is stamped from the authenticated token, never trusted from the client.
    rows = [
        ImpressionRow(
            user_id=user_id,
            dish_id=i.dish_id,
            shown_at=i.shown_at,
            context=i.context,
            converted=i.converted,
        )
        for i in body
    ]
    n = await repo.insert_impressions(rows)
    return ImpressionsResponse(ingested=n)
