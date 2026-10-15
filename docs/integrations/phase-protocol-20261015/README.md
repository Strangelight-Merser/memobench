# 观察阶段与最终文件任务：真实验收通过

Kylin、OpenClaw 均完成原始完整案例并通过严格文件任务验收：每款产品 80 条观察、2 个会话、1 次查询。所有观察阶段的任务目录始终为空，最终查询各自新建 `markers/ready.txt`，精确内容为 5 字节 `READY`，没有换行。原生写入调用、返回结果、文件快照与哈希相互一致，清理成功。

| 产品 | 完整运行桥摘要 | 观察 | 最终任务 | 原生画像 | 主复核 |
|---|---|---:|---|---|---|
| Kylin | `66428d82…` | 80/80 | passed | 81/81 完成 | [逐条复算](PRIMARY_KYLIN_COMPLETE_RUN_REVIEW.json) |
| OpenClaw | `d1e29805…` | 80/80 | passed | 不适用；原生记忆启用 | [逐条复算](PRIMARY_OPENCLAW_COMPLETE_RUN_REVIEW.json) |

当前部署桥为 `d1e29805c756dd99aff69d2f4a906f52163d87df274000d64acedc99daaf541d`。相对 Kylin 完整运行使用的 `66428…`，仅 OpenClaw 原生工具展示配置有两项差异；Kylin 执行、阶段、工具与原生源码未变。新桥下 Kylin 10 项、OpenClaw 6 项完整接入探针及 OpenClaw 阶段验证均通过，独立复核支持保留 Kylin 原完整案例结果，不将不同桥版本混称为同一次运行。

## 修复内容

观察文本和最终问题原文保持不变。独立系统指令标明当前阶段：观察阶段只读挂载任务目录，原生记忆目录仍可写；查询阶段开放任务写入。每条观察都记录目录前后快照，没有删除提前生成的文件来伪造新建条件。

Kylin 的原生完成评审此前遗漏阶段说明，把历史观察中的命令当作本轮必须执行的任务。现在由可信调用方单独传入 `ephemeral_system_prompt`；阶段说明只用于解释范围，不能单独作为完成证据。原生评审、画像和记忆均保持启用，blocked 不提升为 completed。

OpenClaw 的完整观察序列暴露了原生工具目录压缩问题：模型通过 `tool_call` 包装调用 write，先因缺少 content 失败，再成功写入。该轮仍保留为失败。最终修复仅使用产品支持的 `tools.toolSearch=false`、`tools.codeMode=false`，直接提供完整工具 schema；原有 allowlist 和记忆功能不变。没有加入包装兼容层，未识别的调用、失败写入仍按原严格审计处理。原生实际工具还包括派生的 `apply_patch`、`skills_read`，不声称只有配置列出的五项。

## 验证与原始证据

仓库 254 项测试通过；Kylin 原生 VM 环境补丁 8 项测试通过。两款产品最终文件均为新建，SHA-256 为 `c2e3ac47f4a325469c1a2d5f117e463ec943c721986d5d9f09ac4540b7d80526`。

- [独立最终验收复核](FINAL_ACCEPTANCE_REVIEW.md)
- [当前桥完整接入回执](direct-tools-revision/receipt.json)
- [原生工具 schema 实测](direct-tools-revision/native-catalog.json)
- [Kylin 完整运行原始证据](cli-final/raw-kylin/2cea8868451a41d7afdc4c52a23a4656.json)
- [OpenClaw 完整运行原始证据](cli-openclaw-direct-schema/raw-openclaw/223c691091f14ffaa424d8cffaeaa15c.json)
- [OpenClaw 成功运行及清理回执](cli-openclaw-direct-schema/execution-receipt.json)
- [原生评审补丁复核与初审问题](NATIVE_REVIEW_SCOPE_REVIEW.md)
- [原始数据、历史证据和评分文件冻结摘要](before.json)
- [最终保留检查](PRESERVATION_AND_SCAN.json)
- [调用范围及停止约束](SCOPE.json)

旧的标点不匹配、原生评审 blocked、OpenClaw 包装调用失败和上轮提前创建文件的负结果均保留，不改为 passed。具体见本目录 `probe-kylin`、`format-revision/smoke-kylin.json`、[OpenClaw 失败摘要](cli-final/OPENCLAW_FAILURE_PRESERVED.json) 和 [上轮验收](../current-probe-20261015/README.md)。

## 结论边界

本次通过的是已暴露合成案例的完整真实产品接入与文件任务回归，不是 94 变体全数据集跑分、未见留出或产品排名。通用语义 judge 未配置，其原始 `score.status=pending_review` 保持原样；本案例的文件任务通过状态由未修改的严格文件评分器及主代理、独立 AI 复算证实，不以语义评分状态代替文件验证。

本次共 295 次产品调用，包含保留的失败运行和有明确代码/配置修订后的新运行，无自动重试。产品内部模型请求数和费用不可精确观察，均不编造为零。达到本轮验收范围后停止模型调用。
