"""OpenAI normalizer: ONE combined chat call (function-calling) that returns a cuisine-blind
canonical dish (name + description + ingredients + prep_method) and a 10-dim flavor profile.

Structured output is forced via a required tool call, so we parse arguments, not free text.
SDK imported lazily. The description is deliberately cuisine-blind so the dedup embedding
clusters by what a dish *is*, keeping kindred-but-distinct dishes apart.
"""
from __future__ import annotations

import json

from app.ports import FLAVOR_DIMS, NormalizedDish

_PARAMETERS = {
    "type": "object",
    "properties": {
        "canonical_name": {
            "type": "string",
            "description": "Short canonical dish name (a person could recognize it).",
        },
        "description": {
            "type": "string",
            "description": (
                "One or two sentences describing the dish by its ingredients, preparation "
                "technique, and texture. CUISINE-BLIND: do NOT name a cuisine, country, "
                "region, or language of origin."
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
}

_TOOL = {
    "type": "function",
    "function": {
        "name": "record_dish",
        "description": "Record the normalized, cuisine-blind canonical form of a dish.",
        "parameters": _PARAMETERS,
    },
}

_SYSTEM = (
    "You normalize free-text dish entries into a canonical, cuisine-blind form for a dish "
    "catalog. Always call the record_dish function. Keep the description strictly about "
    "ingredients, technique, and texture — never mention a cuisine, nationality, or region."
)


class OpenAINormalizer:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self._model = model
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # lazy

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def normalize(self, text: str) -> NormalizedDish:
        client = self._ensure_client()
        resp = await client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Dish entry: {text}"},
            ],
            tools=[_TOOL],
            tool_choice={"type": "function", "function": {"name": "record_dish"}},
        )
        data = _extract_tool_arguments(resp)
        flavor = [min(1.0, max(0.0, float(data["flavor"][dim]))) for dim in FLAVOR_DIMS]
        return NormalizedDish(
            name=str(data["canonical_name"]).strip(),
            description=str(data["description"]).strip(),
            flavor=flavor,
            ingredients=[str(x).strip().lower() for x in data.get("ingredients", [])],
            prep_method=(str(data["prep_method"]).strip() if data.get("prep_method") else None),
        )


def _extract_tool_arguments(resp) -> dict:
    message = resp.choices[0].message
    if not message.tool_calls:
        raise ValueError("OpenAI response did not contain a record_dish tool call")
    return json.loads(message.tool_calls[0].function.arguments)
