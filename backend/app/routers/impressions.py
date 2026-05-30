from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_repo
from app.ports import DishRepository, ImpressionRow
from app.schemas import ImpressionIn, ImpressionsResponse

router = APIRouter(tags=["impressions"])


@router.post("/impressions", response_model=ImpressionsResponse)
async def ingest_impressions(
    body: list[ImpressionIn],
    repo: DishRepository = Depends(get_repo),
) -> ImpressionsResponse:
    rows = [
        ImpressionRow(
            user_id=i.user_id,
            dish_id=i.dish_id,
            shown_at=i.shown_at,
            context=i.context,
            converted=i.converted,
        )
        for i in body
    ]
    n = await repo.insert_impressions(rows)
    return ImpressionsResponse(ingested=n)
