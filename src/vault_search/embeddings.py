from __future__ import annotations

import httpx


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self._model = model

    def embed(self, text: str) -> list[float]:
        response = self._client.post(
            "/api/embed",
            json={"model": self._model, "input": text, "truncate": True},
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.post(
                "/api/embed",
                json={"model": self._model, "input": texts, "truncate": True},
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except httpx.HTTPStatusError:
            return [self.embed(t) for t in texts]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaEmbedder:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
