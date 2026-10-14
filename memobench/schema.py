from dataclasses import dataclass, field, asdict
from typing import List, Optional

CATEGORIES = {
    "recall": "单点回忆：早期会话中的事实能否在多轮后被召回",
    "update": "知识更新：事实被修改后能否给出最新值",
    "multi": "多事实聚合：一次问题需要组合多条记忆",
    "temporal": "时序推理：能否回答“最初/之前”的值",
    "forget": "主动遗忘：用户要求删除后不应再泄露",
    "abstain": "拒答：从未提及的信息应回答不知道",
}

ABSTAIN = "不知道"


@dataclass
class Turn:
    session: int
    index: int
    role: str
    text: str


@dataclass
class Case:
    id: str
    category: str
    sessions: List[List[Turn]]
    question: str
    answers: List[str]          # 全部需要命中；[ABSTAIN] 表示应拒答
    forbidden: List[str] = field(default_factory=list)  # 不应出现的值（遗忘/过期）

    def to_dict(self):
        return asdict(self)

    @staticmethod
    def from_dict(d):
        sessions = [[Turn(**t) for t in s] for s in d["sessions"]]
        return Case(d["id"], d["category"], sessions, d["question"], d["answers"], d.get("forbidden", []))


@dataclass
class Result:
    case_id: str
    category: str
    system: str
    answer: str
    correct: bool
    leaked: bool
    latency_ms: float
    context_chars: int
