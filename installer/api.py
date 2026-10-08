import json
import os
import urllib.error
import urllib.request

from vault_search.config import DEFAULT_OLLAMA_URL


class ApiError(RuntimeError):
    """Ollama ist nicht erreichbar oder hat einen Fehler gemeldet."""


def base_url() -> str:
    return os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def request(path: str, data: dict | None = None, timeout: float = 5) -> dict:
    body = None if data is None else json.dumps(data).encode("utf-8")
    query = urllib.request.Request(
        base_url() + path, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(query, timeout=timeout) as response:
            result = json.load(response)
    except (OSError, urllib.error.URLError, ValueError) as error:
        raise ApiError(f"Ollama-Anfrage fehlgeschlagen ({base_url()}): {error}") from error
    if not isinstance(result, dict):
        raise ApiError("Ollama lieferte kein JSON-Objekt.")
    if result.get("error"):
        raise ApiError(f"Ollama meldet: {result['error']}")
    return result
