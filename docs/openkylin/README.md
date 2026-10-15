当前虚拟机操作通道见 [VM_ACCESS.md](VM_ACCESS.md)，真实智能体接入见 [NATIVE_VM.md](../integrations/NATIVE_VM.md)。[当前版本完整接入与真实验收](../integrations/phase-protocol-20261015/README.md) 提供最新原始证据。下文保留原环境与验收说明。

# 卡5：文件任务与 openKylin 验收

核心只依赖标准库，不调用网络、不需要 root、不安装软件。
本目录记录卡5的实现与实际离线诊断；文件任务通过不代表 GUI、系统设置、存储物理擦除或真实智能体已适配。

## 接口与边界

`memobench.sandbox_v2.FileSandbox(root)` 要求评测器给出**不存在的新目录**，父目录必须由评测器控制。每个 episode/variant 独立创建实例，同一 episode 的会话共用实例。`close()` 仅关闭句柄，不删除证据。调用者负责临时目录生命周期。

`execute(operation, operation_id, **arguments)` 白名单：

| 操作 | 参数 | value |
|---|---|---|
| create | path, text | null |
| read | path | UTF-8文本 |
| list | 无 | 全部文件相对路径 |
| render | path, template, values | null |
| audit | 无 | 动作记录副本 |

结果的 `receipt` 是协议 `WriteReceipt.to_dict()`，ready 表示操作完成，不宣称跨重启持久去重。失败返回 failed 和固定错误码。使用 `WriteReceipt.from_dict` / `require_ready` 检查，不能忽略失败。操作 ID 在实例内去重，同 ID 不同参数拒绝；重启后不允许自动重试写入。

模板是标准库 `string.Template` 的 `$name` / `${name}`，values 只接收字符串映射。缺变量拒绝，不执行表达式、命令或 Python。create/render 只新建文件，拒绝覆盖；更新后的模板使用新文件名。目录按路径自动创建。

文件路径使用冻结的 `SandboxReference` 语法并进一步拒绝空段、`.`。逐层 dir_fd 与 O_NOFOLLOW 打开，拒绝所有符号链接、硬链接、特殊文件；写入 O_EXCL，不截断已有文件。文件哈希为 UTF-8 原始字节的 SHA256，不改大小写或换行。

**这只是受控文件工具，不是操作系统权限沙箱。** root 的父目录必须可信，测试期间不得有另一个进程重命名其目录树。一个可自由执行 shell 的同账户 agent 可以绕过工具；仅修改 cwd、chmod 700 或换临时 HOME 均不能证明它看不到 gold。`native_isolation_status()` 因缺少权限后端明确返回 blocked，当前代码不启动 native agent。

正式接入须在专用 VM/测试账户中运行 agent，gold 留在外部评测器：只投递单条 `public_task_input(Observation/Probe)`，公开模板/输入文件通过工具代理传输；不共享仓库、私有数据挂载或评测器内存。同一 VM 内不同账户还需验证对私有文件的读取确实被拒绝。外部隔离由卡4/卡7接入并附真实证据，不能通过传一个布尔值解锁本模块。审计存放在评测器进程，不能把它放进 agent 可修改目录。

## 私有文件评分语义

不增添另一套 Episode/Gold/Prediction 字段；复用卡1类型。卡5在合同允许的 `Gold.expected_actions` 自由字典中定义：

```json
{"operation":"render", "path":"current/note.txt", "sha256":"实际内容SHA256",
 "template_sha256":"当前模板SHA256", "old_paths":["old/note.txt"],
 "old_template_sha256":"旧模板SHA256"}
```

operation/path/sha256 必填；render 还须 template_sha256；old_paths 和 old_template_sha256 可选。哈希必须是64位小写十六进制，上例文字仅解释格式。`validate_actions(gold)` 拒绝未知动作和字段。它们仅供评测器使用，不可作为工具请求发送给 agent。

在任务开始或删除请求到达时，评测器保存 `baseline = box.snapshot()` 与 `audit_since = len(box.audit)`；执行结束后调用：

```python
result = verify_task(box, gold, prediction, baseline=baseline, audit_since=audit_since)
```

