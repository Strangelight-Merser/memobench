# 观察摄入与任务执行分阶段

根因是旧桥对 observe/query 使用同一组可写任务工具。两产品曾在观察阶段创建 READY 文件，最终 query 的严格 create 条件因此不成立；旧案例及失败报告保留，不通过删除提前文件或放宽评分修复。

待审实现只改桥、阶段回归和此前自建测试的夹具。Kylin observe 使用原生 memory toolset，query 恢复 memory,file；原生 session resume 不变，memory/profile 不关闭。原生 CLI 读取 HERMES_EPHEMERAL_SYSTEM_PROMPT 并作为附加系统提示传给 AIAgent，阶段说明通过此独立入口提供，不拼接公开 observation。OpenClaw 使用原生 agents.defaults.workspace 指向 agent-workspace、defaults.cwd 指向任务 workspace；AGENTS.md 承载阶段说明，MEMORY.md 与 memory/ 保持原生写入。

每次进程仍在同一 case home、原生 session 运行。observe 单独只读挂载任务 workspace，query 恢复可写；原生 state 与记忆空间继续可写。OpenClaw 阶段 AGENTS.md 单文件始终只读挂载，桥只在产品进程外更新它。实际 argv（无密钥）、未改写的公开文本/sha、独立策略全文/sha均随每轮原始证据保存。observe 的真实任务快照前后必须一致，不一致保留原生回答及失败证据，不能返回 ready。

OpenClaw 原生源码 agent-scope-config-CDYpzA0r.mjs 的 resolveAgentRunCwd 独立解析 cwd；system-prompt-config-DxXh6YX8.mjs 显示 Directory Roles。workspace-ZTBSFGyP.mjs 中 skipBootstrap 仅控制 ensureBootstrapFiles，现有 AGENTS 由 loadWorkspaceBootstrapFiles 读取。无模型实际调用该加载函数，两轮变更均加载当前文本，见 native-bootstrap.json。

无模型真实 bwrap 验证见 mount-permissions.json：两产品 observe 直接路径、绝对路径、../及符号链接写入被 EROFS 拒绝；任务目录 rename/rmdir 被 EBUSY 拒绝；记忆/state仍可写；query任务可写。OpenClaw AGENTS 两阶段均只读。首次探针断言将 Kylin 不使用的 AGENTS 文件误判为应只读，已修正为仅 OpenClaw 策略文件要求只读；没有模型调用或运行产品。

原生记忆根的文件轨迹单独存 memory_events，不计入 task events。其他越界路径、失败写入和严格 create 检查保持闭锁；本轮不修改 native_artifacts/scoring/judge 等审核 RULE_FILES，也不声称已覆盖遗忘或 memory_events 的完整隐私评分。

6 项新阶段测试及 5 binding / 7 audit / 11 artifact 测试通过。tests-before/ 保存获主复核批准调整前的三个自建工程测试；fixture-adjustments.diff 仅显式 phase 参数与隔离审计测试中的 phase 准备 mock，未删除或弱化原断言。尚未部署，也未开始本轮模型验收；需主复核通过后以新完整 probe 验证原生记忆、query工具恢复及阶段刷新，再执行原定完整80观察case。

## 实施后状态

以上初始方案记录保留。阶段测试现为 8 项，仓库全量 254 项通过；桥已部署，原生完成评审另有 execution_scope 补丁。完整真实文件案例两产品均通过，OpenClaw 仅两项原生工具展示配置修复；版本、失败记录及边界以 [最终验收](README.md) 为准。
