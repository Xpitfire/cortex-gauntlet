"""Shared embedding honesty: hashing is an explicit choice; a named model that fails is surfaced,
never silently swapped; image embeddings require CLIP and raise when unavailable."""

import math

import pytest

import gauntlet.analysis.embedding as emb
from gauntlet.analysis.embedding import EmbeddingUnavailable, embed_images, embed_texts, is_clip_model


def test_none_model_selects_hashing_and_is_unit_normed():
    vecs, backend = embed_texts(["home page header", "cart totals"], None)
    assert backend == "hash-fallback"
    assert len(vecs) == 2
    assert abs(math.sqrt(sum(x * x for x in vecs[0])) - 1.0) < 1e-6


def test_named_model_with_missing_library_raises_never_silently_swaps(monkeypatch):
    # a CONFIGURED model must be used or fail loudly — never silently swapped for hashing. If the
    # library is absent the user must see it (install it, or explicitly choose GAUNTLET_VERTEX_MODEL=none)
    monkeypatch.setattr(emb, "_load", lambda model: (_ for _ in ()).throw(ImportError("no st")))
    with pytest.raises(ImportError):
        embed_texts(["x"], "all-MiniLM-L6-v2")


def test_named_model_load_failure_raises_never_silently_swaps(monkeypatch):
    monkeypatch.setattr(emb, "_load", lambda model: (_ for _ in ()).throw(RuntimeError("corrupt")))
    with pytest.raises(RuntimeError):
        embed_texts(["x"], "all-MiniLM-L6-v2")  # a real failure must surface, not become hashing


def test_persistent_encode_fd_race_raises_does_not_swap_to_hashing(monkeypatch):
    # a configured model that persistently can't run must FAIL LOUDLY (so the run surfaces it), NOT
    # silently produce a hash-based number that masquerades as the configured VERTEX metric
    class _Racing:
        def encode(self, *_a, **_k):
            raise ValueError("bad value(s) in fds_to_keep")

    monkeypatch.setattr(emb, "_load", lambda model: _Racing())
    with pytest.raises((ValueError, __import__("subprocess").SubprocessError)):
        embed_texts(["home page", "cart totals"], "all-MiniLM-L6-v2")


def test_non_race_encode_error_still_propagates(monkeypatch):
    class _Broken:
        def encode(self, *_a, **_k):
            raise RuntimeError("genuine encode bug")

    monkeypatch.setattr(emb, "_load", lambda model: _Broken())
    with pytest.raises(RuntimeError):  # a real encode bug must surface, not silently become hashing
        embed_texts(["x"], "all-MiniLM-L6-v2")


def test_image_embeddings_need_a_clip_model():
    assert is_clip_model("clip-ViT-B-32") and not is_clip_model("all-MiniLM-L6-v2")
    with pytest.raises(EmbeddingUnavailable):
        embed_images(["/nonexistent.png"], "all-MiniLM-L6-v2")


def test_image_embeddings_raise_when_clip_deps_missing(monkeypatch):
    monkeypatch.setattr(emb, "_load", lambda model: (_ for _ in ()).throw(ImportError("no torch")))
    with pytest.raises(EmbeddingUnavailable):
        embed_images(["/nonexistent.png"], "clip-ViT-B-32")  # no image hashing fallback — must surface
