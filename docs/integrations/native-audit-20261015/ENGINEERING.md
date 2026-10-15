# 远端真实文件审计与人工审批闭环 · 2026-10-15

工程通道已接通；数据与许可仍未签收，正式评测没有放行。保留了全部原始数据、既有测试、产品补丁及历史证据。主 agent 的 87 份保护文件哈希核对结果见工作区 deliverables/remote-audit-approval-review-20261015/。

## 真实执行与边界

- 真实 Kylin、OpenClaw 各执行了 **1 次全新合成开发 query**，均完成公开指定的随机文件写入，真实文件核验 passed，cleanup ready。没有自动重试、没有跑候选或正式 test。这里的 2 次是产品 query 数，不能当作供应商 API 请求数；费用和 token 用量不可得时仍为 null。
- `real-developer-001/` 保留公开输入、完整原生 Prediction、当前操作 checkpoint、实际字节 base64/哈希、当前产品 session 的原生文件工具轨迹、原始 namespace 导出及清理回执。这是基础开发验收，不能替代九项跨会话接入验收或正式准确率。
- `remote-synthetic-002/` 的 4 个合成 cases 验证了真实 SSH、bwrap reset 隔离、文件和 SQLite 读取，含 OpenClaw 的 Node24 SQLite/zstd 解码。它替换了产品 invoke 和画像读取，明确不是实际产品调用结果。首次合成失败（画像 inspector fixture 不完整）保留在 `remote-synthetic/` 与对应 command.log，没有覆盖。

## 远端文件验收如何工作

`SSHVMTransport → bridge artifact_checkpoint → 原生 query → bridge artifact_evidence → NativeAdapter → verify_remote_task`。

评测器只把公开输入、run/namespace/session/operation 标识传入产品侧，gold 和文件预期哈希始终留在本地。bridge 在调用前后独立读取 workspace 的实际字节，拒绝符号链接、硬链接、特殊文件和越界路径；不导出产品数据库或画像作为任务文件。每文件上限 256 KiB、workspace 总计 512 KiB，超过或读取不完整就闭锁，不截断证据。SSH 响应亦有现有 4 MiB 上限。

Kylin 从固定版本 messages 表读取；OpenClaw 从固定版本 transcript_events 表读取，并用 VM 自带 Node24 处理 JSONB/zstd。只导出当前产品 session、本次 checkpoint 之后的 workspace 文件工具调用与对应结果。前缀变更/截断、重复 ID、结果先于调用、工具名不匹配、缺结果均不能证明执行。原生轨迹仅作佐证，主要证据是宿主侧字节与变化；这不构成对产品恶意重写自身日志的防篡改证明。

当前可验证的是直接 `write_file` / `write` 创建新文件及准确内容。支持多产物逐项验收、已预置文件负例、明确 old_paths 负例、删除检测、字节/哈希失配、错 session/operation 和不完整审计。render 的模板来源不能据此证明，正式入口会预先阻断。exec、未覆盖的原生写入方法、无轨迹变更或删除保留 unsupported/blocked，不猜任意 shell 命令含义，不把它们当作已验证成功。只有经人批准的机器约束才进入 gold；没有擅自修订青禾原始数据。

审计失败与产品结果分开：产品已成功而采集失败时，保留原生 Prediction 和完整回答，artifacts.complete=false、保存 audit_error_type，任务保持 blocked。校验失败的原始 checkpoint/evidence 也先进入 evidence_index，不会因异常丢失。实际 query timeout、observe unknown、后续未执行和 cleanup 失败仍分别留存。

## 人工审批与许可

新增 `approval_v2.py`、`tools/dataset_approvals.py`，与现有 build/validate/run 和 check_release 数据签收门禁相连。

