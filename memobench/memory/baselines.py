"""四个参考基线，覆盖主流长期记忆方案的典型取舍。"""
import math
import re
from collections import Counter, defaultdict
from typing import List

from ..schema import Turn
from .base import MemorySystem


class FullContext(MemorySystem):
    """全量上下文：上限参考，成本最高。"""
    name = "full_context"

    def __init__(self):
        self.turns: List[Turn] = []

    def observe(self, turn):
        self.turns.append(turn)

    def recall(self, question):
        return [t.text for t in self.turns if t.role == "user"]


class SlidingWindow(FullContext):
    """滑动窗口：只保留最近 N 条用户消息，模拟有限上下文。"""
    name = "sliding_window"

    def __init__(self, size=12):
        super().__init__()
        self.size = size

    def recall(self, question):
        return super().recall(question)[-self.size:]


def _grams(text):
    text = re.sub(r"\s+", "", text.lower())
    return [text[i:i + 2] for i in range(len(text) - 1)]


class BM25Retrieval(FullContext):
    """向量/关键词检索式 RAG 的代表：字符二元组 BM25，取 top-k 后按时间排序。"""
    name = "bm25_rag"

    def __init__(self, k=4, k1=1.5, b=0.75):
        super().__init__()
        self.k, self.k1, self.b = k, k1, b

    def recall(self, question):
        docs = super().recall(question)
        if not docs:
            return []
        toks = [_grams(d) for d in docs]
        avg = sum(map(len, toks)) / len(toks)
        df = Counter(g for t in toks for g in set(t))
        n = len(docs)
        scores = []
        for i, t in enumerate(toks):
            tf = Counter(t)
            s = 0.0
            for g in set(_grams(question)):
                if g not in tf:
                    continue
                idf = math.log(1 + (n - df[g] + 0.5) / (df[g] + 0.5))
                s += idf * tf[g] * (self.k1 + 1) / (tf[g] + self.k1 * (1 - self.b + self.b * len(t) / avg))
            scores.append((s, i))
        top = sorted(i for s, i in sorted(scores, reverse=True)[: self.k] if s > 0)
        return [docs[i] for i in top]


_STATE = re.compile(r"我的(.+?)(?:是|现在改成)(.+?)(?:了)?。")
_FORGET = re.compile(r"请忘掉我的(.+?)，")


class ProfileStore(MemorySystem):
    """结构化画像：抽取键值事实并原地覆盖，支持删除。省 token、更新强，但丢失历史。"""
    name = "profile_store"

    def __init__(self):
        self.profile = {}

    def observe(self, turn):
        if turn.role != "user":
            return
        m = _FORGET.search(turn.text)
        if m:
            self.profile.pop(m.group(1), None)
            return
        m = _STATE.search(turn.text)
        if m:
            self.profile[m.group(1)] = m.group(2)

    def recall(self, question):
        return [f"我的{k}是{v}。" for k, v in self.profile.items()]
