import importlib
from functools import lru_cache


@lru_cache(maxsize=1)
def get_rag_service():
    return importlib.import_module('rag_service')


class _LazyRagServiceProxy:
    def __getattr__(self, name):
        return getattr(get_rag_service(), name)


rag_service = _LazyRagServiceProxy()