- 人阅读的 HTML 与导出的决策 JSON绑定同一 context：源故事、全部两改写、既有配对长度变体、seed、生成器/合同/评分器/任务核验与 judge prompt 的内容哈希。数据或相关规则变化会使审批过期，不能事后给旧审核补当前指纹。
- 导入校验完整名单、重复/未知字段、实际签收字段、带时区且非未来时间、开发暴露和两改写检查。测试故事已暴露时不能 accepted。人签 JSON 原始字节直接保存，许可单独签收；不会代替人署名或自动 accepted。
- 导入只写源目录之外、尚不存在的新数据副本，拒绝链接材料；原始 sources/review/test 不覆盖。许可绑定数据内容与审核 context。manifest 的 status/license 必须和重新派生的审批结论一致，一个 accepted 字符串无法放行。
- 全部故事必须有明确决策；pending 留待审，rejected 排除。全部拒收或最终 test 为空不能 accepted；语义审核完成但许可未签收时是 pending_license。

可直接交给人的待审包：

`/Users/huaiyi/Documents/oschina/deliverables/memobench-human-review-20261015-remote-audit/`

含 README.md、review.html、approval.json、license-approval.json。60 条仍全部 pending、无人签名，许可 pending。实际用模板导入新副本后的结果保存在 `pending-import-command.log`：60 pending、test=0、release_status=pending_review。审核页的内嵌 context、脚本语法和导入格式已核对；当前 CUA 明确拒绝 file://，没有绕过策略，视觉复核尚未完成。

青禾故事的明确禁用路径与两种改写等义性仍需人审；已用于 Pro 开发反例，不能作为未见最终留出。首次审批测试曾读取第一个候选 test 的结构，后来改为完全自造源故事；这次结构暴露单独登记在 `development-exposure-note.json`，没有在该故事上调用模型。原始分区和人工记录未擅改。

## 版本、部署与回滚

两次真实 query 使用的 bridge SHA-256：

`dc22dd2e533ed1ec64f4cdf5bc6e9acecdb7d9f565c35088ab9a61c1b99521a2`

最终部署 bridge SHA-256：

`1b22e1637d4c535f64d074347ebede46b4291172ce73eb938d01c5f430097d6d`

两版仅相差“审计采集失败时保留产品 Prediction、让任务闭锁”的异常分支。`bridge-audit-failure-semantics.patch`、两版源码和 `bridge-version-receipt.json` 记录精确差异；缺轨迹/不安全文件的离线回归证明 Prediction 仍 ok、任务 blocked。没有声称两次真实 query 跑在最终 hash，也没有再调用模型。

最终版已部署默认路径 `/home/mb/memobench-native/native_vm_product.py`，两端 hash 相等。部署后 py_compile 通过，默认 SSH transport 对两产品分别完成 reset/begin/checkpoint/close，0 query、0 API。完整 `deployment-receipt.json` 保留检查与回滚路径。

原版备份：

`/home/mb/memobench-native/native_vm_product.py.backup-6996e5353c68087d2988f5814ed59d0c6fa0337712dcd10fc4b8c10c17b9ad5f`

需要回滚时，先确认没有运行中的 case，在 VM 将该备份复制回默认脚本，再重算 SHA-256，应为 `6996e5353c68087d2988f5814ed59d0c6fa0337712dcd10fc4b8c10c17b9ad5f`，并运行 `python3 -m py_compile`。恢复匹配该旧协议的本地桥/transport 版本后才能继续；不要用当前新客户端强行忽略版本失配。本批没有执行回滚。

## 验证和仍须人完成的部分

`tests-final.log`：225 项通过；最后补充“失败校验仍保存原始证据”的回归后，最终结果以 `tests-final-226.log` 为准。测试命令为 `python3 -m unittest discover -s tests -v`，未修改任何既有测试。`artifacts-tests.log`、`approval-tests.log` 和 `existing-data-tests.log` 为对应阶段定向日志。源码最终哈希见 `final-source-hashes.json`，初始状态见 `initial-state.json`。

仍须人完成：逐故事语义/证据/改写/约束与开发暴露审核、独立数据许可、最终裁决及真实运行范围和预算签收。真实原数据保持 60 pending、正式 test=0。新通道不解除这些门禁；本批两次开发验收不生成正式排名。
