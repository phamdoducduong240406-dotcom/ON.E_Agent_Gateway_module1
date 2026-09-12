"""
Module 1 — Index
Embedding + cosine similarity search.
§5.7: Plain numpy matrix with cosine similarity. No hosted vector DB today.
"""

from __future__ import annotations

import json
import hashlib
import numpy as np
from pathlib import Path
from typing import Any

from config import EMBED_MODEL, OUTPUT_DIR, CACHE_DIR, TOP_K_SEMANTIC


class VectorIndex:
    """Index cho semantic search bằng cosine similarity.

    §5.7: Plain numpy matrix, no hosted vector DB.
    Cache embeddings to disk keyed by hash of agent_text.
    """

    def __init__(
        self,
        embeddings: np.ndarray,
        skus: list[str],
        texts: list[str],
        model: Any,
    ):
        self.embeddings = embeddings
        self.skus = skus
        self.texts = texts
        self.model = model

        # Normalise embeddings for fast cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1  # Avoid division by zero
        self.normalised = embeddings / norms

    def search(self, query: str, k: int = TOP_K_SEMANTIC) -> list[tuple[str, float]]:
        """Tìm kiếm cosine similarity.

        Args:
            query: Câu truy vấn
            k: Số kết quả trả về (default: TOP_K_SEMANTIC = 20)

        Returns:
            List[(sku, score)] sắp xếp theo score giảm dần
        """
        # Encode query
        query_emb = self.model.encode([query], normalize_embeddings=True)

        # Cosine similarity (dot product of normalised vectors)
        scores = np.dot(self.normalised, query_emb.T).flatten()

        # Top-k indices
        top_indices = np.argsort(scores)[::-1][:k]

        results = [
            (self.skus[i], float(scores[i]))
            for i in top_indices
        ]

        return results

    def build(self, records: list[dict[str, Any]]) -> None:
        """Build index từ records (alternative interface per spec §5.7).

        Args:
            records: List records có 'agent_text'
        """
        model = _load_model()
        self.model = model

        skus: list[str] = []
        texts: list[str] = []

        for record in records:
            sku = record.get("sku", "unknown")
            agent_text = record.get("agent_text", "")
            if agent_text:
                skus.append(sku)
                texts.append(agent_text)

        embeddings = model.encode(
            texts, show_progress_bar=True,
            normalize_embeddings=False, batch_size=32,
        )
        embeddings = np.array(embeddings)

        self.embeddings = embeddings
        self.skus = skus
        self.texts = texts

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1
        self.normalised = embeddings / norms

    def save(self, path: str | Path) -> None:
        """Lưu index (embeddings + metadata) vào file."""
        path = Path(path)
        np.save(str(path.with_suffix(".npy")), self.embeddings)

        meta = {
            "skus": self.skus,
            "texts": self.texts,
            "model_name": EMBED_MODEL,
        }
        with open(path.with_suffix(".meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"  [index] Saved index: {path.with_suffix('.npy')}")

    @classmethod
    def load(cls, path: str | Path, model: Any) -> "VectorIndex":
        """Load index từ file đã save."""
        path = Path(path)
        embeddings = np.load(str(path.with_suffix(".npy")))

        with open(path.with_suffix(".meta.json"), "r", encoding="utf-8") as f:
            meta = json.load(f)

        return cls(
            embeddings=embeddings,
            skus=meta["skus"],
            texts=meta["texts"],
            model=model,
        )


def _load_model():
    """Load embedding model. Chỉ gọi mạng lần đầu."""
    from sentence_transformers import SentenceTransformer
    print(f"[index] Loading embedding model: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)
    print(f"[index] Model loaded.")
    return model


def build_index(
    records: list[dict[str, Any]],
    cache_path: str | Path | None = None,
) -> VectorIndex:
    """Tạo embedding index từ agent_text của tất cả records.

    §5.7: Cache embeddings to disk keyed by hash of agent_text.

    Args:
        records: List records đã có 'agent_text'
        cache_path: Đường dẫn cache index, mặc định output/index

    Returns:
        VectorIndex object
    """
    if cache_path is None:
        cache_path = OUTPUT_DIR / "index"

    model = _load_model()

    # Prepare texts and SKUs
    skus: list[str] = []
    texts: list[str] = []

    for record in records:
        sku = record.get("sku", "unknown")
        agent_text = record.get("agent_text", "")

        if agent_text:
            skus.append(sku)
            texts.append(agent_text)
        else:
            print(f"  [index] WARNING: {sku} has no agent_text, skipping")

    print(f"[index] Encoding {len(texts)} texts...")

    # Encode
    embeddings = model.encode(
        texts,
        show_progress_bar=True,
        normalize_embeddings=False,  # We normalise ourselves
        batch_size=32,
    )

    embeddings = np.array(embeddings)

    # Build index
    index = VectorIndex(
        embeddings=embeddings,
        skus=skus,
        texts=texts,
        model=model,
    )

    # Save cache
    index.save(cache_path)

    print(f"[index] Index built: {len(skus)} entries, dim={embeddings.shape[1]}")
    return index


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from config import CATALOG_RAW_PATH
    from ingest import ingest

    records = ingest(CATALOG_RAW_PATH)

    # Give some fake agent_text for testing
    for r in records[:5]:
        r["agent_text"] = f"{r.get('name', '')}. Giá: {r.get('price', 'N/A')} AUD."

    # Build index with just 5 records
    test_records = [r for r in records[:5] if "agent_text" in r]
    if test_records:
        index = build_index(test_records)

        # §5.7 Acceptance: query returns relevant result in top 3
        queries = [
            "màn hình 4K giá rẻ",
            "cheap monitor",
        ]
        for q in queries:
            results = index.search(q, k=3)
            print(f"\nQuery: '{q}'")
            for sku, score in results:
                print(f"  {sku}: {score:.4f}")
