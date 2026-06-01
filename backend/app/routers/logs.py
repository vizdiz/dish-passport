from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.deps import get_current_user, get_embedder, get_normalizer, get_repo, get_settings
from app.ports import DishNormalizer, DishRepository, Embedder
from app.schemas import (
    DishOut,
    FlavorOverrideRequest,
    FlavorOverrideResponse,
    LogRequest,
    LogResponse,
    flavor_to_dict,
)
from app.services.ingestion import DishNotFound, log_dish

router = APIRouter(tags=["logs"])


@router.post("/logs", response_model=LogResponse)
async def create_log(
    body: LogRequest,
    user_id: int = Depends(get_current_user),
    repo: DishRepository = Depends(get_repo),
    embedder: Embedder = Depends(get_embedder),
    normalizer: DishNormalizer = Depends(get_normalizer),
    settings: Settings = Depends(get_settings),
) -> LogResponse:
    try:
        result = await log_dish(
            repo=repo,
            embedder=embedder,
            normalizer=normalizer,
            user_id=user_id,
            text=body.text,
            dish_id=body.dish_id,
            sentiment=body.sentiment,
            rating=body.rating,
            notes=body.notes,
            photo_url=body.photo_url,
            tau=settings.dedup_tau,
        )
    except DishNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return LogResponse(
        dish=DishOut.from_record(result.dish),
        is_new=result.is_new,
        log_id=result.log_id,
    )


@router.patch("/logs/{log_id}/flavor", response_model=FlavorOverrideResponse)
async def refine_flavor(
    log_id: int,
    body: FlavorOverrideRequest,
    user_id: int = Depends(get_current_user),
    repo: DishRepository = Depends(get_repo),
) -> FlavorOverrideResponse:
    """User refines the 10 flavor dims for one of THEIR logs (implicit signal; Service 3)."""
    if not await repo.log_belongs_to(log_id, user_id):
        raise HTTPException(status_code=404, detail=f"log {log_id} not found")
    vector = body.as_vector()
    await repo.set_log_flavor_override(log_id, vector)
    return FlavorOverrideResponse(log_id=log_id, flavor_override=flavor_to_dict(vector))
