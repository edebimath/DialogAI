"""Text embeddings through Ollama (bge-m3: multilingual, good Turkish retrieval)."""

from typing import Protocol

import httpx

from app.core.config import settings

BATCH = 16


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingError(Exception):
    pass


class OllamaEmbedder:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=settings.ollama_url, timeout=120)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), BATCH):
            body = {"model": settings.embedding_model, "input": texts[i : i + BATCH], "keep_alive": "30m"}
            if not settings.embed_on_gpu:
                body["options"] = {"num_gpu": 0}
            try:
                r = await self._client.post("/api/embed", json=body)
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise EmbeddingError(
                    f"Gömme modeli ({settings.embedding_model}) çalıştırılamadı: {e}. "
                    f"Ollama açık mı ve model indirildi mi? (ollama pull {settings.embedding_model})"
                ) from e
            vectors.extend(r.json()["embeddings"])
        return vectors


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbedder()
    return _embedder


def set_embedder(embedder: Embedder) -> None:
    """Tests swap in a deterministic embedder."""
    global _embedder
    _embedder = embedder
