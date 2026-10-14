"""读取器：根据记忆上下文回答问题。

- RuleReader：离线、确定性，用于复现与 CI，隔离出“记忆系统本身”的能力。
- LLMReader：任意 OpenAI 兼容接口（DeepSeek、Qwen、本地 vLLM/Ollama 等）。
"""
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

from .generator import ATTRS
from .schema import ABSTAIN

_LINE = re.compile(r"我的(.+?)(?:是|现在改成)(.+?)(?:了)?。")
_FORGET = re.compile(r"请忘掉我的(.+?)，")


class RuleReader:
    name = "rule"

    def answer(self, question: str, context: List[str]) -> str:
        asked = sorted((question.find(a), a) for a in ATTRS if a in question)
        first = any(word in question for word in ("最初", "一开始", "改之前", "原来"))
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
    """MEMOBENCH_CACHE=0 关闭缓存；CACHE_DIR 设置目录；TIMEOUT 设置秒数。

    后两项环境变量同样使用 MEMOBENCH_ 前缀。失败后最多重试三次。
    """

    def __init__(self, model=None, base_url=None, api_key=None, timeout=None):
        self.model = model or os.getenv("MEMOBENCH_MODEL", "deepseek-chat")
        self.base_url = (base_url or os.getenv("MEMOBENCH_BASE_URL", "https://api.deepseek.com/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("MEMOBENCH_API_KEY", "")
        self.timeout = float(timeout if timeout is not None else os.getenv("MEMOBENCH_TIMEOUT", "60"))
        self.cache_dir = (Path(os.getenv("MEMOBENCH_CACHE_DIR", ".cache/memobench"))
                          if os.getenv("MEMOBENCH_CACHE", "1").lower() not in ("0", "false", "off") else None)
        self.name = f"llm:{self.model}"

    def answer(self, question, context):
        prompt = PROMPT.format(memory="\n".join(f"- {c}" for c in context) or "（空）", question=question)
        cache_path = None
        if self.cache_dir is not None:
            key = hashlib.sha256(json.dumps([self.model, prompt], ensure_ascii=False).encode("utf-8")).hexdigest()
            cache_path = self.cache_dir / f"{key}.json"
            if cache_path.exists():
                return json.loads(cache_path.read_text(encoding="utf-8"))
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    answer = json.load(r)["choices"][0]["message"]["content"].strip()
                break
            except urllib.error.HTTPError as exc:
                exc.close()
                if attempt == 3 or (exc.code not in (408, 429) and not 500 <= exc.code < 600):
                    raise
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if attempt == 3:
                    raise
            time.sleep(2 ** attempt)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            # 原子替换，避免并发读取到未写完的缓存。
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_path.parent,
                                             delete=False) as f:
                temp_path = Path(f.name)
                try:
                    json.dump(answer, f, ensure_ascii=False)
                    f.close()
                    temp_path.replace(cache_path)
                finally:
                    temp_path.unlink(missing_ok=True)
        return answer
