"""Ports: the contracts the ingestion gate depends on.

The gate (`app/services/ingestion.py`) imports *only* from this module — never a DB
driver or a vendor SDK. Adapters in `app/adapters/` implement these Protocols.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, Sequence, runtime_checkable

# Canonical flavor dimensions, in storage order. `flavor` vectors (len 10) follow this.
FLAVOR_DIMS: tuple[str, ...] = (
    "umami", "spicy", "sour", "sweet", "bitter",
    "rich", "herbaceous", "smoky", "fermented", "fresh",
)


@dataclass(frozen=True)
class NormalizedDish:
    """Output of the one combined LLM call: a cuisine-blind canonical dish."""
    name: str
    description: str               # cuisine-blind canonical description — the dedup key
    flavor: list[float]            # len 10, each 0..1, ordered by FLAVOR_DIMS
    ingredients: list[str] = field(default_factory=list)
    prep_method: Optional[str] = None


@dataclass(frozen=True)
class DishRecord:
    """A persisted canonical dish (no opaque embedding — that never leaves the repo)."""
    id: int
    name: str
    description: str
    ingredients: list[str]
    prep_method: Optional[str]
    flavor: list[float]            # len 10
    embedding_model_version: str
    created_at: datetime


@dataclass(frozen=True)
class Neighbor:
    dish: DishRecord
    cosine: float                  # cosine similarity in [-1, 1]


@dataclass(frozen=True)
class ImpressionRow:
    user_id: int
    dish_id: int
    shown_at: datetime
    context: str                   # 'feed' | 'recs' | 'similar'
    converted: bool = False


@runtime_checkable
class Embedder(Protocol):
    @property
    def model_version(self) -> str: ...
    async def embed(self, text: str) -> list[float]: ...


@runtime_checkable
class DishNormalizer(Protocol):
    async def normalize(self, text: str) -> NormalizedDish: ...


@runtime_checkable
class DishRepository(Protocol):
    async def get_dish(self, dish_id: int) -> Optional[DishRecord]: ...
    async def nearest(self, embedding: Sequence[float]) -> Optional[Neighbor]: ...
    async def insert_dish(
        self,
        normalized: NormalizedDish,
        embedding: Sequence[float],
        embedding_model_version: str,
    ) -> DishRecord: ...
    async def insert_log(
        self,
        *,
        user_id: int,
        dish_id: int,
        sentiment: str,
        rating: Optional[int],
        notes: Optional[str],
    ) -> int: ...
    async def insert_impressions(self, rows: Sequence[ImpressionRow]) -> int: ...
