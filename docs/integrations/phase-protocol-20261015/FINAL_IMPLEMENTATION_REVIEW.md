# 阶段协议实现独立复核

结论：当前实现未发现阻断进入新协议合成/真实验收的实质问题；通过范围为代码与现有无模型权限证据复核，不代表产品原生记忆或完整案例已经通过。复核桥 SHA-256 为 `f902baf78d332e13160234c624d2714a4786e836d5e5a635a73465fd04e3a0cd`。未部署、未调用模型、未修改桥、测试或冻结的历史结果。

## 已核对

- 读取当前桥全文相关入口、6 项阶段测试、`fixture-adjustments.diff`、`IMPLEMENTATION.md`、`check-mount-permissions.py` / `mount-permissions.json` 和 `native-bootstrap.json`。本次不重复运行主线程正在统一执行的测试。
- observe 的任务目录以独立只读 mount 覆盖在可写 HOME 内，query 不增加该覆盖。实际 VM 四组合记录与当前桥摘要一致：observe 相对/绝对/../和符号链接写入均 EROFS；同 UID 对任务根 rename/rmdir 均 EBUSY。因此可写 HOME 父目录没有在所测操作中绕过任务挂载。两产品 query 任务写入可用。
- 原生记忆和状态保留可写；OpenClaw 阶段 AGENTS 文件通过单文件 ro-bind 保护，observe/query 内直接覆盖均 EROFS。Kylin 不使用该文件，权限探针对此没有误设成功条件。
- OpenClaw 配置独立 agent workspace 与任务 cwd，不使用会同时覆盖两者的 CLI --cwd。桥仅在产品进程外刷新阶段 AGENTS，不代写 MEMORY.md/memory。原生 bootstrap 函数两阶段真实加载不同现有 AGENTS 的证据存在；skipBootstrap 不阻止该加载。该函数级证据尚不等同于完整模型请求级证据。
- Kylin 使用原生环境入口 HERMES_EPHEMERAL_SYSTEM_PROMPT。另经只读 SSH 核对固定安装源码：cli.py:2818–2822 每个 CLI 实例从环境读取；cli.py:4600 传入 agent；agent/agent_init.py:205 赋给 ephemeral_system_prompt；agent/chat_completion_helpers.py:959–960 与 agent/conversation_loop.py:1199–1200 将其附加到 effective_system，未替换原生 system/profile。resume 仍保留原 session ID；query 恢复 memory,file 工具。请求级阶段刷新仍需后续真实 probe 验收。
- 原始公开文本作为独立 argv 参数原样送入产品，阶段策略不拼入 observation/query；每轮保存实际 argv、公开文本及摘要、独立策略。observe 快照出现变化会保留原生回答、标记失败且返回 unknown，不能当 ready。
- 绝对 agent-workspace 根下文件事件单独进入 memory_events；任务路径进入 events，现评分只从 events 获取 write。因此 MEMORY.md 写入不能满足 READY create。路径含 ..、失败 write、缺失/重复/乱序工具结果和 transcript prefix 检查仍闭锁。memory_events 仍保存原生调用和结果，并非把失败吞掉。
- 旧自建测试夹具调整只增加显式 phase 或隔离 phase 准备的 mock；读取的 diff 未删除或弱化原断言。新测试验证工作目录、公开文本、resume ID、原生配置保留、阶段限制及事件作用域。

## 保留边界与验收门禁

1. 尚未据以上证据认定“产品记住了”：需要新完整 probe 验证两会话原生存储/检索、query 工具恢复和阶段说明实际刷新，之后才执行原定 80 观察精确 story+variant 案例。若产品选择不存储或无法检索，保留失败，不由桥补做。
2. 无模型 mount 探针验证任务根 rename/rmdir 和常见绕行；它不是任意恶意进程攻击的完整证明。阶段策略文件的保证包括所开放工具下的单文件只读，不应扩大为整个可写 agent-workspace 父目录不可移动的安全声明。
3. memory_events 根级分类覆盖该 agent workspace 任意子文件，不仅 MEMORY.md/memory。当前遗忘评分不会扫描 memory_events，不能宣称已覆盖其完整隐私/遗忘语义。本轮 READY create 无此策略；不据此修改评分或推广到全部任务类别。
4. Kylin observe memory-only 和 OpenClaw observe 可写原生记忆是各自现成产品能力；这是明确声明的新阶段协议，需与旧 unrestricted CLI 结果分开报告，不能回写旧分数。
5. 原始证据、原始观察、gold 和评分保持原状。后续若桥摘要改变，本复核不能自动覆盖变更；应针对差异追加复核。

