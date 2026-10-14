"""画像与情景日志、会话摘要，以及可选的 mem0 适配器。"""
import re
from uuid import uuid4

from .base import MemorySystem
from .baselines import _FORGET, _STATE


def _sentences(text):
    # 保留句末标点，避免同一轮中的多条事实被合并读取。
    return re.findall(r"[^。！？\n]+[。！？]?", text)


class HybridMemory(MemorySystem):
    """结构化画像定位属性，带会话时间戳的情景日志保留变更历史。"""
    name = "hybrid"

    def __init__(self):
        self.profile = {}
        self.log = []

    def observe(self, turn):
        if turn.role != "user":
            return
        for sentence in _sentences(turn.text):
            forgotten = _FORGET.search(sentence)
            if forgotten:
                attr = forgotten.group(1)
                self.profile.pop(attr, None)
                self.log = [event for event in self.log if event[2] != attr]
                continue
            fact = _STATE.search(sentence)
            if fact:
                attr, value = fact.groups()
                self.profile[attr] = value
                self.log.append((turn.session, turn.index, attr, value))

    def recall(self, question):
        attrs = {attr for attr in self.profile if attr in question}
        events = sorted(self.log, key=lambda event: event[:2])
        return [f"[会话{s}，轮次{i}] 我的{attr}是{value}。"
                for s, i, attr, value in events if attr in attrs]


class SessionSummary(MemorySystem):
    """会话结束时提取个人事实、修正和遗忘指令，丢弃闲聊。"""
    name = "session_summary"

    def __init__(self):
        self.pending = {}
        self.summaries = {}

    def observe(self, turn):
        if turn.role == "user":
            self.pending.setdefault(turn.session, []).append(turn)

    def end_session(self, session):
        turns = self.pending.pop(session, [])
        summary = self.summaries.setdefault(session, [])
        for turn in sorted(turns, key=lambda turn: turn.index):
            for sentence in _sentences(turn.text):
                if "我的" in sentence and (_STATE.search(sentence) or _FORGET.search(sentence)):
                    summary.append(sentence.strip())

    def recall(self, question):
        return [sentence for session in sorted(self.summaries)
                for sentence in self.summaries[session]]


class Mem0Adapter(MemorySystem):
    """按用例隔离用户的可选 mem0 接入，需要另行配置模型与存储。"""
    name = "mem0"

    def __init__(self):
        # 延迟导入，缺少可选依赖时不影响其他记忆系统。
        try:
            import mem0
        except ImportError as exc:
            raise RuntimeError(
                "mem0 无法加载：请安装可选依赖（python3 -m pip install mem0ai）"
                "并检查其依赖；离线评测请使用 DEFAULT_SYSTEMS。"
            ) from exc
        self.memory = mem0.Memory()
        self.user_id = f"memobench-{uuid4().hex}"

    def observe(self, turn):
        if turn.role == "user":
            self.memory.add([{"role": "user", "content": turn.text}], user_id=self.user_id)

    def recall(self, question):
        result = self.memory.search(question, filters={"user_id": self.user_id})
        events = sorted(result["results"], key=lambda event: event.get("created_at") or "")
        return [event["memory"] for event in events]
