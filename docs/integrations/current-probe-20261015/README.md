# 当前版本完整接入与真实模型验收

2026-10-15，6.1-sol 执行、主代理独立复核。**当前桥版本的两产品完整接入检查和真实文件审计回归均通过；完整 80 条观察案例也已执行到底，其不通过结果原样保留。** 原生记忆及 Kylin 用户画像始终启用，未用关闭功能规避超时。

当前桥 SHA-256：`6b0ad695c89dc233901eca4561b73a5158db339dcef41e72932394c033da1c81`。本地与远端一致，部署备份及版本变更见 [deployment.json](audit-fix-acceptance/deployment.json)。产品版本、Kylin 源文件清单见 [product-versions.json](product-versions.json) 和 [kylin-source-inventory.json](kylin-source-inventory.json)；Kylin 部署无法现场读取 Git HEAD，以实际文件哈希标识，历史提交不充当当前观测值。模型请求别名为 `deepseek-flash`，供应商权重快照、API 请求总数和费用未知。

## 当前版本已验证结果

| 检查 | Kylin | OpenClaw |
|---|---|---|
| 完整接入 probe | 10/10 通过 | 6/6 通过 |
| 同会话、跨会话、跨案例隔离和真实文件 | 通过 | 通过 |
| 原生持久画像、prompt 注入、每轮画像终态 | 通过 | 不适用 |
| 读取目录失败后仍完成原生文件写入 | 通过 | 通过 |
| 随机新文件真实字节、当前工具调用链、清理 | 通过 | 通过 |

新版本原始记录见 [audit-fix-acceptance](audit-fix-acceptance/README.md)。主代理重新解析两次实际查询的完整原生 transcript，重算工具审计、绑定和文件哈希，确认文件原先不存在、失败读取没有被计为成功写入、实际写入内容正确且清理完成：[独立复核结果](PRIMARY_REPAIRED_BRIDGE_REVIEW.json)，[可复核脚本](review_repaired_bridge.py)。严格准备入口重新读取并验证当前完整证据，结果 [current-plan/plan.json](audit-fix-acceptance/current-plan/plan.json) 的 blockers 为空。全量 94 variants 的计划没有执行。

## 完整真实 CLI 案例的原结果

在修复审计前，预先固定一个原始完整案例，两个产品各执行 80 条观察与 1 次查询，共 162 次产品调用，无截短、无自动重试。原始公开输入逐字段与批准数据一致。主复核见 [PRIMARY_CLI_REVIEW.json](PRIMARY_CLI_REVIEW.json)，原始文件在 [cli-prepared](cli-prepared/execution-receipt.json)。

- **Kylin：**81 次原生画像处理均正常完成；最终找回 `markers/ready.txt` 和五字节 `READY`，当前 query 有真实 `write_file`。文件在观察期已创建、query 前后字节相同，因此严格 `create` 验收为 `failed/action_trace_mismatch`，没有追认为通过。
- **OpenClaw：**最终原生答复未找回约定；query 前后均存在同一正确文件，但没有新创建动作。旧审计还在目录读取失败时中断，保持 `blocked/native tool audit incomplete`。清理成功；因审计异常跳过第二次 end_session，不能声称正常走完全部会话收尾。
- 原自动语义分数保留 `pending_review`，本次明确标识的 AI 证据复核已给出上述结论，不修改历史分数，不冒充人工签收或已校准模型裁判。

该样本在观察阶段已有执行含义，而 query 的新建验收要求文件尚不存在，构成前提冲突。它能揭示真实 CLI 行为及集成问题，不能用于两产品正式排名或纯记忆能力比较。独立分析见 [CASE_APPLICABILITY_REVIEW.md](CASE_APPLICABILITY_REVIEW.md)。没有删除提前生成的文件、改题、改 gold 或重跑到成功。

## 修复与验证范围

审计现在接受原生读取的普通文本/JSON 标量，合法 workspace 根目录读取不再误判越界；失败读取作为 `succeeded=false` 事件保留。失败写入、越界写入、缺失/重复/乱序结果、transcript 前缀被替换仍拒绝。发生审计异常时，原始 transcript、失败阶段及安全固定原因码会留存，原生回答不被覆盖。

246 项测试全部通过，见 [tests-after-audit-fix.log](tests-after-audit-fix.log)。87 份受保护原始文件哈希未变，见 [FINAL_INTEGRITY.json](FINAL_INTEGRITY.json)。独立 AI 数据审核与内部使用授权沿用原记录，不要求用户填写审核表；不扩大为公开再分发许可。

本轮产品调用：旧桥完整 probe 12 次 + 原样 CLI 162 次 + 修复后完整 probe/文件回归 14 次，共 188 次。产品调用不等于供应商请求数，费用未推算。文件审计覆盖直接文件工具，未支持的 exec、删除、render 不伪装为通过。所有本轮执行已结束，无后台模型调用。
