# 真实 CLI 案例适用性复核

本报告仅复核 story `e6a7a9059f826b02f8edd920` 与 variant `d012611aa89b90909fcea7b9` 的精确组合（episode `5668053304ca40ac9ef62563`），不依据可跨 story 重复的 variant 单独选样。读取当前 `data/v0.2-ai-reviewed` 的 test episode、OpenClaw 归档和现有验收源码；未修改数据、评分、桥或远端，也未触发模型。

**判定：本次负结果同时包含协议前提冲突、原生跨会话信息使用未成功和审计集成缺陷，不能归结为单一能力失败，也不能宣称任务完成或产品整体能力差。**

## 已核实证据

- 原始观察共 80 条。观察 0 为“机器读取的标记文件 markers/ready.txt 内容只能是 READY，不能有换行、引号或解释。”；观察 40 开启第二会话时说“重新开会话后仍按同一约定制作标记。”；最终 query 为“请创建约定的机器读取标记文件。”
- Gold 要求 `create markers/ready.txt`，内容 SHA-256 为 `c2e3ac47f4a325469c1a2d5f117e463ec943c721986d5d9f09ac4540b7d80526`（五字节 `READY`）。`memobench/native_artifacts_v2.py` 的 `verify_remote_task` 要求文件在 query baseline 中不存在、在 query 后发生变化，且有对应原生 write/write_file 事件；否则产生 `action_trace_mismatch`。
- OpenClaw 归档 `cli-prepared/raw-openclaw/8295f8e29460435fb388cd9b271c8ecd.json` 中，观察 0 evidence `87553e119928ad50e4b69d099ed68ba569fdec5fdc82b28b65cb5e7d8cf970b7.json` 已声称写入并读回五字节 READY，且 `files_before` 无该文件、`files_after` 有该文件。这里保留“答复声称”和文件库存证据的区别；未留存该观察的完整工具 transcript，不能追加声称独立验过其工具调用链。
- Query evidence `362f894da43c2900f9ae2d3cbb1b1388d39a407d0912b756cc7e6e2e9d31a4af.json` 的 bridge baseline 与 after 均包含 `markers/ready.txt`，解码均为精确 `READY`。因此 query 前文件已存在是直接字节证据。
- 观察 40 与最终原生回答均表示不知道先前约定；最终回答没有声称新建成功。Query `ok=true`，工具摘要为 3 次 read、1 次失败；stderr 明示读取 workspace 目录失败。Artifact 为 `complete=false`、`audit=null`、`audit_error_type=ValueError`，未保存原始 native records 或具体原因。

## 三类问题的边界

**任务定义与 CLI 协议不匹配。** 在真实代理 CLI 中，observe 是带工具能力的真实 user turn，代理会立即回答并可写文件。观察 0 没有明确禁止执行，观察 40 也具有“制作标记”的执行含义；当前桥没有将它们隔离为仅摄入信息的阶段。观察期提前创建文件因此是合理可发生的行为，却破坏 query-only create 验收的前置条件。即便最终 query 完美回忆并重写相同内容，文件已在 baseline 中，仍不能满足现有 create 验收。不能把这项必然冲突当作纯记忆能力的鉴别结果，也不能删除文件或改 gold 来追认通过。

**本配置中的原生信息使用未成功。** 后续原生答复确实未恢复约定，尽管 query 前正确文件仍在 workspace。这支持“该配置、该路径下的跨会话检索/回忆和文件发现未成功”的局部观察。它不能单独区分未存储、检索不足、提示/会话配置、文件发现方式或模型决策等原因；答复中关于 embedding 配置的描述是产品自述，不能代替配置和运行证据。更不能由此推断其他模型、配置或产品总体能力。

**审计集成问题。** 已离线合成复现正常文本 read 被强制 JSON 解码、失败 read 直接终止审计、合法 workspace 根目录被当越界等缺陷；真实 query 有目录 read 失败，但原始 transcript 随 HOME 清理而缺失，无法确定本次首先触发哪个 raise。当前不完整审计应继续保持阻断，不能用 after 文件正确或产品 `ok=true` 替代原生执行证据。证据留存与 read 审计完整性修复不会消除 baseline 已存在的独立问题，也不应改变旧分数。

## 结果可用范围

本例可作为真实 CLI 接入的探索性负结果：证明观察会产生提前副作用、最终原生回答未恢复约定，以及审计证据链不完整。它不适合充当已隔离协议干扰的 query 创建能力或纯跨会话记忆结论，也不构成两产品正式排名。应保留本次原始结果；任何后续正式测试须先明确观察是否允许执行及 query 的创建前提，并采用事先确定且独立验收的协议，另起运行、另记结果，不回写本次历史。Kylin 运行状态和结果不在本报告的判定范围内。

## 主代理补充：Kylin 完整运行

Kylin 完成相同的 80 条观察和 1 次最终查询，81 次原生画像处理均为 `profile_completed=true`。最终回答正确指出 `markers/ready.txt` 和精确五字节 `READY`；原生审计记录了当前 query 中的 `write_file`。但 query 前后字节相同且文件早已存在，独立重算仍为 `failed/action_trace_mismatch`。因此本例可证实该运行找回并使用了约定，但不满足原有“新建”动作验收，不能将其改记为任务通过。原自动语义评分 `pending_review` 保留；本报告是明确标识的 AI 证据复核，不是人工签收或已校准裁判分数。主复核结果见 `PRIMARY_CLI_REVIEW.json`。
