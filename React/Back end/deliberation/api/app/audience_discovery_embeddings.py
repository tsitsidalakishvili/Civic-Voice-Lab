import hashlib
import os
import time
from typing import Dict, List, Optional

import numpy as np
import requests
from sklearn.feature_extraction.text import HashingVectorizer


class EmbeddingResult:
    def __init__(self, vector: List[float], model: str, timestamp: float, text_hash: str):
        self.vector = vector
        self.model = model
        self.timestamp = timestamp
        self.text_hash = text_hash


class EmbeddingsService:
    def __init__(self, dim: int = 256):
        self.dim = dim
        self.model = f"hashing-{dim}"
        self.vectorizer = HashingVectorizer(
            n_features=dim,
            alternate_sign=False,
            norm="l2",
            analyzer="word",
            ngram_range=(1, 2),
        )
        self.cache: Dict[str, EmbeddingResult] = {}
        self.api_url = os.getenv("EMBEDDINGS_API_URL", "").strip()
        self.api_key = os.getenv("EMBEDDINGS_API_KEY", "").strip()
        self.api_model = os.getenv("EMBEDDINGS_MODEL", "").strip()
        self.batch_size = int(os.getenv("EMBEDDINGS_BATCH_SIZE", "16"))

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _call_embeddings_api(self, texts: List[str]) -> List[List[float]]:
        payload = {"input": texts, "model": self.api_model or "text-embedding-3-small"}
        response = requests.post(
            self.api_url,
            json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data.get("data", [])]

    def _embed_remote(self, texts: List[str]) -> List[EmbeddingResult]:
        results: List[EmbeddingResult] = []
        for idx in range(0, len(texts), self.batch_size):
            batch = texts[idx : idx + self.batch_size]
            last_error: Optional[str] = None
            for attempt in range(3):
                try:
                    vectors = self._call_embeddings_api(batch)
                    timestamp = time.time()
                    for text, vector in zip(batch, vectors):
                        text_hash = self._hash_text(text)
                        result = EmbeddingResult(
                            vector=vector,
                            model=self.api_model or "remote",
                            timestamp=timestamp,
                            text_hash=text_hash,
                        )
                        self.cache[text_hash] = result
                        results.append(result)
                    break
                except Exception as exc:
                    last_error = str(exc)
                    time.sleep(1 + attempt)
            else:
                raise RuntimeError(last_error or "Embeddings API failed")
        return results

    def embed(self, texts: List[str]) -> List[EmbeddingResult]:
        if not texts:
            return []
        hashes = [self._hash_text(text) for text in texts]
        results: List[EmbeddingResult] = []
        pending_indices = [idx for idx, h in enumerate(hashes) if h not in self.cache]

        if pending_indices:
            pending_texts = [texts[idx] for idx in pending_indices]
            if self.api_url and self.api_key:
                try:
                    self._embed_remote(pending_texts)
                except Exception:
                    matrix = self.vectorizer.transform(pending_texts).toarray()
                    for idx, vector in zip(pending_indices, matrix):
                        text_hash = hashes[idx]
                        result = EmbeddingResult(
                            vector=vector.astype(float).tolist(),
                            model=self.model,
                            timestamp=time.time(),
                            text_hash=text_hash,
                        )
                        self.cache[text_hash] = result
            else:
                matrix = self.vectorizer.transform(pending_texts).toarray()
                for idx, vector in zip(pending_indices, matrix):
                    text_hash = hashes[idx]
                    result = EmbeddingResult(
                        vector=vector.astype(float).tolist(),
                        model=self.model,
                        timestamp=time.time(),
                        text_hash=text_hash,
                    )
                    self.cache[text_hash] = result

        for text_hash in hashes:
            results.append(self.cache[text_hash])

        return results
