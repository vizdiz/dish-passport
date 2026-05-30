"""OpenAI embedder (text-embedding-3-small, 1536d). SDK imported lazily so the module
graph stays importable without `openai` installed or any key present."""
from __future__ import annotations


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._model = model
        self._client = None  # built on first use (lazy SDK import)

    @property
    def model_version(self) -> str:
        return self._model

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # lazy

            self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    async def embed(self, text: str) -> list[float]:
        client = self._ensure_client()
        resp = await client.embeddings.create(model=self._model, input=text)
        return list(resp.data[0].embedding)
