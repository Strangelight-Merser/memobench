# 2026-10-15 离线 native 接线与失败闭锁

本目录是离线合成回归证据，不是产品成绩、live 接入验收或人工签收。未访问 VM、未读取凭据、未调用模型、未发布/推送。SOURCE_INDEX.md、audit.json 云附件未取得；依据 REVIEW_FROM_THREAD.md 与当前完整仓库复现。

## 本批实现

- `run(..., native_transport_factory=...)` 在显式 offline 模式选择 kylin/openclaw，创建实际 NativeAdapter，走 reset/begin/observe/query/end/close 生命周期。native Prediction 原文进入 judge，不经过组件 adapter、Reader 或答案裁剪。run.json/summary 明示 fixture，publish_ranking=false。
- 本地受控工具 transport 可交给评测器当前 home 中的 FileSandbox；评测器在当前 query 前采集 baseline/audit checkpoint，按 run/namespace/episode/variant/session/operation 绑定，任务后按每个 expected_action 验真实文件字节哈希与真实工具日志。gold 不进入 transport。
- 缺少可信产物通道继续 blocked，不把 native Prediction.file_actions 当成真实工具执行。该本地工具 handle 不等于已实现 SSH 远端审计。
- observe unknown receipt 保留于 blocked_write/events，后续 query 不执行，合成结果明确 query_executed=false 与 not_executed_reason。Prediction 合同暂无 not_executed 状态，统计仍落 error，不能当查询已尝试错误。真实 query timeout 保留 timeout。
- cleanup_error、cleanup_receipts 与主失败分开；旧调用者在只发生 cleanup 失败时仍能通过 error.stage 看到 close。
- VM bridge operation evidence 新增 namespace/session/operation/method/bridge 哈希绑定和每次产品调用前后文件快照，query timeout 分类不丢失。
- probe 使用本地事件的预期 case/session/method/operation 核对导出，按 operation 索引而非任意扫描；必需检查集合、导出错误、缺画像终态均闭锁。q3 文件核验使用该 query 前后快照。跨 case 不泄露代号与正确回答不知道分别记录。

## 原始证据结构

`initial-state.json` 保存工作前 Git 状态、HEAD、关键源码哈希。`positive.json`、`forbidden-old.json`、`unknown-observe.json`、`query-timeout.json` 是合成 fixture 实际执行导出，保存 summary、完整 case（Prediction、score、events、cleanup、失败阶段、operation_evidence）及公开 transport_calls。usage 不可得保持 null/unknown，不填零费用。

命令和环境见 environment.json。完整首次测试日志保留于 tests-initial.log（发现后已修复的泄露传播与 cleanup 回归）；tests-final.log 是当前最终全套结果。native-all-tests.log、runner-tests.log 为对应阶段定向日志，测试数量以各日志为准。

## 范围与仍阻塞项

1. SSHVMTransport 尚无可认证的远端原生工具审计/产物读取协议；本批未伪造其日志。在线 native_factory 已有 SSH 分支，但仅当显式 live/online、明确用途、真实数据审批 accepted、数据内容哈希、配置字节哈希、当前 bridge 哈希、acceptance 文件哈希与必需接入检查全部匹配时才可构造 transport。acceptance 还必须关联按内容哈希冻结的原始 namespace exports，逐一验证 reset/mount/sentinel/binding/closed，核原始回答与 Prediction 一致，复用 inspect_export 重新计算检查；不能只改 summary bool。当前真实证据不具备这些条件，仍阻断。正式 run 含文件任务时，在构造任何 transport 前直接阻断远端审计缺口。SSH 请求携带 bridge 哈希，远端在读取 provider 前核对自身版本。不能宣称第一批所有工程目标全部完成。
2. Qinghe 原始 story 的禁止旧位置约束仍需人审编译到机器 gold。未改 sources、候选集、review 或正式发布数据；新增 synthetic Gold 明确带 old_paths，证明该约束生效时“正确新文件+禁止旧路径”必失败。现有未标注候选题并未因此自动修正。
3. 新预检要求 acceptance 绑定 dataset_sha256（按 runner hash_inventory 序列化），由后续冻结审核提供；现有真实 probe 没有此字段，不自动补造。probe 新格式尚未真实 VM 验证；历史证据没有新 binding 时应失败，不能重新标记历史 probe 为当前通过。
4. 数据语义/开发暴露、数据许可、最终人裁、live 授权与预算均未签收。线上不支持 resume/restart；真实运行仍关闭；本批未扩大范围到审批发布状态机。
