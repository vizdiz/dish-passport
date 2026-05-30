from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_repo
from app.ports import DishRepository
from app.schemas import DishOut

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
