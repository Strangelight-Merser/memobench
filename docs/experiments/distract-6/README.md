# distract-6 实验归档

2026-10-14，Python 3.13.12，代码基点 `7d8334882baff6f6e270a2a6fdf874a72228268a`，本次未修改源码。规则读取器、seed=42、每类 20 条、6 个会话、每会话目标 8 条用户消息、每个相关属性 6 条干扰，共 120 条用例、6 个默认系统、720 条系统评测记录。

```sh
python3 -m memobench.cli run --distract 6 --out docs/experiments/distract-6
```

本目录保存单档汇总、720 条逐例结果与 HTML 报告。

固定数据由同版本生成器按上述参数导出，文件哈希见 [metadata.json](metadata.json)。耗时为本机测量值，重跑会变化。规则读取器结果仅作为模板范围内的“记忆系统上限能力”；LLM 端到端结果待补。
