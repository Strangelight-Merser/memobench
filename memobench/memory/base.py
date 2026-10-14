from abc import ABC, abstractmethod
from typing import List

from ..schema import Turn


class MemorySystem(ABC):
    """被测记忆系统的统一接口。接入新系统（mem0、Letta、自研方案）只需实现这三个方法。"""

    name = "base"

    @abstractmethod
    def observe(self, turn: Turn) -> None:
        """接收一条对话轮次。"""

    def end_session(self, session: int) -> None:
        """会话结束钩子，可用于摘要、压缩、持久化。"""

    @abstractmethod
    def recall(self, question: str) -> List[str]:
        """针对问题返回提供给模型的记忆上下文（按时间顺序的文本行）。"""
