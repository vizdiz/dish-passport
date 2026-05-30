from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_repo
from app.ports import DishRepository
from app.schemas import DishOut, SimilarNeighbor, SimilarResponse
from app.services.errors import DishNotFound
from app.services.similarity import similar_dishes

router = APIRouter(tags=["dishes"])


@router.get("/dishes/{dish_id}", response_model=DishOut)
async def get_dish(
    dish_id: int,
    repo: DishRepository = Depends(get_repo),
) -> DishOut:
    dish = await repo.get_dish(dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail=f"dish {dish_id} not found")
    return DishOut.from_record(dish)


@router.get("/dishes/{dish_id}/similar", response_model=SimilarResponse)
async def get_similar(
    dish_id: int,
    n: int = Query(default=10, ge=1, le=50),
    repo: DishRepository = Depends(get_repo),
) -> SimilarResponse:
    """Pure big-vector cosine neighbors (Service 2). Self excluded, ranked by cosine."""
    try:
        neighbors = await similar_dishes(repo, dish_id, n)
    except DishNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return SimilarResponse(
        dish_id=dish_id,
        n=n,
        neighbors=[
            SimilarNeighbor(dish=DishOut.from_record(nb.dish), cosine=nb.cosine)
            for nb in neighbors
        ],
    )
