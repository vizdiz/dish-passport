from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import get_current_user, get_repo
from app.ports import DishRepository
from app.schemas import DishOut, FactorScore, SimilarNeighbor, SimilarResponse
from app.services.errors import DishNotFound
from app.services.flavor_svd import project
from app.services.similarity import similar_dishes

router = APIRouter(tags=["dishes"])


@router.get("/dishes/{dish_id}", response_model=DishOut)
async def get_dish(
    dish_id: int,
    _user: int = Depends(get_current_user),
    repo: DishRepository = Depends(get_repo),
) -> DishOut:
    dish = await repo.get_dish(dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail=f"dish {dish_id} not found")
    out = DishOut.from_record(dish)

    # Service 3: project into the latest flavor-factor space (no refit). Null until one exists.
    model = await repo.get_latest_svd_model()
    if model is not None:
        values = project(dish.flavor, model)
        out.factors = [
            FactorScore(label=label, value=round(v, 4))
            for label, v in zip(model.factor_labels, values)
        ]
        out.svd_model_version = model.version
    return out


@router.get("/dishes/{dish_id}/similar", response_model=SimilarResponse)
async def get_similar(
    dish_id: int,
    n: int = Query(default=10, ge=1, le=50),
    _user: int = Depends(get_current_user),
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
