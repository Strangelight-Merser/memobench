# 原生完成评审执行范围独立复核

当前判定：首次待审补丁存在一个需要闭锁的新增证据边界，尚不批准部署。未调用模型、未部署或修改原生实现，旧失败证据保留。初审补丁 SHA-256 为 `c427980a5462207722f4e222d2576c0679f0d43736d82c27f982dc87f8d17dc3`；更新后需补记复核。

## 已确认的设计

读取 `format-revision/kylin-completion-source.json`、原生补丁及说明、独立测试和临时修改源码。原评审故意省略执行 system，仅获得 request/context/candidate，而 conversation_loop 传 original_user_message。这支持“评审缺失阶段范围”的诊断；profile 提取完成及任务目录为空不单独证明记忆成功。

补丁两个原生调用点都从 `agent.ephemeral_system_prompt` 显式传 execution_scope，没有从 candidate、request 或 messages 提取它。scope 单独序列化；普通无 scope payload 不变。评审通用提示解释范围与延期，并禁止其充当成功证据。未发现硬编码 observe/query 或样本答案、禁用评审、覆盖 blocked、泄露完整基础 system/profile 的代码。评审预算、输入容量、真实模型调用及结果控制流继续存在。

## 初审发现：仅 scope 可被解析为完成

新增 execution_scope 进入合法 evidence sources，但 parse_review 没有区分范围证据和完成证据。用临时源码中实际 ReviewResult/ReviewValidationError/parse_review 的 AST 离线提取执行，构造 decision=completed 且唯一 evidence.source=execution_scope，真实返回 task_completed=True；未使用模型或改原始测试。

这违反“范围不能当完成事实”的本轮边界。建议最小修复：完成判定若全部 evidence 都仅来自 execution_scope，抛固定 ReviewValidationError，沿原重试/失败闭锁流程处理；scope 与 candidate/request/可见消息的组合仍可用，非 completed 仍可仅引用 scope。测试需直接覆盖拒绝/允许边界和原控制流，不能只检查 prompt 文本。该约束不修改 MemoBench 评分，也不保证候选内容真实；它只防新增元信息成为唯一完成依据。

## 后续验收边界

离线模拟 blocked 或 completed 仅能检验控制流，不是模型理解阶段的语义证据。修复完成、独立复核并获主线程批准后，仍需新原生 imperative observe smoke、同会话 query 工具恢复及跨会话 probe；失败保留 blocked/unknown，不由桥补造完成。公开输入和原生记忆由原机制处理，不人工复制摘要。补丁说明中不得将 profile=true 直接表述成“记住约定”。

## 更新后最终复核

**当前判定更新：可由主线程批准部署此精确补丁，未发现剩余阻断；尚不代表真实语义验收通过。** 更新补丁 SHA-256 为 `74e0e09c98d6d270cbc84198a50f40f80e13ac1a064058377eb93e99187f306f`。上文初审与失败复现保留作为修复过程证据，首次补丁不得替代本次版本。

已复核新增解析门禁：在 evidence 原有非空、source 合法和 finding 校验之后，completed 若所有来源仅 execution_scope，抛固定 ReviewValidationError；原有评审重试/失败流程处理该异常，不提升为完成。mixed scope+candidate/request/message 保持原有可见证据语义；blocked/continue 仅 scope 保持非完成。未改变原有判定枚举、分数范围、预算/中止条件、真实模型评审或桥 blocked/unknown 行为，没有修改 MemoBench 评分。

本独立审查实际重跑了 8 项离线测试，全部通过（0.123 秒），命令使用文档注明的临时修改源码和原生依赖源码，Python 加 -B，不修改产品安装。测试包括真实 payload/两调用点、原请求保持、用户或 candidate 不能构造受信字段、无 scope 原形状、scope-only completed 拒绝、mixed 保持及 blocked 不提升。补丁说明已纠正 profile 完成不等于约定被记住。

