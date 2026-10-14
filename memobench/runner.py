import time
from collections import defaultdict
from typing import Iterable, List

from . import memory
from .schema import Case, Result, CATEGORIES
from .scorer import score


def run(cases: List[Case], systems: Iterable[str], reader) -> List[Result]:
    results = []
    for name in systems:
        for case in cases:
            mem = memory.get(name)
            for s, turns in enumerate(case.sessions):
                for t in turns:
                    mem.observe(t)
                mem.end_session(s)
            t0 = time.perf_counter()
            ctx = mem.recall(case.question)
            ans = reader.answer(case.question, ctx)
            ms = (time.perf_counter() - t0) * 1000
            ok, leaked = score(case, ans)
            results.append(Result(case.id, case.category, name, ans, ok, leaked, ms, sum(map(len, ctx))))
    return results


def summarize(results: List[Result]):
    """system -> {category: acc, overall, leak_rate, avg_ctx, avg_ms}"""
    by = defaultdict(list)
    for r in results:
        by[r.system].append(r)
    out = {}
    for sys, rs in by.items():
        row = {}
        for c in CATEGORIES:
            sub = [r for r in rs if r.category == c]
            if sub:
                row[c] = sum(r.correct for r in sub) / len(sub)
        row["overall"] = sum(r.correct for r in rs) / len(rs)
        row["leak_rate"] = sum(r.leaked for r in rs) / len(rs)
        row["avg_ctx"] = sum(r.context_chars for r in rs) / len(rs)
        row["avg_ms"] = sum(r.latency_ms for r in rs) / len(rs)
        out[sys] = row
    return out
