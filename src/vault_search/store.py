from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import lancedb
import pyarrow as pa

from .config import DEFAULT_EMBED_MODEL

CHUNKS_TABLE = "chunks"


@dataclass
class Chunk:
    path: str
    heading: str
    chunk_idx: int
    mtime: float
    text: str
    vector: list[float]


def _schema(embed_dim: int, embed_model: str) -> pa.Schema:
    return pa.schema(
        [
            pa.field("path", pa.string()),
            pa.field("heading", pa.string()),
            pa.field("chunk_idx", pa.int32()),
            pa.field("mtime", pa.float64()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), embed_dim)),
        ],
        metadata={"embed_model": embed_model, "embed_dim": str(embed_dim)},
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class VaultStore:
    def __init__(
        self,
        index_dir: Path,
        embed_dim: int,
        embed_model: str = DEFAULT_EMBED_MODEL,
        *,
        full: bool = False,
    ):
        index_dir.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_dir))
        self._embed_dim = embed_dim
        self._embed_model = embed_model
        self._table = self._open_or_create_table(full)

    def _open_or_create_table(self, full: bool):
        if CHUNKS_TABLE in self._db.list_tables().tables:
            table = self._db.open_table(CHUNKS_TABLE)
            if self._matches_model(table.schema):
                return table
            if not full:
                raise ValueError(
                    "Modell oder Dimension des Index passt nicht zur Konfiguration "
                    "oder die Modellmetadaten fehlen. Bitte vault-reindex --full ausführen."
                )
            self._db.drop_table(CHUNKS_TABLE)
        return self._db.create_table(
            CHUNKS_TABLE, schema=_schema(self._embed_dim, self._embed_model)
        )

    def _matches_model(self, schema: pa.Schema) -> bool:
        metadata = schema.metadata or {}
        return (
            metadata.get(b"embed_model") == self._embed_model.encode("utf-8")
            and metadata.get(b"embed_dim") == str(self._embed_dim).encode("utf-8")
            and schema.field("vector").type.list_size == self._embed_dim
        )

    def replace_note(self, path: str, chunks: Iterable[Chunk]) -> int:
        rows = [c.__dict__ for c in chunks]
        if any(len(row["vector"]) != self._embed_dim for row in rows):
            raise ValueError("Dimension der Embeddings passt nicht zum Index.")
        self.delete_note(path)
        if not rows:
            return 0
        self._table.add(rows)
        return len(rows)

    def delete_note(self, path: str) -> None:
        self._table.delete("path = " + _sql_literal(path))

    def known_mtimes(self) -> dict[str, float]:
        mtimes: dict[str, float] = {}
        rows = self._table.search().select(["path", "mtime"]).limit(None).to_list()
        for row in rows:
            existing = mtimes.get(row["path"])
            if existing is None or row["mtime"] > existing:
                mtimes[row["path"]] = row["mtime"]
        return mtimes

    def search(self, vector: list[float], k: int = 5) -> list[dict]:
        results = self._table.search(vector).limit(k).to_list()
        for row in results:
            row.pop("vector", None)
        return results

    def search_by_path_prefix(
        self, vector: list[float], path_prefix: str, k: int = 5
    ) -> list[dict]:
        results = (
            self._table.search(vector)
            .where("path LIKE " + _sql_literal(path_prefix + "%"), prefilter=True)
            .limit(k)
            .to_list()
        )
        for row in results:
            row.pop("vector", None)
        return results

    def fetch_note_vectors(self, path: str) -> list[list[float]]:
        rows = (
            self._table.search()
            .select(["vector"])
            .where("path = " + _sql_literal(path))
            .limit(None)
            .to_list()
        )
        return [row["vector"] for row in rows]

    def count(self) -> int:
        return self._table.count_rows()