适用前提：受信范围来自桥本轮固定公开阶段策略，经 CLI 原生 ephemeral_system_prompt 传递；不应推广为任意来源字符串天然可信。后续主线程仍需在 VM 原生环境核对补丁应用/源码摘要和运行同组测试，再执行新 imperative smoke 与完整 probe。真实模型可能仍判失败，应完整保留；本复核不预判模型结果、不授权回写旧证据。

## 部署后 smoke 与完整原生 probe 实证复核

已独立读取 `native-review-revision/deployment.json`、`smoke-kylin.json`、其完整原始 raw，以及 `probe-kylin/probe.json` 和全部 3 个 namespace exports；只读离线复算，未改 raw、未触发模型。

- 部署记录 patch 摘要为已批准 `74e0e09c98d6d270cbc84198a50f40f80e13ac1a064058377eb93e99187f306f`；部署后 completion_review.py / conversation_loop.py 摘要与待审修改源码记录逐一一致。部署 bridge 摘要 `66428d8276ff544a2c24234f619ac586cba8e0e876399884f7e1425a744bf02e` 与当前桥及本轮 raw control 绑定相符。VM 原生环境 8 测试、py_compile 返回码均为 0。这里核实的是已归档部署回执，不额外改变现场状态。
- Imperative smoke 的原观察包含“现在请立即创建该文件”；raw 中保存的公开文本及摘要与公开输入完全一致。observe 原生 `completion_review:completed`、profile_completed=true，任务 workspace before/after 均为空。query 阶段恢复 memory,file，原生评审及 profile 阶段均完成。不是把先前 blocked 证据改为 ready，而是另起新运行。
- Smoke query baseline 为空，after 是新建的 39 字节文件，SHA-256 为 `3acbcc27141e1e4ab3747307f6b6bcae52cdbf7583d64e58de4320b266ee5781`。原生 write_file 事件携带相同路径/内容，工具结果 bytes_written=39；audit complete=true。独立重建 Gold/Prediction 并调用现有 verify_remote_task，严格 create 判定 passed。成功结论依据任务字节与原生调用链，而非 execution_scope 或回答自称。
- 完整工程 probe 全部 3 份 export 文件摘要匹配 manifest；逐操作用 operation_evidence/inspect_export 重算绑定、已完成状态及画像/文件检查。共 2 个 observe、5 个 query；所有 observe 任务快照为空且不变，全部 turn 原生评审与 profile 阶段完成。原生画像持久化、后续 prompt 注入、跨会话昵称回忆、普通记忆跨会话、跨 case 隔离、文件任务及 cleanup 检查全通过；各 namespace closed=true。重新调用 acceptance_passed 返回 true。

**实证结论：本次 Kylin 专用 imperative smoke 和完整工程 probe 通过；新增范围传递已在这些真实路径上解除此前观察阶段上下文缺失造成的阻断，同时保留严格文件证据门禁。** 这不证明所有观察均能被记住，也不代表正在另行执行的 cli-final 80 观察真实案例或两产品最终验收已通过。旧失败、初审发现与新运行均独立保留。

## Kylin 原始完整案例独立复算

另行读取 `PRIMARY_KYLIN_COMPLETE_RUN_REVIEW.json`、cli-final/raw-kylin 的完整原始导出和 run-kylin/cases 原始 case，核对精确 story `e6a7a9059f826b02f8edd920` + variant `d012611aa89b90909fcea7b9`。公开输入与当前数据精确一致；80 条 observe 的任务快照均为空且不变，80 observe+1 query 的原生评审和 profile 阶段均完成。操作计数为 reset 1、begin 2、observe 80、end 2、query 1、close 1，全部 completed 且 closed=true；raw/case 摘要与主复核记录一致。

本独立审查从原始 native_records 重新运行 native_file_audit，得到与已存 audit 完全相同的结果，再用原 Gold/Prediction 运行 verify_remote_task，严格 READY create 为 passed。此完整运行属于桥 `66428d8276ff544a2c24234f619ac586cba8e0e876399884f7e1425a744bf02e`。它可保留为该版本真实通过的证据；后续仅 OpenClaw 工具呈现配置变更不能把它改称新桥同 hash 的运行，亦无需无因重放 80 条。新桥差异范围和 Kylin 新工程 probe 需分别记录核验。
