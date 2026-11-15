"""Local embeddings for semantic skill matching (docs/05 §8.3, ADR-010).

* :class:`SentenceTransformerEncoder` loads ``all-MiniLM-L6-v2`` (384-d, CPU) **once per process**
  and encodes in batches of 32. Nothing leaves the server; the model files come from the
  Hugging Face cache (baked into the worker image or downloaded once).
* :class:`EmbeddingService` caches vectors by ``(model, sha256(normalised text))`` in any
  key-value cache with ``get_many``/``set_many`` (Django's Redis cache in production), so the
  same phrase is never encoded twice.
* :class:`SemanticSkillMatcher` is the parser's ``semantic`` callback: nearest taxonomy skill for
  an unmatched phrase, returned only above a threshold (0.75 until Phase 10 calibration). It is
  an *inferred* match with capped confidence; it never replaces an explicit one.

If the model cannot load, callers run without semantic matching (deterministic path only,
EC-AI-06); :class:`HashingEncoder` exists for tests and offline development, not production.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
import unicodedata
from array import array
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

Vector = list[float]
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSIONS = 384
DEFAULT_THRESHOLD = 0.75
BATCH_SIZE = 32


class Encoder(Protocol):
    name: str
    dimensions: int

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        """Unit-length vectors, one per text, in order."""
        ...


class Cache(Protocol):
    def get_many(self, keys: Iterable[str]) -> Mapping[str, Any]: ...

    def set_many(self, data: dict[str, Any], timeout: Any = ...) -> Any: ...


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def unit(vector: Sequence[float]) -> Vector:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product of unit vectors (= cosine similarity)."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def pack(vector: Sequence[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack(blob: bytes) -> Vector:
    out = array("f")
    out.frombytes(blob)
    return list(out)


# ------------------------------------------------------------------------------ encoders
class SentenceTransformerEncoder:
    """sentence-transformers on CPU; import and model load are deferred to first use."""

    def __init__(self, model_name: str = DEFAULT_MODEL, *, batch_size: int = BATCH_SIZE) -> None:
        self.name = model_name
        self.dimensions = DIMENSIONS
        self.batch_size = batch_size
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.name, device="cpu")
                dimension = getattr(self._model, "get_embedding_dimension", None) or (
                    self._model.get_sentence_embedding_dimension
                )
                self.dimensions = int(dimension())
        return self._model

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [[float(x) for x in row] for row in vectors]


class HashingEncoder:
    """Deterministic bag-of-character-trigrams vectors: tests and offline dev only."""

    def __init__(self, dimensions: int = DIMENSIONS) -> None:
        self.name = f"hashing-{dimensions}"
        self.dimensions = dimensions

    def encode(self, texts: Sequence[str]) -> list[Vector]:
        out: list[Vector] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            padded = f"  {normalise_text(text)}  "
            for i in range(len(padded) - 2):
                digest = hashlib.blake2b(padded[i : i + 3].encode(), digest_size=4).digest()
                vector[int.from_bytes(digest, "big") % self.dimensions] += 1.0
            out.append(unit(vector))
        return out


_ENCODERS: dict[str, Encoder] = {}
_ENCODERS_LOCK = threading.Lock()


def get_encoder(name: str = DEFAULT_MODEL) -> Encoder:
    """One encoder per model per process (Celery workers load the model once)."""
    with _ENCODERS_LOCK:
        if name not in _ENCODERS:
            _ENCODERS[name] = (
                HashingEncoder()
                if name.startswith("hashing")
                else (SentenceTransformerEncoder(name))
            )
        return _ENCODERS[name]


# ------------------------------------------------------------------------------- service
class EmbeddingService:
    def __init__(
        self, encoder: Encoder, cache: Cache | None = None, *, timeout: int = 30 * 24 * 3600
    ) -> None:
        self.encoder = encoder
        self.cache = cache
        self.timeout = timeout
        self.encoded = 0  # texts actually sent to the model (for tests/metrics)

    def key(self, text: str) -> str:
        digest = hashlib.sha256(normalise_text(text).encode()).hexdigest()
        return f"emb:{self.encoder.name}:{digest}"

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        keys = [self.key(t) for t in texts]
        cached: Mapping[str, Any] = self.cache.get_many(set(keys)) if self.cache else {}
        found: dict[str, Vector] = {k: unpack(v) for k, v in cached.items() if v}
        missing: dict[str, str] = {}
        for key, text in zip(keys, texts, strict=True):
            if key not in found and key not in missing:
                missing[key] = text
        if missing:
            todo = list(missing.items())
            for i in range(0, len(todo), BATCH_SIZE):
                batch = todo[i : i + BATCH_SIZE]
                vectors = self.encoder.encode([text for _, text in batch])
                self.encoded += len(batch)
                fresh = {key: vector for (key, _), vector in zip(batch, vectors, strict=True)}
                found.update(fresh)
                if self.cache:
                    self.cache.set_many({k: pack(v) for k, v in fresh.items()}, self.timeout)
        return [found[k] for k in keys]

    def embed_one(self, text: str) -> Vector:
        return self.embed([text])[0]


# ------------------------------------------------------------------------------- matcher
@dataclass(frozen=True)
class SkillVector:
    skill_id: str
    name: str
    vector: Vector


class SemanticSkillMatcher:
    """Nearest taxonomy skill for a phrase; ``__call__`` fits ``parser.Semantic``."""

    def __init__(
        self,
        service: EmbeddingService,
        skills: Iterable[SkillVector],
        *,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self.service = service
        self.skills = [s for s in skills if s.vector]
        self.threshold = threshold

    def nearest(self, phrase: str, k: int = 3) -> list[tuple[SkillVector, float]]:
        if not self.skills or not phrase.strip():
            return []
        query = self.service.embed_one(phrase)
        scored = [(s, cosine(query, s.vector)) for s in self.skills]
        scored.sort(key=lambda pair: (-pair[1], pair[0].name))
        return scored[:k]

    def __call__(self, phrase: str) -> tuple[str, str, float] | None:
        best = self.nearest(phrase, k=1)
        if not best or best[0][1] < self.threshold:
            return None
        skill, score = best[0]
        return skill.skill_id, skill.name, round(score, 4)
