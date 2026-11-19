"""Tests for task embed: stratos/embed.py wraps a local CPU embedding model (memory M2).

config.EMBED = {"model": "jinaai/jina-embeddings-v2-base-code", "cache_dir": r"C:\\PolyStrata-data\\embeddings",
"max_chars": 2000} (jina's code model found 7 of 8 expected tower defense chunks in a top 5, bge-small 5).

Embedder(model=None, cache_dir=None, backend=None, max_chars=None): None -> the config.EMBED value (read when the
Embedder is made). backend(model, cache_dir) makes the model object; by default it is fastembed.TextEmbedding
(model_name=model, cache_dir=cache_dir), imported inside the default backend only, so importing stratos.embed never
imports fastembed. The model object is made on first use, once.
- .name -> the model name.
- .embed(texts) -> [list of floats] per text, from model.embed(<texts cut to max_chars characters>); each vector
  becomes a plain list of Python floats.
- .embed_query(text) -> list of floats from model.query_embed([cut text]) when getattr(model, "query_embed", None) is not None, else
  from model.embed([cut text])."""
import sys

from stratos import config, embed


class FakeModel:
    def __init__(self, with_query=True):
        self.seen = []
        if not with_query:
            self.query_embed = None

    def embed(self, texts):
        self.seen.append(("embed", list(texts)))
        for t in texts:
            yield [float(len(t)), 1.0]

    def query_embed(self, texts):
        self.seen.append(("query", list(texts)))
        for t in texts:
            yield [0.0, float(len(t))]


def test_config():
    assert config.EMBED["model"] == "jinaai/jina-embeddings-v2-base-code"
    assert config.EMBED["max_chars"] == 2000 and config.EMBED["cache_dir"]


def test_importing_does_not_load_fastembed():
    assert "fastembed" not in sys.modules or embed.__dict__.get("fastembed") is None


def test_embed(monkeypatch):
    monkeypatch.setattr(config, "EMBED", {"model": "m1", "cache_dir": "c1", "max_chars": 3})
    made = []
    model = FakeModel()

    def backend(name, cache_dir):
        made.append((name, cache_dir))
        return model
    e = embed.Embedder(backend=backend)
    assert e.name == "m1" and made == []
    assert e.embed(["abcdef", "ab"]) == [[3.0, 1.0], [2.0, 1.0]]
    assert e.embed_query("xyzzy") == [0.0, 3.0]
    assert made == [("m1", "c1")]
    assert model.seen == [("embed", ["abc", "ab"]), ("query", ["xyz"])]


def test_a_model_without_query_embed():
    model = FakeModel(with_query=False)
    model.query_embed = None
    e = embed.Embedder(model="m", cache_dir="c", max_chars=100, backend=lambda n, c: model)
    assert e.embed_query("ab") == [2.0, 1.0]


def test_vectors_are_plain_floats():
    class NumpyLike:
        def embed(self, texts):
            for t in texts:
                yield _Arr([1, 2])

    class _Arr(list):
        pass
    e = embed.Embedder(model="m", cache_dir="c", max_chars=10, backend=lambda n, c: NumpyLike())
    (v,) = e.embed(["a"])
    assert type(v) is list and all(type(x) is float for x in v)
