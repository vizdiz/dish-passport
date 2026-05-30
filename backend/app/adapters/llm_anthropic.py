"""Anthropic normalizer: ONE combined call that returns a cuisine-blind canonical dish
(name + description + ingredients + prep_method) and a 10-dim flavor profile.

Structured output is forced with tool-use, so we parse a tool_use block, not free text.
SDK imported lazily. The description is deliberately cuisine-blind: it names ingredients,
technique, and texture but NOT cuisine/origin, so the dedup embedding clusters by what a
dish *is*, letting kindred-but-distinct dishes (al pastor vs shawarma) stay apart.
"""
from __future__ import annotations

from app.ports import FLAVOR_DIMS, NormalizedDish

_TOOL = {
    "name": "record_dish",
    "description": "Record the normalized, cuisine-blind canonical form of a dish.",
    "input_schema": {
        "type": "object",
        "properties": {
            "canonical_name": {
                "type": "string",
                "description": "Short canonical dish name (a person could recognize it).",
            },
            "description": {
                "type": "string",
                "description": (
                    "One or two sentences describing the dish by its ingredients, "
                    "preparation technique, and texture. CUISINE-BLIND: do NOT name a "
                    "cuisine, country, region, or language of origin."
                ),
            },
            "ingredients": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Primary ingredients, lowercase.",
            },
            "prep_method": {
                "type": "string",
                "description": "Dominant cooking technique, e.g. grilled, braised, raw, fried.",
            },
            "flavor": {
                "type": "object",
                "description": "Each flavor dimension scored 0.0-1.0.",
                "properties": {dim: {"type": "number"} for dim in FLAVOR_DIMS},
                "required": list(FLAVOR_DIMS),
            },
        },
        "required": ["canonical_name", "description", "ingredients", "prep_method", "flavor"],
    },
}

_SYSTEM = (
    "You normalize free-text dish entries into a canonical, cuisine-blind form for a dish "
    "catalog. Always call the record_dish tool. Keep the description strictly about "
    "ingredients, technique, and texture — never mention a cuisine, nationality, or region."
)


class AnthropicNormalizer:
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic  # lazy

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def normalize(self, text: str) -> NormalizedDish:
        client = self._ensure_client()
        resp = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_dish"},
            messages=[{"role": "user", "content": f"Dish entry: {text}"}],
        )
        data = _extract_tool_input(resp)
        flavor = [float(data["flavor"][dim]) for dim in FLAVOR_DIMS]
        flavor = [min(1.0, max(0.0, v)) for v in flavor]
        return NormalizedDish(
            name=str(data["canonical_name"]).strip(),
            description=str(data["description"]).strip(),
            flavor=flavor,
            ingredients=[str(x).strip().lower() for x in data.get("ingredients", [])],
            prep_method=(str(data["prep_method"]).strip() if data.get("prep_method") else None),
        )


def _extract_tool_input(resp) -> dict:
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "record_dish":
            return dict(block.input)
    raise ValueError("Anthropic response did not contain a record_dish tool_use block")
