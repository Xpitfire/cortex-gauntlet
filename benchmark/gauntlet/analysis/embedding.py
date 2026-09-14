"""Shared local embeddings for VERTEX (text) and the vision judge (image+text) — one model, two uses.

Selection is explicit and provenance is honest:
- `model is None` selects the deterministic **hashing** text embedding — an explicit offline choice
  (`GAUNTLET_VERTEX_MODEL=none`), not an error path; keeps tests reproducible without a model download.
- A *named* text model is loaded via sentence-transformers. A missing library or a failing load/encode
  is **raised** (the ImportError propagates from `_load`) — we never silently swap in the hashing
  embedding or a different model that would change the numbers; offline operation is the explicit
  `model=None` opt-in above, never an implicit degradation.
- Image embeddings require a CLIP model (sentence-transformers + Pillow). If unavailable we raise
  `EmbeddingUnavailable` — there is no image hashing fallback, and the only caller (the CLIP judge) is
  selected explicitly, so a missing dependency must surface, not degrade silently.

The same CLIP model encodes both images and text, so configuring `clip-ViT-B-32` lets the visual judge
and VERTEX share one loaded model.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading

from . import _proc

_HASH_DIM = 256
_TOKEN = re.compile(r"[a-z0-9]+")  # lowercased alphanumeric word tokens
_model_cache: dict[str, object] = {}  # model id -> loaded SentenceTransformer (process-lifetime cache)
_load_lock = threading.Lock()  # serialize first-loads so concurrent suite threads don't race the load


class EmbeddingUnavailable(RuntimeError):
    """A requested embedding backend (model/library) is not available and must not be silently swapped."""


def is_clip_model(model: str | None) -> bool:
    return bool(model) and "clip" in model.lower()


def hash_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hashing embedding (stable hashlib digest, L2-normalized)."""

    vec = [0.0] * _HASH_DIM
    for token in _TOKEN.findall(text.lower()):
        digest = hashlib.sha1(token.encode()).digest()
        idx = digest[0] | (digest[1] << 8)
        sign = 1.0 if digest[2] & 1 else -1.0
        vec[idx % _HASH_DIM] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _constrain_torch_threads() -> None:
    """Pin torch/OMP to a single thread BEFORE loading the model. Under the suite's heavy concurrency
    (many CLI subprocesses + docker builds + playwright, all spawning threads) torch's default thread
    pools (one per core) create a thread storm on load that hits the per-user thread limit → pthread
    EAGAIN. That EAGAIN was misread as a transient fd-race and silently degraded VERTEX to 0 for every
    arm. One thread is ample for small-embedding inference and removes the trigger. Idempotent."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    try:
        import torch

        torch.set_num_threads(1)
    except Exception:  # noqa: BLE001 — torch may be absent or already configured; not fatal
        pass


def _load(model: str) -> object:
    """Load + cache a sentence-transformers model ONCE, even under concurrency. A double-checked lock
    serializes the first load so concurrent suite threads don't race it (the cause of the configured
    model failing mid-run); after warm-up every thread reuses the one cached model. ImportError /
    load errors propagate — a configured model that cannot load is a LOUD failure, never a silent swap."""

    cached = _model_cache.get(model)
    if cached is not None:
        return cached
    with _load_lock:
        if model not in _model_cache:
            _constrain_torch_threads()
            from sentence_transformers import SentenceTransformer  # may raise ImportError

            _model_cache[model] = SentenceTransformer(model)  # load/download errors propagate (not masked)
    return _model_cache[model]


def warm(model: str | None) -> str:
    """Pre-load the configured embedding model ONCE, up front, before the suite spawns its concurrent
    subprocess/thread storm — so the heavy first load never collides with peak resource pressure and
    fail-degrade VERTEX. `model is None` (hashing) is a no-op. A NAMED model that cannot load raises
    loudly here, at a clean point, instead of silently degrading every arm mid-run."""
    if model is None:
        return "hash"
    _load(model)  # populates the process-lifetime cache; raises if the named model genuinely can't load
    return f"{'clip' if is_clip_model(model) else 'sentence-transformers'}:{model}"


def embed_texts(texts: list[str], model: str | None) -> tuple[list[list[float]], str]:
    """Unit-vector text embeddings + a backend tag. `model=None` is the EXPLICIT hashing choice
    (`GAUNTLET_VERTEX_MODEL=none`); a NAMED model is computed with that model — never silently swapped
    for hashing or any other method. A transient fd-table race is retried (the SAME model), and a
    persistent failure RAISES so the configured metric is honoured or the run fails loudly."""

    if model is None:
        return [hash_embed(t) for t in texts], "hash-fallback"
    st = _load(model)
    # retry the SAME model on a transient fd-race (legitimate — not a method change); a persistent race
    # or any real error propagates rather than masquerading as a different metric
    vectors = _proc.retry_fd_race(lambda: st.encode(texts, normalize_embeddings=True))  # type: ignore[attr-defined]
    return [list(map(float, v)) for v in vectors], f"sentence-transformers:{model}"


def embed_images(paths: list[str], model: str) -> tuple[list[list[float]], str]:
    """Unit-vector CLIP image embeddings. Raises EmbeddingUnavailable if CLIP/Pillow is missing."""

    if not is_clip_model(model):
        raise EmbeddingUnavailable(f"image embeddings need a CLIP model, got {model!r}")
    try:
        from PIL import Image  # noqa: F401 — required by sentence-transformers' CLIP image path

        st = _load(model)
    except ImportError as exc:
        raise EmbeddingUnavailable(
            f"CLIP image embedding unavailable ({exc}); install sentence-transformers + Pillow + torch, "
            "or choose --vision-judge heuristic"
        ) from exc
    from PIL import Image

    images = [Image.open(p).convert("RGB") for p in paths]
    vectors = _proc.retry_fd_race(lambda: st.encode(images, normalize_embeddings=True))  # type: ignore[attr-defined]
    return [list(map(float, v)) for v in vectors], f"clip:{model}"


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))  # inputs are unit vectors
