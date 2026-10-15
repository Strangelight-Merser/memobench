当前内部评测采用 [独立 AI 审核与主复核](ai-review-20261015/ENGINEERING.md)，默认 recipe 已指向新审核目录；原始数据和以下历史卡接口记录保留。

# 真实智能体接入与隔离

最新：[观察阶段协议修复与完整真实验收](phase-protocol-20261015/README.md)。两产品当前完整 probe 已通过；各 80 条观察、两会话、最终新建精确文件和清理均通过严格验收，主代理与独立 AI 已复算原始证据。Kylin 的 81 次原生画像处理均完成，原生记忆未关闭。各版失败记录仍保留，不用于排名。历史画像修复见 [KYLIN_PROFILE_FIX.md](KYLIN_PROFILE_FIX.md)。

新增 openKylin VM 产品桥和小规模在线验收，当前结果见 [NATIVE_VM.md](NATIVE_VM.md)。以下为卡4阶段的原始通用适配层记录，保留历史证据；其中本机 PATH 和 VM 状态不代表最新接入状态。

## 卡4历史记录

本次交付通用 subprocess 适配器、JSON-over-HTTP 客户端、native 生命周期控制与离线测试。
**两款真实智能体接入仍为 blocked，不能进入正式 native 排名。** 没有为未知安装版本编造参数或响应格式；产品专用桥接绑定仍需现场源码与帮助探测后实现、验收。本目录中的假进程测试不是 Kylin Agent Runtime / OpenClaw 的实测。

## 当前实测记录

2026-10-14，本机 Darwin arm64 / Python 3.13.12。执行记录见
[agent-probe-macos.json](agent-probe-macos.json)。PATH 未发现 `kylin-agent-runtime`、`openclaw`，
所选服务的 `DEEPSEEK_API_KEY` 未设置；没有执行模型请求，没有读取实际 agent HOME。
版本、帮助、模型配置、会话语义、长期记忆、真实状态目录、异步 flush、真实清理和权限隔离均为 `NOT_VERIFIED`，人工签收为 `pending_review`。
这只是 PATH 检查，不声称全盘没有安装软件。openKylin VM 尚不可用，卡5的权限隔离模块也不在本 worktree 中。

实际执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tools/probe_agents.py \
  --config configs/adapters/native.json \
  --out docs/integrations/agent-probe-macos.json --live
```

退出码 **2**，状态 **blocked**。任务卡原命令输出到 `artifacts/agent-probe.json`；为遵守卡4只能写独占路径的限制，本次仅替换 `--out`。
`--live` 不自动运行任务、启动网关、安装软件或调用付费 API；这里只执行发现的程序的 `--version` / `--help` / OpenClaw `agent --help`。
不带 `--live` 时不启动任何外部程序。即使帮助返回 0，工具也不会把生命周期标成 PASS。
配置中的 DeepSeek 仅为待配置服务选择；没有锁定、调用或宣称已对齐任何模型。

## 冻结接口与集成入口

```python
from memobench.adapters_v2 import NativeAdapter, SubprocessTransport, HTTPTransport
from memobench.schema_v2 import AdapterCapabilities
from memobench.protocol_v2 import require_ready

