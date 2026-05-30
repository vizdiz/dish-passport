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

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "LogRequest":
        has_text = self.text is not None and self.text.strip() != ""
        has_id = self.dish_id is not None
        if has_text == has_id:
            raise ValueError("provide exactly one of `text` or `dish_id`")
        return self


class DishOut(BaseModel):
    id: int
    name: str
    description: str
    ingredients: list[str]
    prep_method: Optional[str]
    flavor: dict[str, float]            # dim -> score, ordered by FLAVOR_DIMS
    embedding_model_version: str
    created_at: datetime

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


class LogResponse(BaseModel):
    dish: DishOut
    is_new: bool
    log_id: int


class ImpressionIn(BaseModel):
    user_id: int
    dish_id: int
    shown_at: datetime
    context: ImpressionContext
    converted: bool = False


class ImpressionsResponse(BaseModel):
    ingested: int


def flavor_to_dict(flavor: list[float]) -> dict[str, float]:
    """Map a length-10 flavor vector to {dim: score}, rounding for transport."""
    return {dim: round(float(v), 4) for dim, v in zip(FLAVOR_DIMS, flavor)}
