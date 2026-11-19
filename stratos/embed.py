"""Wrap a local CPU embedding model for the memory (task M2).

The model object is created lazily on first use by a backend callable, so importing this module never imports the
backend (fastembed) and the model is only built once.
"""


def _fastembed_backend(model, cache_dir):
    """Build the default embedding model object, importing fastembed only here."""
    import fastembed
    return fastembed.TextEmbedding(model_name=model, cache_dir=cache_dir)


class Embedder:
    def __init__(self, model=None, cache_dir=None, backend=None, max_chars=None):
        cfg = config.EMBED
        self.name = model if model is not None else cfg["model"]
        self.cache_dir = cache_dir if cache_dir is not None else cfg["cache_dir"]
        self.max_chars = max_chars if max_chars is not None else cfg["max_chars"]
        self.backend = backend if backend is not None else _fastembed_backend
        self.model = None

    def _get_model(self):
        if self.model is None:
            self.model = self.backend(self.name, self.cache_dir)
        return self.model

    def embed(self, texts):
        model = self._get_model()
        return [[float(x) for x in v] for v in model.embed([t[:self.max_chars] for t in texts])]

    def embed_query(self, text):
        model = self._get_model()
        q = getattr(model, "query_embed", None)
        vectors = q([text[:self.max_chars]]) if q is not None else model.embed([text[:self.max_chars]])
        return [float(x) for x in next(vectors)]


from stratos import config