# argv 必须指向已经审核的协议桥，不是普通 agent CLI；默认不会执行。
transport = SubprocessTransport(
    ["/absolute/path/to/reviewed-bridge"], live=True,
    credential_env=("DEEPSEEK_API_KEY",), timeout=60,
)
capabilities = AdapterCapabilities(native_answer="supported", restart="unsupported")
agent = NativeAdapter(transport, capabilities)
# 按时序调用 reset_case / begin_session / observe / end_session / query。
# 每次写入先 require_ready；query 返回冻结的 Prediction，绝不走公共 Reader。
# finally 中 close；cleanup_not_verified 必须记录为未完成清理。
```

上例是接口用法，不是可运行的产品配置，`native_answer=supported` 必须有桥接和实际响应证据。
HTTP 方式使用 `HTTPTransport(endpoint, live=True, key_env="AGENT_API_KEY")` 替换 transport。
HTTPS 或 loopback HTTP 才可用；拒绝 URL 内凭据、query、fragment，禁用环境代理与重定向，避免凭据转发。
所有 HTTP 测试使用模拟响应，无监听端口、无网络访问。没有把该 JSON 协议叫作 MCP。

只有卡1的 `Observation`、`Probe`、`Prediction`、`AdapterCapabilities`、`WriteReceipt` 参与数据接口；没有另起答案字段。
观察和问题严格通过 `adapter_payload()`，不接受 Gold、Episode、普通字典或子类。
输出使用 `validate_prediction()` 验证归属和可观察证据。没有可观察成本和证据就保留 null。
不导入生成器、评分器或公共 Reader。所有角色均原样传输。

## 桥接传输约定

这是传输封套，不是第二套数据 schema。单次 subprocess 调用 stdin 是一个 UTF-8 JSON 对象：

```json
{"method":"observe","operation_id":"opaque-operation-id","payload":{"episode_id":"e","variant_id":"v","session_id":"s","observation_id":"o","role":"user","text":"虚构测试文本","observed_at":"2026-10-14T10:00:00Z","sandbox_references":[]}}
```

stdout 必须只有一个 JSON 对象：query 返回完整冻结 `Prediction`，其余返回冻结 `WriteReceipt`。
不解析自然语言声称的“完成”，不从日志中猜答案；非法 JSON、重复键、非法数值、非零退出或归属错误不会变成成功。
HTTP POST 使用同一封套，额外的 `namespace` 是每个 episode/variant 的随机测试空间名；服务端必须做权限校验。

| method | payload | 桥的职责 |
|---|---|---|
| reset_case | episode_id、variant_id | 为全新测试空间建立真实产品状态；不得重用用户配置 |
| begin_session | episode_id、variant_id、session_id | 创建新会话，保留当前 case 的长期记忆 |
| observe | Observation.to_public() | 投递一次并等待可读取；保持 role，不能擅自改成 user |
| end_session | episode_id、variant_id、session_id | 等待实际异步写入；未确认就 unknown/failed |
| query | Probe.to_public() | 投递一次，返回产品自身回答 |
| close | episode_id、variant_id | 停止该测试空间的任务/后台写入并清理本地或远端测试状态 |

桥负责产品接口映射及可观察的就绪证据。适配器不会把进程退出 0、HTTP 200、任务已排队或返回了一段答案自动当作记忆 ready。
`durable` 必须由产品绑定的持久化证据支持；桥没有证据就不能返回 durable。
本次未引入任意 shell 工具执行，也未启动任何智能体自主工具循环。

## 隔离、重试与清理

- 每个 case 创建随机临时 HOME，设置独立 XDG 和 TMPDIR；同 case 多会话共用它，variant 和 episode 切换后换新目录。ID 不参与路径拼接。
- subprocess 使用固定 argv、stdin JSON、`shell=False`；不继承真实 HOME、代理、PYTHONPATH、供应商凭据。显式 `credential_env` 仅允许名称以 `_API_KEY` / `_TOKEN` 结尾的变量，不把值写入配置、日志或 argv。
- **HOME / cwd 隔离不是权限沙箱。** 真实测试必须在专用 VM/测试账户配合卡5权限控制；gold 在评测器侧，产品进程不能有读取权限。HTTP 服务端也必须隔离 namespace、存储和工具权限。当前没有这项实际证据。
- 相同操作 ID 和相同 payload 返回原结果，含 query；不同 payload 报合同错误。不自动重试 HTTP 429/5xx、网络错误、超时或非零退出，避免写入被重复执行。
- 写入 unknown/failed、非法响应、query 失败会封锁后续新操作。桥应在单次调用内等待 flush；等待不成功即停止该 case，不用轮询写操作来重试。
- 运行目录留有 `NO_RESUME` 与只含哈希的操作日志。原目录不能重新打开；进程重启后的恢复明确 **unsupported**。卡7不得将中断 native 运行换个目录冒充续跑；重新试验须记为独立运行。
- `close()` 对每个空间发送一次清理请求，记录 `cleanup_receipts`；未确认清理抛出 `cleanup_not_verified`，不自动重发。随后仅清理本实例生成的 case 目录，保留运行标记/哈希日志，不读取或删除真实 agent 配置。符号链接目标不跟随删除。
- `close()` 不宣称物理擦除，也不能证明未知远端任务已停止。清理失败需人工检查专用服务的任务与状态。
- 生命周期调用为串行；本地去重不承诺多个评测器实例之间的共享去重。运行目录由单个评测器独占。

## 真实接入的人工与工程剩余工作

1. 在专用 openKylin VM/测试账户安装两款软件，固定版本或源码 commit、安装依赖及许可证；不要复制完整私人 HOME。运行上述 probe 保存真实版本/帮助输出。探测无法进行时在两小时内停止并记录缺口。
2. 按该安装版本源码确认产品入口、session ID、新会话、状态目录、模型配置、flush 完成信号及清理接口，完成对应产品桥。通用适配器不能直接拿普通 CLI 当 JSON 桥。不能在帮助证据缺失时猜参数。
3. OpenClaw 使用专用测试网关与状态空间；当前不默认加 `--local`。确认返回答案后的后台写入如何等待。Kylin 的 `-z` 不证明跨会话记忆，必须另验。
4. 用虚构 canary 验证 S1 写入、结束等待、S2 新会话回忆；保存真实 session ID、response、等待证据。另一个 variant/episode 不得读到 canary；重启语义和清理另行验证。保存公开输入与响应，不保存密钥或私人配置。
5. 与卡5验证权限：产品进程读取 gold 文件必须失败，文件工具只能访问测试区。适配器临时 HOME 不能替代这个检查。
6. 模型尽量统一供应商、endpoint、请求/返回模型、有效参数、版本/摘要；使用冻结 `ModelRecord`/`RunManifest` 记录。不能对齐则标“整体系统比较”，不能把差异归因于记忆。
7. 人工签收两套实际软件的证据后，再由卡7纳入正式 native 运行。当前测试通过仅证明适配层行为。

external mem0 是 P1：本机没有已提供的专用服务，未创建服务、数据库或 v2 mem0 适配器，状态 blocked；不会复用 v1 未锁版本入口冒充验收。

## 一手文档核对（不等于运行证据）

2026-10-14 已读取 [Kylin 官方源码仓库说明](https://gitee.com/openkylin/agent-runtime)：
记录了 `kylin-agent-runtime --help`、setup 和 `-z` 单次任务入口。没有从这些说明推断出本机已安装或会话持久性通过。

已读取 [OpenClaw 官方 agent CLI 文档](https://docs.openclaw.ai/cli/agent)：网关回答返回后可能仍有可选记忆 flush；单次 `--local` 跳过可选的回合后工作，传输丢失存在执行结果不确定性。
因此本实现没有默认 `--local`，也没有对写操作进行自动重发。网页随版本变化，最终仍以安装版本源码和帮助为准。

## 离线验收结果

本次实际执行，均退出 0：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_adapters_v2.py' -v
# 25 tests, OK
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover tests
# 71 tests, OK
```

原始日志：[卡4测试](adapters-tests.txt)、[全量测试](all-tests.txt)。
覆盖同 case 跨会话保留、跨 variant/episode 隔离、写入与 query 去重、写后超时、
未知 flush 阻断、清理失败、重启拒绝、所有角色、gold 剥离、shell 文本数据化、
证据与输出归属、HTTP 错误不重试、重定向拒绝以及无安装/无凭据探测。
既有源码和测试未修改；未 git commit；核心新增代码仅使用标准库。

2026-10-15：已接通 [远端真实文件审计与人工审批闭环](native-audit-20261015/ENGINEERING.md)，包含两产品各一次真实开发文件任务、默认 bridge 部署回执、无 API 生命周期检查及未签收审核包入口。数据与许可仍待人签收。

当前正式入口使用 [native 准备 recipe 与 dry plan](native-preparation-20261015/ENGINEERING.md)：审批数据和产品接入分别验证，自动生成可审阅配置，缺条件不创建 transport。
