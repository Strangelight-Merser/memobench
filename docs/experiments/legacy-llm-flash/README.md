# v1 legacy × DeepSeek 读取器（2026-10-14）

- 命令：`MEMOBENCH_MODEL=deepseek-flash MEMOBENCH_BASE_URL=https://api.deepseek.com/v1 python3 -m memobench.cli run --reader llm --distract 6`
- 数据：v1 模板 120 题（seed 42，distract 6），6 个记忆系统，共 720 次调用，temperature 0，单次运行（无重复、无置信区间）。
- 解释边界：v1 模板数据 + 旧版子串评分（存在 AUDIT.md 所列反例），仅作 legacy 诊断，不与 v2 / native 混榜。hybrid 等策略的抽取与模板句式耦合。
- 主要观察：全量上下文在 abstain 上降到 65%（模型会依据同主题干扰句“猜”答案），说明更多上下文并不等于更好的边界识别；profile_store 在遗忘题降到 55%。
