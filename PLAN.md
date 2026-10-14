# MemoBench 参赛计划（单人 + Codex 并行）

**赛题**：openKylin｜面向 openKylin 操作系统的智能体长期记忆自动化评测 Benchmark 设计（开源 AI 工具赛道）
**截止**：10/16 24:00 发送材料到 oscc@oschina.cn（代码仓库 + 介绍 PDF + 演示视频）

## 已完成（M0，主线）
- `schema / generator / memory(4 基线) / reader(规则+LLM) / scorer / runner / report / cli`，零依赖，离线可跑
- 6 维能力：recall / update / multi / temporal / forget / abstain，加泄露率与上下文成本
- 难度旋钮：会话数、轮数、同主题干扰句数（distract=6 时 BM25 跌到 68%，区分度成立）

## 并行任务（每个任务一个 worktree，只改自己负责的文件）
| ID | 内容 | 独占文件 |
|---|---|---|
| T1 | 单元测试 + CLI 冒烟测试（unittest，无依赖） | `tests/` |
| T2 | 进阶记忆系统：Hybrid（画像+带时间戳情景日志）、Summary（会话摘要）、mem0 可选适配器 | `memobench/memory/advanced.py`, `memobench/memory/__init__.py` |
| T3 | 报告升级：雷达图、成本-准确率散点、失败用例明细；`sweep` 难度曲线子命令 | `memobench/report.py`, `memobench/sweep.py`, `memobench/cli.py` |
| T4 | 文档：README、作品介绍（→PDF）、木兰 PSL-2 许可证、CONTRIBUTING、GitHub Actions CI | `README.md`, `docs/`, `LICENSE`, `CONTRIBUTING.md`, `.github/` |
| T5 | 数据与 LLM：问法改写多样化、多次更新链；LLM reader 重试/磁盘缓存/并发 | `memobench/generator.py`, `memobench/reader.py` |

## 时间线
- 10/14：M0 ✅，派发 T1–T5，完成报名表
- 10/15：合并、跑全量（规则读取器 + 1 个国产 LLM），修 bug；Gitee/GitHub 公开仓库
- 10/16 白天：介绍 PDF、录 3 分钟演示视频；晚上 22:00 前发邮件（留 2 小时余量）

## 演示视频脚本（3 分钟）
1. 问题：智能体“记不住/记错/忘不掉”，缺统一评测（20s）
2. 一条命令生成数据集 + 运行评测（40s）
3. 报告：雷达图看各系统能力短板，难度曲线看鲁棒性（60s）
4. 接入新系统只需实现 3 个方法（30s）
5. openKylin 场景与后续路线（30s）
