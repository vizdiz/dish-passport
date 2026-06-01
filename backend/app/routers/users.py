from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user, get_repo
from app.ports import DishRepository
from app.schemas import DishOut, FactorScore, TasteProfileOut

router = APIRouter(tags=["taste"])


@router.get("/users/me/taste-profile", response_model=TasteProfileOut)
async def get_taste_profile(
    user_id: int = Depends(get_current_user),
    repo: DishRepository = Depends(get_repo),
) -> TasteProfileOut:
    profile = await repo.get_taste_profile(user_id)
    if profile is None:
        raise HTTPException(
            status_code=404,
            detail=f"no taste profile for user {user_id} (run rebuild_taste_profiles)",
        )

    factor_scores = None
    model = await repo.get_latest_svd_model()
    if profile.flavor_factor_pref and model is not None:
        factor_scores = [
            FactorScore(label=label, value=round(value, 4))
            for label, value in zip(model.factor_labels, profile.flavor_factor_pref)
        ]

    representative: list[DishOut] = []
    if profile.liked_centroid:
        for nb in await repo.vector_topk(profile.liked_centroid, 5, []):
            representative.append(DishOut.from_record(nb.dish))

    return TasteProfileOut(
        user_id=user_id,
        n_dishes=profile.n_dishes,
        flavor_factor_pref=factor_scores,
        representative_dishes=representative,
        has_liked_centroid=profile.liked_centroid is not None,
        has_disliked_centroid=profile.disliked_centroid is not None,
    )
