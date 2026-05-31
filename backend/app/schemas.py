"""HTTP request/response models. Kept separate from the internal port dataclasses."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.ports import FLAVOR_DIMS, DishRecord

Sentiment = Literal["liked", "neutral", "disliked"]
ImpressionContext = Literal["feed", "recs", "similar"]


class LogRequest(BaseModel):
    user_id: int
    text: Optional[str] = None
    dish_id: Optional[int] = None
    sentiment: Sentiment = "liked"
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None
    photo_url: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "LogRequest":
        has_text = self.text is not None and self.text.strip() != ""
        has_id = self.dish_id is not None
        if has_text == has_id:
            raise ValueError("provide exactly one of `text` or `dish_id`")
        return self


class FactorScore(BaseModel):
    label: str                          # data-derived, e.g. "rich+umami ↔ fresh+sour"
    value: float


class DishOut(BaseModel):
    id: int
    name: str
    description: str
    ingredients: list[str]
    prep_method: Optional[str]
    flavor: dict[str, float]            # dim -> score, ordered by FLAVOR_DIMS
    embedding_model_version: str
    created_at: datetime
    # Service 3: 4-factor projection, present once an SVD model exists (else null).
    factors: Optional[list[FactorScore]] = None
    svd_model_version: Optional[str] = None

    @classmethod
    def from_record(cls, d: DishRecord) -> "DishOut":
        return cls(
            id=d.id,
            name=d.name,
            description=d.description,
            ingredients=list(d.ingredients),
            prep_method=d.prep_method,
            flavor=flavor_to_dict(d.flavor),
            embedding_model_version=d.embedding_model_version,
            created_at=d.created_at,
        )


class FlavorOverrideRequest(BaseModel):
    """User refinement of the 10 flavor dims (stored as logs.flavor_override)."""
    flavor: dict[str, float]

    @model_validator(mode="after")
    def _validate_dims(self) -> "FlavorOverrideRequest":
        if set(self.flavor) != set(FLAVOR_DIMS):
            raise ValueError(f"flavor must have exactly these keys: {list(FLAVOR_DIMS)}")
        if any(not (0.0 <= v <= 1.0) for v in self.flavor.values()):
            raise ValueError("every flavor score must be in [0, 1]")
        return self

    def as_vector(self) -> list[float]:
        return [float(self.flavor[dim]) for dim in FLAVOR_DIMS]


class FlavorOverrideResponse(BaseModel):
    log_id: int
    flavor_override: dict[str, float]


class LogResponse(BaseModel):
    dish: DishOut
    is_new: bool
    log_id: int


class SimilarNeighbor(BaseModel):
    dish: DishOut
    cosine: float


class SimilarResponse(BaseModel):
    dish_id: int
    n: int
    neighbors: list[SimilarNeighbor]


class ImpressionIn(BaseModel):
    user_id: int
    dish_id: int
    shown_at: datetime
    context: ImpressionContext
    converted: bool = False


class ImpressionsResponse(BaseModel):
    ingested: int


class RecommendationOut(BaseModel):
    dish: DishOut
    score: float
    explanation: str                    # from flavor factors, never the embedding
    components: dict[str, float]         # normalized signal contributions {cf, cb, vec}


class RecommendationsResponse(BaseModel):
    user_id: int
    n: int
    cold_start: bool
    recommendations: list[RecommendationOut]


class PresignRequest(BaseModel):
    content_type: Literal["image/jpeg", "image/png", "image/webp"]


class PresignResponse(BaseModel):
    upload_url: str
    public_url: str
    key: str
    headers: dict[str, str] = {}   # exact headers the client must send with the PUT


class TasteProfileOut(BaseModel):
    user_id: int
    n_dishes: int
    flavor_factor_pref: Optional[list[FactorScore]]
    representative_dishes: list[DishOut]
    has_liked_centroid: bool
    has_disliked_centroid: bool


def flavor_to_dict(flavor: list[float]) -> dict[str, float]:
    """Map a length-10 flavor vector to {dim: score}, rounding for transport."""
    return {dim: round(float(v), 4) for dim, v in zip(FLAVOR_DIMS, flavor)}
