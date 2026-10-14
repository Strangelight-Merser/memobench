from .base import MemorySystem
from .baselines import FullContext, SlidingWindow, BM25Retrieval, ProfileStore

REGISTRY = {
    "full_context": FullContext,
    "sliding_window": SlidingWindow,
    "bm25_rag": BM25Retrieval,
    "profile_store": ProfileStore,
}


def get(name: str) -> MemorySystem:
    if name not in REGISTRY:
        raise KeyError(f"未知记忆系统: {name}，可选: {', '.join(REGISTRY)}")
    return REGISTRY[name]()
