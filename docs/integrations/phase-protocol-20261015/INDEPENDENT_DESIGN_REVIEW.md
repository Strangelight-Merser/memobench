# 独立阶段协议设计复核

状态：设计约束已复核，尚未据此宣称实现、隔离或真实重验通过。本报告不修改被冻结的 current-probe 原始证据、数据、gold 或评分。

## 原问题与最小边界

真实 CLI 把 observe 当带工具的 user turn，可能在观察期直接创建最终任务文件。既有 create 验收要求 query 前文件不存在，故不能靠删除提前文件、改 gold 或事后放宽判定解决。协议应明确：observe 可更新产品原生记忆，但任务交付物仅在 query 阶段可写；原始 observation.text/query 必须保留，不改写成另一份任务。

## 读取过的依据

- `docs/spec-v0.2.md` 的“适配器合同”要求 ready 可供后续读取、同一 episode 跨会话不重复 reset，native Prediction 必须来自产品；flush/restart/storage inspection 需实际实现与举证。
- `memobench/protocol_v2.py` 的 observe 接收原 Observation、验证作用域并返回 receipt，合同没有实现阶段文件权限。
- 旧桥 `tools/native_vm_product.py` 的 sandbox/configure/invoke 将 OpenClaw agent workspace 与 cwd 合在 `/home/mb/case/workspace`，允许 read/write/edit/memory_search/memory_get。Kylin 状态位于独立 `.kylin-agent-runtime`。这使“全禁 observe 文件写入”对两个产品具有不等价影响。
- 通过只读 SSH 读取固定安装 `/home/mb/memobench-native/openclaw/node_modules/openclaw/dist/agent-scope-config-CDYpzA0r.mjs:442–445`：`resolveAgentRunCwd` 使用 agent `cwd` 或 `agents.defaults.cwd`，注释明确任务目录不改变 agent workspace。
- 同安装 `system-prompt-config-DxXh6YX8.mjs:630–641` 原生区分 runtimeCwd/workspaceDir；不同目录时提示 Working directory 为 tools/deliverables，Agent workspace 为 AGENTS.md/SOUL.md/MEMORY.md/memory。
- `config-utils-DnfHy8-v.mjs:65–90` 从 agents workspace 解析原生记忆根；memory search extraPaths 仅扩展检索路径，不能当作写入权限隔离。
- `agent-runner-memory-CyRPqp5o.mjs:676` 的自动 memory flush 条件排除 CLI；不能据成功 CLI 返回宣称 Gateway flush 已执行。
- 执行 agent 补充的现场证据：旧 OpenClaw observe 曾通过原生 write 更新 workspace/MEMORY.md；`register.agent-turn-DATo_DHf.mjs` 的 `--cwd` 描述会同时设置 agent workspace 与工具 cwd。因此应核实配置 cwd 的实际传递，避免该 CLI flag 再合并两目录。此项为协作证据，实施验收仍须独立核对实际运行配置和轨迹。

## 可验收约束与反例

1. **保留原生记忆。** OpenClaw 使用独立 agent workspace 和任务 cwd；observe 保留原生 write/edit 的记忆能力。Kylin 保留其原生 memory/profile/state。由产品自行决定是否存储和检索，不由桥代写 MEMORY.md、profile 或摘要。
2. **任务目录阶段权限。** observe 用 OS 层只读任务挂载；query 使用同一持久化任务目录可写挂载。仅 tools.allow/deny、cwd 或提示语不足以形成路径级权限证据。
3. **防父目录绕过。** 同 UID 不应能从可写父目录重命名、删除或替换只读任务根；必须实际尝试 rename/unlink/recreate，及绝对路径、`..`、符号链接绕行。应检查挂载目标本身是否受到 mountpoint 保护，而非只验证根内 write 失败。保留记忆父目录可写不等于允许替换任务根。
4. **原始输入。** 原 Observation 文本和角色按原协议送达；额外阶段约束应使用产品真实的 system/config 入口并留存。不能把原文拼接改写、人工解释答案或注入 gold 路径/字节。若无可靠公开入口，应明确记为能力限制，不能伪称系统级约束。
5. **事件作用域。** task workspace 的原生直接写事件才可作为评分 write；memory workspace 事件单独保留为 memory_events，不进入 task writes。越界任务写、失败 write、重复/缺失/乱序结果及 prefix 替换继续拒绝。memory_events 不是可任意吞掉异常的兼容通道。
6. **失败如实呈现。** observe 尝试创建 task 文件必须被拒绝，且阶段快照不变；产品仍可自行写原生记忆。query 新建文件必须字节精确、首次出现并有成功原生 write 链。产品因为限制无法完成记忆或 query 时，记录失败，不由桥补做。
7. **隔离与续存。** 同 episode 的两会话保留记忆，不同 episode 不共享；每个阶段配置/桥摘要、原始 transcript、目录快照、失败固定原因码和 cleanup receipts 可复核。
8. **新运行。** 合成无模型权限检查先通过，再进行完整真实观察和查询。新协议与旧无阶段限制结果分别保存；不覆盖旧失败、不回写旧分数，不把有限案例推广为产品排名。

## 后续独立实现审查

执行 agent 完成后，对实际 diff 与其合成/运行证据核验以上约束，尤其同 UID 父目录重命名、memory_events 与 task writes 的边界，以及产品原生 system 入口。此文件记录设计依据，不预先认可尚未检查的实现。
