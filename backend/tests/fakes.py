"""In-memory test doubles + deterministic vector helpers.

The geometry helpers build unit vectors with an *exact* cosine to a fixed axis, so the
dedup gate's threshold behavior can be asserted precisely without a real embedder.
"""
from __future__ import annotations

import hashlib
import math
from typing import Optional, Union

from app.ports import NormalizedDish

DIM = 1536


def axis0() -> list[float]:
    """Unit vector along dimension 0: [1, 0, 0, ...]."""
    v = [0.0] * DIM
    v[0] = 1.0
    return v


def vec_cos_to_axis0(cosine: float) -> list[float]:
    """A unit vector whose cosine similarity to axis0() equals `cosine` exactly."""
    c = max(-1.0, min(1.0, cosine))
    v = [0.0] * DIM
    v[0] = c
    v[1] = math.sqrt(max(0.0, 1.0 - c * c))
    return v


def _tok_index(tok: str) -> int:
    return int.from_bytes(hashlib.md5(tok.encode()).digest()[:4], "big") % DIM


def hash_vec(text: str) -> list[float]:
    """Deterministic L2-normalized bag-of-tokens vector (process-stable, unlike hash())."""
    v = [0.0] * DIM
    for tok in text.lower().split():
        v[_tok_index(tok)] += 1.0
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0.0:
        return axis0()
    return [x / norm for x in v]


def flat_flavor(value: float = 0.5) -> list[float]:
    return [value] * 10


class StubNormalizer:
    """Maps input text to a NormalizedDish. `mapping` values may be a full NormalizedDish
    or a description string (name/flavor then defaulted). Counts calls."""

    def __init__(
        self,
        mapping: Optional[dict[str, Union[NormalizedDish, str]]] = None,
        default_flavor: Optional[list[float]] = None,
    ) -> None:
        self._mapping = mapping or {}
        self._default_flavor = default_flavor or flat_flavor()
        self.calls = 0

    async def normalize(self, text: str) -> NormalizedDish:
        self.calls += 1
        spec = self._mapping.get(text)
        if isinstance(spec, NormalizedDish):
            return spec
        description = spec if isinstance(spec, str) else text.strip().lower()
        return NormalizedDish(
            name=text.strip().title(),
            description=description,
            flavor=list(self._default_flavor),
            ingredients=[],
            prep_method=None,
        )


class StubEmbedder:
    """Maps a description string to a vector. Unmapped text falls back to hash_vec.
    Counts calls so the fast lane can assert zero embeds."""

    def __init__(
        self,
        mapping: Optional[dict[str, list[float]]] = None,
        model_version: str = "stub-emb-v0",
    ) -> None:
        self._mapping = mapping or {}
        self._model_version = model_version
        self.calls = 0

    @property
    def model_version(self) -> str:
        return self._model_version

    async def embed(self, text: str) -> list[float]:
        self.calls += 1
        # Substring match: the gate embeds a composite (name + description + ...), so a mapping
        # keyed on the description still resolves.
        if text in self._mapping:
            return list(self._mapping[text])
        for key, vec in self._mapping.items():
            if key in text:
                return list(vec)
        return hash_vec(text)
