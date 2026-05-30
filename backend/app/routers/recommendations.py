from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.deps import get_repo
from app.ports import DishRepository
from app.schemas import DishOut, RecommendationOut, RecommendationsResponse
from app.services.recommend import recommend

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    user_id: int = Query(...),
    n: int = Query(default=10, ge=1, le=50),
    repo: DishRepository = Depends(get_repo),
) -> RecommendationsResponse:
    result = await recommend(repo, user_id, n)
    return RecommendationsResponse(
        user_id=user_id,
        n=n,
        cold_start=result.cold_start,
        recommendations=[
            RecommendationOut(
                dish=DishOut.from_record(r.dish),
                score=r.score,
                explanation=r.explanation,
                components=r.components,
            )
            for r in result.recommendations
        ],
    )
