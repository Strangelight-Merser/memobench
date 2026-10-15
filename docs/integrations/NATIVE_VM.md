# openKylin 中的真实智能体接入

**最新状态：Kylin 的画像超时及后续验收阻塞已修复，九项完整接入验收通过。** 当前版本是官方固定基线加三个本地补丁，原生记忆与画像保持启用；运行入口、补丁、失败记录与最终证据见 [Kylin 修复与验收](KYLIN_PROFILE_FIX.md)。OpenClaw 已通过的结果仍保留。

## 首次接入历史记录

以下保留首次接入时的版本、失败和判断；其中 Kylin 阻塞状态已被上述新验收更新。

2026-10-14（America/Chicago；证据时间为 UTC）。已打通 SSH/SFTP，安装并调用两款真实智能体。OpenClaw 完成两次严格的五项小样本验收（含重启后的最终版本）；Kylin 已真实执行检索和文件动作，但完整验收未通过。此记录不是正式数据集成绩或产品排名。

## 运行入口

在仓库根目录运行以下命令；`--out` 必须不存在，`--live` 会实际调用配置的模型服务并产生用量。

```sh
python3 tools/probe_native_vm.py --ssh-config ../.local-vm/ssh_config --product openclaw --out /tmp/memobench-openclaw-new --live
python3 tools/probe_native_vm.py --ssh-config ../.local-vm/ssh_config --product kylin --out /tmp/memobench-kylin-new --live
```

操作通道与恢复方法见 [VM_ACCESS.md](../openkylin/VM_ACCESS.md)。模型凭据来自本机 `~/.memobench.env`，仅部署到客户机仓库外的 `~/memobench-native/provider.json`（0600）。源码与证据不含凭据。客户机桥接文件为 `~/memobench-native/native_vm_product.py`；修改仓库对应脚本后须使用 SCP 部署。

`SSHVMTransport` 接入既有 `NativeAdapter` 生命周期。每个 case 创建独立 HOME；同 case 新会话使用新的产品 session ID，保留该 case 的原生记忆。使用 bubblewrap 隔离挂载与进程，只允许写入本 case，系统和产品安装目录只读，不挂载评测数据、答案或其他 case。每次 reset 实测隔离哨兵在外存在、在内不可见。网络保持开放供模型 API 使用，这不是网络隔离证明。

## 固定版本与运行方式

- openKylin 2.0 SP2、aarch64、Linux 6.6.0-25-generic，Python 3.12.2，bubblewrap 0.9.0。
- Kylin 来源为官方 agent-runtime，commit `246652c0fdb687953ef8ef25973081bf1298f0c6`，真实 `chat -Q` CLI，`memory,file` 工具组。未修改上游源码。
- OpenClaw 2026.10.3、Node 24.22.0，使用 `agent --local` 原生嵌入式路径，允许 read/write/edit/memory_search/memory_get。
- 两者均使用 DeepSeek `deepseek-flash`。OpenClaw 不设置 OPENAI_API_KEY，避免把 DeepSeek 凭据错误地用于 OpenAI embedding。
- 最终 Kylin 配置：12 步、单次进程 300 秒；用户画像仍启用，关闭一 token 预检，画像提取尝试一次。该选项调整须随结果披露，不能称默认配置成绩。

Kylin quiet stdout 混有调试输出，因此答案取自其原生 SQLite 当前会话、本次调用后写入的最终 assistant 消息。最终桥接还校验本次新增原生日志的 `completion_review:completed`；该版本 quiet CLI 不写 task_runs，且预算耗尽也可能退出 0，不能仅凭退出码认定成功。缺少完成证据时明确失败，不猜测回答或重放操作。超时保留已捕获输出和新增日志，不把部分写入算完成。

## 实测证据

原始试跑均保存在 [native-vm-20261014](native-vm-20261014/)，没有覆盖失败结果。

| 试跑 | 结果与解释 |
| --- | --- |
| OpenClaw 001 | 五项检查通过，但发现错误的 OpenAI 凭据别名造成 embedding 401。不能作为最终配置验收。 |
| OpenClaw 002 | 同会话准确回答、独立新会话准确回答、实际文件内容哈希、不同 case 不泄露代号、清理均通过。修正凭据；未配置语义 embedding，不能据此声称向量检索已验证。 |
| OpenClaw 003 | 虚拟机重启后以最终桥接复跑，五项检查全部通过；桥接哈希与 environment.json、binding-hashes.json 一致。 |
| Kylin 001 | 早期宽松包含检查显示同会话/跨会话包含代号，文件哈希正确；文件任务退出时画像提取超时，整轮不通过。早期 stdout 解析与包含标准不同，不与后续严格结果混算。 |
| Kylin 002 | 严格答案比较失败；同会话有额外解释，跨会话在 5 步预算下耗尽。之后原生文件任务找到代号并写入正确内容；case 隔离与清理通过。整轮不通过。 |
| Kylin 003 | 12 步下首轮模型完成回答，但退出阶段画像提取超过 300 秒。入口收到 unknown，停止后清理成功；后续检查未执行。出现过 DeepSeek 503，原生 SDK 自行重试。整轮不通过。 |

最终桥接状态校验与诊断保存是在 001/002 及 Kylin 003 之后补强的，已用于 OpenClaw 003，不追溯改写原始结论。完整测试 `python3 -m unittest discover -s tests`：192 项通过（38.094 秒）。对应回归测试覆盖：不接受调试 stdout、旧消息和旧完成日志；退出失败不能采用历史回答；OpenClaw 凭据隔离；超时脱敏与保留诊断；显式 live 门禁。

## 尚未完成的验收

Kylin 当前配置的可靠退出仍被原生用户画像提取阻塞；将预算从 5 增至 12、画像重试降为一次、进程等待增至 300 秒仍未解决。不得关闭原生记忆后冒充等价通过，也不继续无限放宽预算。源码定位为 `agent/user_profile/extractors.py` 的画像请求：复用主模型 client，但未给该请求单独设置输出长度与超时；当前证据不能进一步区分服务拥塞、超长生成或连接等待。下一步应针对该请求做独立的超时/输出长度修复验证，并将改动后的产品版本单独标识。

OpenClaw Gateway 可选 post-turn flush 未运行；embedding、检索证据、写入 token 用量、进程重启恢复能力均未验收，相关能力标为 unsupported。观察消息仅支持 user 角色，其余明确失败。模型网络用量未归一化，不能排名。

正式 `cli_v2 run --config configs/experiments/native.json` 仍保留隔离门禁；本次是独立、可重跑的真实产品接入验收入口，不是把正式 runner 强行解锁。60 个候选故事及 120 个问题仍 pending_review，正式测试集为 0；人工审核、正式 native 批跑、deb 安装卸载验收未完成。