## OpenClaw 直接 schema 两配置修复复核

独立读取 `direct-tools-revision/check-native-catalog.py` / `native-catalog.json` 及测试日志，并只读 SSH 取当前已部署桥源码与待部署本地源码比较。实际 diff 仅 OpenClaw configure 的 tools 增加 toolSearch=false、codeMode=false；原 allowlist、Kylin 配置/调用、阶段策略和审计代码完全不变。旧部署摘要为 `66428d8276ff544a2c24234f619ac586cba8e0e876399884f7e1425a744bf02e`；新待部署摘要为 `d1e29805c756dd99aff69d2f4a906f52163d87df274000d64acedc99daaf541d`。

无模型证据脚本确实在临时 HOME/公开合成配置中调用安装版本的 createOpenClawCodingTools 和 applyToolSearchCatalog，只构造工具定义，不 execute 工具、不调用 provider/model。输出 write schema required 同时含 path/content，read/edit 和 memory_search/memory_get schema 保留；tool_search_enabled=false、compacted=false、tools_same_reference=true，无 tool_call/tool_search。工厂输出另含 apply_patch 派生工具，故不能声称最终工具输出恰好为五项，亦不能把此工厂检查当最终请求策略过滤证据。原配置 allowlist 仍是五项，没有扩大授权。

完整测试日志为 254 项通过。当前没有阻断部署这两个配置项的问题；部署后仍需原生真实 probe/新 OpenClaw 完整案例确认实际模型请求工具表面与严格任务结果。旧桥 Kylin 80 观察通过结果可按原摘要保留；新桥 Kylin 工程 probe 应另记新摘要与运行，不称同一次/同 hash，也不因无关 OpenClaw 配置变更重复其 80 条。

## 新桥 d1 部署后完整接入验收独立复核

已读取 direct-tools-revision 的 receipt/deployment、两产品 probe 报告及全部原始 exports、OpenClaw imperative smoke 与原始 raw。所有运行绑定新桥 `d1e29805c756dd99aff69d2f4a906f52163d87df274000d64acedc99daaf541d`；5 份 probe export 摘要逐一匹配，namespace 均 closed。独立调用 inspect_export/acceptance_passed 重算，两产品完整工程 probe 均 passed，共 12 个产品 turn；Kylin 原生评审/profile 均完成。OpenClaw 另有 smoke 2 turn，合计 14 turn，不等同 provider 请求数。

实际 OpenClaw smoke 证据显示：observe 任务 workspace 前后均空，自主调用 memory_search/read/write 将约定保存到原生 agent-workspace/MEMORY.md；query 使用原生直接 write/read 创建任务文件。完整原始 native_records 没有用 tool_call 包装这些调用。实际 systemPromptReport tools.entries 包含 read/edit/write/apply_patch/skills_read/memory_search/memory_get；两阶段 schemaChars=1908，write schemaChars=191、propertiesCount=2，工具摘要无 tool_call。原生记忆写入保留，未由桥代写记忆。

对 smoke 原 Gold/Prediction 与快照独立调用 verify_remote_task，空 query baseline、新建精确字节和原生成功 write 链使严格 create passed；不以 scope 或候选回答代替执行证据。两产品完整 probe + 此 smoke 构成当前新桥完整接入验收通过的证据。实际派生工具另有 apply_patch/skills_read，不能把配置 allowlist 五项误称最终 schema 只有五项。

范围限制：本结论不是新 OpenClaw 80 观察案例完成；该案例已在 cli-openclaw-direct-schema 独立运行，需最终 raw 出齐后再复算。此前旧桥 OpenClaw 包装/失败写入结果继续保留，不追认为通过。Kylin 80 条完整案例仍明确属于旧桥 664 版本，另有本轮新桥工程 probe 证明其接入无回归。
