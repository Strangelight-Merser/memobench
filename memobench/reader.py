"""读取器：根据记忆上下文回答问题。

- RuleReader：离线、确定性，用于复现与 CI，隔离出“记忆系统本身”的能力。
- LLMReader：任意 OpenAI 兼容接口（DeepSeek、Qwen、本地 vLLM/Ollama 等）。
"""
import json
import os
import re
import urllib.request
from typing import List

from .generator import ATTRS
from .schema import ABSTAIN

_LINE = re.compile(r"我的(.+?)(?:是|现在改成)(.+?)(?:了)?。")
_FORGET = re.compile(r"请忘掉我的(.+?)，")


class RuleReader:
    name = "rule"

    def answer(self, question: str, context: List[str]) -> str:
        asked = sorted((question.find(a), a) for a in ATTRS if a in question)
        first = "最初" in question
        parts = []
        for _, attr in asked:
            value = None
            for line in context:
                f = _FORGET.search(line)
                if f and f.group(1) == attr:
                    value = None
                    continue
                m = _LINE.search(line)
                if m and m.group(1) == attr:
                    if first and value is not None:
                        continue
                    value = m.group(2)
            parts.append(value or ABSTAIN)
        return "；".join(parts) if parts else ABSTAIN


PROMPT = """你是一个具备长期记忆的 openKylin 桌面助手。下面是与该用户有关的记忆（按时间先后排列）：
{memory}

规则：只依据记忆作答；如果用户要求忘掉某信息，或记忆中没有相关信息，回答“不知道”。答案尽量简短。
问题：{question}"""


class LLMReader:
    def __init__(self, model=None, base_url=None, api_key=None):
        self.model = model or os.getenv("MEMOBENCH_MODEL", "deepseek-chat")
        self.base_url = (base_url or os.getenv("MEMOBENCH_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("MEMOBENCH_API_KEY", "")
        self.name = f"llm:{self.model}"

    def answer(self, question, context):
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": PROMPT.format(
                memory="\n".join(f"- {c}" for c in context) or "（空）", question=question)}],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()
