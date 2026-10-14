from .base import MemorySystem
from .baselines import FullContext, SlidingWindow, BM25Retrieval, ProfileStore
from .advanced import HybridMemory, SessionSummary, Mem0Adapter

REGISTRY = {
    "full_context": FullContext,
    "sliding_window": SlidingWindow,
    "bm25_rag": BM25Retrieval,
    "profile_store": ProfileStore,
    "hybrid": HybridMemory,
    "session_summary": SessionSummary,
    "mem0": Mem0Adapter,
}

# CLI 默认只运行无需第三方依赖的系统，mem0 仍可显式选择。
DEFAULT_SYSTEMS = [name for name in REGISTRY if name != "mem0"]


def get(name: str) -> MemorySystem:
    if name not in REGISTRY:
        raise KeyError(f"未知记忆系统: {name}，可选: {', '.join(REGISTRY)}")
    return REGISTRY[name]()
