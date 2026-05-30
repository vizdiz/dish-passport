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
class SvdModel:
    """A fitted flavor SVD: stored so new dishes project into factor space without refit."""
    version: str
    components: list[list[float]]   # n_factors x 10, orthonormal rows (loadings)
    singular_values: list[float]    # n_factors
    mean: list[float]               # 10, the centering mean
    factor_labels: list[str]        # n_factors, derived from loadings


@dataclass(frozen=True)
class TasteProfile:
    user_id: int
    liked_centroid: Optional[list[float]]      # 1536, or None if no positive logs
    disliked_centroid: Optional[list[float]]   # 1536, or None
    flavor_factor_pref: Optional[list[float]]  # 4, mean latent factors over liked dishes
    n_dishes: int


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
    async def similar(self, dish_id: int, n: int) -> list[Neighbor]: ...
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

    # ---- flavor / SVD (Service 3) ----
    async def set_log_flavor_override(self, log_id: int, flavor: Sequence[float]) -> bool: ...
    async def all_dish_flavors(self) -> list[tuple[int, list[float]]]: ...
    async def save_svd_model(self, model: SvdModel) -> None: ...
    async def get_latest_svd_model(self) -> Optional[SvdModel]: ...
    async def save_dish_factors(
        self, factors: Sequence[tuple[int, list[float]]], svd_model_version: str
    ) -> None: ...
    async def get_dish_factors(self, dish_id: int) -> Optional[tuple[list[float], str]]: ...

    # ---- collaborative filtering (Service 4) ----
    async def all_logs(self) -> list[tuple[int, int, str]]: ...   # (user_id, dish_id, sentiment)
    async def save_cf_factors(
        self,
        user_factors: Sequence[tuple[int, list[float]]],
        item_factors: Sequence[tuple[int, list[float]]],
        model_version: str,
    ) -> None: ...
    async def get_cf_user_factors(self, user_id: int) -> Optional[tuple[list[float], str]]: ...
    async def get_cf_item_factors(self, dish_id: int) -> Optional[tuple[list[float], str]]: ...
    async def all_cf_item_factors(self) -> list[tuple[int, list[float]]]: ...

    # ---- recommendation / taste profiles (Service 5) ----
    async def all_user_ids(self) -> list[int]: ...
    async def user_logs(self, user_id: int) -> list[tuple[int, str]]: ...   # (dish_id, sentiment)
    async def user_impressions(
        self, user_id: int
    ) -> list[tuple[int, datetime, bool]]: ...                              # (dish_id, shown_at, converted)
    async def dish_embeddings(self, dish_ids: Sequence[int]) -> dict[int, list[float]]: ...
    async def vector_topk(
        self, embedding: Sequence[float], k: int, exclude_ids: Sequence[int]
    ) -> list[Neighbor]: ...
    async def centroid_cosines(
        self,
        dish_ids: Sequence[int],
        liked_centroid: Sequence[float],
        disliked_centroid: Optional[Sequence[float]],
    ) -> dict[int, tuple[float, float]]: ...                                # id -> (cos_liked, cos_disliked)
    async def popular_dishes(self, k: int, exclude_ids: Sequence[int]) -> list[int]: ...
    async def save_taste_profile(self, profile: TasteProfile) -> None: ...
    async def get_taste_profile(self, user_id: int) -> Optional[TasteProfile]: ...
