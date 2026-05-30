from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings
from app.deps import get_embedder, get_normalizer, get_repo, get_settings
from app.ports import DishNormalizer, DishRepository, Embedder
from app.schemas import DishOut, LogRequest, LogResponse
from app.services.ingestion import DishNotFound, log_dish

router = APIRouter(tags=["logs"])


@router.post("/logs", response_model=LogResponse)
async def create_log(
    body: LogRequest,
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
            user_id=body.user_id,
            text=body.text,
            dish_id=body.dish_id,
            sentiment=body.sentiment,
            rating=body.rating,
            notes=body.notes,
            tau=settings.dedup_tau,
        )
    except DishNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return LogResponse(
        dish=DishOut.from_record(result.dish),
        is_new=result.is_new,
        log_id=result.log_id,
    )
