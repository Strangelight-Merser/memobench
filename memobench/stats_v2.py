"""按故事聚类的配对统计；不把改写、probe、缓存回放当独立用户。"""
from dataclasses import dataclass
import math
import random
from statistics import NormalDist, mean

from .schema_v2 import Episode, Prediction, OFFICIAL_CAPABILITIES, validate_dataset


@dataclass(frozen=True)
class Sample:
    """分数由卡3提供；None 表示未评分/不支持，不自动当作答错。"""
    prediction: Prediction
    score: float
    repeat_id: str
    execution: str

    def __post_init__(self):
        if type(self.prediction) is not Prediction:
            raise ValueError("需要 Prediction")
        self.prediction.validate()
        if self.score is not None and (type(self.score) not in (int, float) or
                                       not math.isfinite(self.score) or not 0 <= self.score <= 1):
            raise ValueError("score 必须在 0..1 或为 null")
        if self.prediction.status != "ok" and self.score is not None:
            raise ValueError("失败输出不能隐式评分")
        if not isinstance(self.repeat_id, str) or not self.repeat_id:
            raise ValueError("需要 repeat_id")
        if self.execution not in ("online", "offline", "replay"):
            raise ValueError("无效执行模式")


def wilson_interval(successes, n, confidence=0.95):
    """仅适用于合适的独立 Bernoulli 样本；不能用于故事内多题伪重复。"""
    if type(n) is not int or type(successes) is not int or not 0 <= successes <= n or not 0 < confidence < 1:
        raise ValueError("无效比例分母或置信度")
    if n == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p, z2 = successes / n, z * z
    center = (p + z2 / (2 * n)) / (1 + z2 / n)
    radius = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return [max(0.0, center - radius), min(1.0, center + radius)]


def _catalog(episodes):
    episodes = list(episodes)
    validate_dataset(episodes)
    result = {}
    for episode in episodes:
        golds = {g.probe_id: g for g in episode.golds}
        for probe in episode.probes:
            key = (probe.episode_id, probe.variant_id, probe.session_id, probe.probe_id)
            result[key] = (episode.story_id, golds[probe.probe_id].official_capabilities)
    return result


def _key(prediction):
    return tuple(getattr(prediction, k) for k in ("episode_id", "variant_id", "session_id", "probe_id"))


def _index(samples, catalog, execution):
    if execution not in ("online", "offline", "replay"):
        raise ValueError("必须选择单一执行模式")
    indexed, replay = {}, 0
    for sample in samples:
        if type(sample) is not Sample:
            raise ValueError("需要 Sample")
        sample.__post_init__()
        key = _key(sample.prediction)
        if key not in catalog:
            raise ValueError("输出引用不在数据集中")
        if sample.execution == "replay":
            replay += 1
        if sample.execution != execution:
            continue
        pair = (key, sample.repeat_id)
        if pair in indexed:
            # 缓存重复只有回放次数增加，不成为新观察。
            if execution == "replay" and indexed[pair] == sample:
                continue
            raise ValueError("同一题同一 repeat 重复")
        indexed[pair] = sample
    return indexed, replay


def summarize(episodes, samples, *, execution, expected_repeats):
    """expected_repeats 是实际计划的重复 ID，用于计算未返回结果的缺失。"""
    repeats = list(expected_repeats)
    if not repeats or any(not isinstance(r, str) or not r for r in repeats) or len(set(repeats)) != len(repeats):
        raise ValueError("需要互异的计划 repeat_id")
    catalog = _catalog(episodes)
    indexed, replay = _index(samples, catalog, execution)
    if any(repeat not in repeats for _, repeat in indexed):
        raise ValueError("出现计划外 repeat_id")
    n_expected = len(catalog) * len(repeats)
    statuses = {name: sum(s.prediction.status == name for s in indexed.values())
                for name in ("ok", "timeout", "error", "unsupported")}
    scored = [s.score for s in indexed.values() if s.score is not None]
    capabilities = {}
    for name in OFFICIAL_CAPABILITIES:
        keys = {key for key, (_, caps) in catalog.items() if name in caps}
        values = [s.score for (key, _), s in indexed.items() if key in keys and s.score is not None]
        capabilities[name] = {"n_expected": len(keys) * len(repeats), "denominator": len(values),
                              "mean": mean(values) if values else None}
    story_scores = {}
    for (key, _), sample in indexed.items():
        if sample.score is not None:
            story_scores.setdefault(catalog[key][0], []).append(sample.score)
    return {"execution": execution, "n_story": len({s for s, _ in catalog.values()}),
            "n_query": len(catalog), "n_repeat": 0 if execution == "replay" else len({r for _, r in indexed}),
            "n_repeat_planned": len(repeats), "n_expected": n_expected,
            "n_received": len(indexed), "n_replay": replay,
            "missing": n_expected - len(indexed), "unscored": len(indexed) - len(scored),
            **statuses, "timeout_rate": statuses["timeout"] / n_expected if n_expected else None,
            "error_rate": (statuses["error"] + statuses["timeout"]) / n_expected if n_expected else None,
            "micro_mean": mean(scored) if scored else None,
            "story_macro_mean": mean(mean(v) for v in story_scores.values()) if story_scores else None,
            "denominator": len(scored), "capabilities": capabilities}


def paired_bootstrap(episodes, left, right, *, execution, n_bootstrap=2000, seed=42):
    """先匹配题目与重复，再整体抽故事；估计等权故事均值 left - right。"""
    if execution == "replay":
        raise ValueError("缓存回放不用于独立采样推断")
    if type(n_bootstrap) is not int or n_bootstrap < 1 or type(seed) is not int:
        raise ValueError("无效 bootstrap 参数")
    catalog = _catalog(episodes)
    a, ar = _index(left, catalog, execution)
    b, br = _index(right, catalog, execution)
    groups = {}
    for key in sorted(a.keys() & b.keys()):
        if a[key].score is not None and b[key].score is not None:
            groups.setdefault(catalog[key[0]][0], []).append(a[key].score - b[key].score)
    values = [mean(groups[story]) for story in sorted(groups)]
    result = {"difference": mean(values) if values else None, "ci95": None,
              "n_story": len(values), "n_pairs": sum(map(len, groups.values())),
              "n_query": len({key[0] for key in a.keys() & b.keys()
                              if a[key].score is not None and b[key].score is not None}),
              "n_repeat": len({key[1] for key in a.keys() & b.keys()
                               if a[key].score is not None and b[key].score is not None}),
              "missing_or_unscored_pairs": len(a.keys() | b.keys()) - sum(map(len, groups.values())),
              "n_replay_excluded": ar + br, "seed": seed, "n_bootstrap": n_bootstrap,
              "estimand": "equal_story_mean_left_minus_right",
              "status": "ok" if len(values) >= 2 else "insufficient_stories"}
    if len(values) >= 2:
        rng = random.Random(seed)
        draws = sorted(mean(rng.choices(values, k=len(values))) for _ in range(n_bootstrap))
        def quantile(p):
            x = (len(draws) - 1) * p
            lo, hi = math.floor(x), math.ceil(x)
            return draws[lo] + (draws[hi] - draws[lo]) * (x - lo)
        result["ci95"] = [quantile(0.025), quantile(0.975)]
    return result