调用者须验证 prediction 的 episode/variant/session 归属（用卡1 `validate_prediction`），本函数验证 probe_id 与 Gold 对应。调用者须保存并逐条核查删除请求之后的每个 Prediction，不可只提交最后一次无泄露回答。快照、检查点与结果均由评测器保存，不能让 agent 提供。

验证器检查实际文件、预期内容哈希、实际模板哈希和成功动作日志。错误码包括 `old_path_reuse`（旧路径复用）、`stale_template`（模板过期）、`missing_file`（声称成功但无文件）、`content_mismatch`、`action_log_mismatch`、`unsafe_artifact`。日志不能代替产物，原有同名文件不能当作新任务成功。直接写入绕过工具或写后修改/删除会失败。外部 agent 若直接操作文件，卡4须接入受信任工具代理或另外提供可信审计；当前不能直接判通过。

`Gold.forget_policies` 每项使用：

```json
{"canary":"MEMOBENCH_FICTIONAL_CANARY_C5", "retained_text":"中文"}
```

canary 明确为虚构字符串，禁止放真实秘密。检查删除请求之后的回答、工具读取输出、新建/修改文件与文件路径；工具写出的内容即便随后文件被删除，内存证据仍可定位泄露。要求最终回答或新产物保留 retained_text。删除前旧文件不直接算新披露，读取旧文件后输出 canary 则违规。此检查是明文精确匹配，不证明语义改写/编码泄露已覆盖，也不证明磁盘擦除。进程内工具内容证据应由评测器保管；关闭/重启后恢复验收需完整证据，不能只恢复哈希日志。

## 12故事组装与待验收项

`assemble_cases(episodes, story_ids, review_status)` 接收现有合同 Episode，选取12个不同故事及其已有 variant，不改写事实/问题、不补足样本。要求 test、跨会话、具有文件 expected_actions。review_status 是评测器人工签收清单映射，只有 approved 才返回 ready；缺故事返回 blocked，未签收返回 pending_review。ready 只表示可交给统一 runner，不代表执行通过。

本分支没有 `data/v0.2` 或卡2实现，因此正式故事选择为0/12，记录见 `fixtures/openkylin/status.json`。单元测试中的12个合同对象只验证选择接口，不是12个已审阅故事。等待卡2提供数据后，人工选择并核对：早期目录/模板、后续目录与模板更改、同事干扰、重开会话、遗忘且保留无关偏好；每一项必须能追溯既有观察及 Gold.evidence，不可用本模块从答案反向编造观察。

人工尚须：

1. 安装并启动 openKylin VM，在其中重新执行环境探测；保存发行版、架构和实际工具版本。模型服务机单独记录，远程模型不能由运行机信息推断。
2. 按上述权限边界布置外部评测器与 agent；尝试读取私有 gold 应失败，保留命令、返回码及权限/挂载证据。
3. 卡2提供12个既有测试故事并完成上述场景审核，人工清单签名；卡4提供两款真实软件版本、会话和异步就绪/持久化证据。
4. 卡7按冻结协议运行：同 episode 只 reset 一次，end_session 后 begin_session 保留记忆；variant/episode 间隔离。保存真实 Prediction、文件、模板哈希和工具审计，验证旧路径/模板/无产物负例。
5. DeepSeek 凭据当前不可用，真实 API 验证 blocked；密钥只在实际测试环境注入，不写入报告或仓库。

## 离线命令

```bash
python3 -m unittest discover -s tests -p 'test_sandbox_v2.py' -v
python3 tools/probe_openkylin.py --out docs/openkylin/local-env.json
python3 -m unittest discover tests
```

任务卡示例 `--out artifacts/openkylin-env.json` 的目标不在本卡独占路径，因此本次仅将 out 改到本目录；探测逻辑不变。集成者可使用任务卡原路径。`--tool /已确认的可执行文件` 可重复指定，只调用其 --version；卡5不猜测两款 agent 的可执行名或会话参数。

环境探测退出码0仅表示成功写出诊断。非 openKylin 输出 NOT_VERIFIED；即便 Linux 的 ID=openkylin，也只输出 detected，acceptance 仍为 NOT_VERIFIED，不能打印 openKylin PASS。未指定工具时版本状态为 NOT_VERIFIED；模型服务机和权限隔离未探测，保持 NOT_VERIFIED。
