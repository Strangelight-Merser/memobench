# MemoBench v0.2 协议合同

卡1范围：数据结构、公开/私有边界、运行清单、适配器接口及离线假实现。
仅依赖 Python 标准库；不实现 runner、评分、数据生成或真实智能体接入。
v1 文件及诊断语义保持原样，不能与 v2 分数混榜。

## 序列化和验证

从 `memobench.schema_v2` 导入数据类型。所有下表 dataclass 均提供
`validate()`、`to_dict()`、`from_dict(data)`、`to_json()`、`from_json(text)`。
构造和序列化都会验证；`from_dict` 还会还原嵌套 dataclass。
缺少必填字段、额外字段、错误类型、重复 JSON 键、NaN/Infinity 均拒绝。
错误统一为 `ContractError(ValueError)`，消息不回显字段值。

JSON 使用字符串枚举；时间必须是带时区的 ISO 8601 完整时间，例如
`2026-10-14T10:00:00Z`，支持小数秒与 `+08:00`。
observed_at 为故事内事件时间，answered_at 为实际回答时间；两者不作先后比较。
所有 ID 为非空字符串，发布数据须使用不编码答案或类别的 opaque ID。
同一 episode/variant 内 session、observation、probe ID 各自唯一；
不同 variant 可以复用局部 ID。操作 ID 则在一个适配器实例中全局唯一。

`validate_dataset(episodes)` 检查 `(episode_id, variant_id)` 重复及同一
`story_id` 跨 dev/test；不把同故事改写当独立故事。
`Episode.validate()` 检查输入的 episode/variant/session 引用、gold 对 probe
的一对一覆盖、证据 observation 引用和字符范围、观察时间顺序、证据不能晚于问题。
`validate_prediction(prediction, probe, capabilities, observations)` 检查输出归属和检索证据引用；不支持观测证据时必须填 null。
证据引用合法不等于证据支持答案，支持度由评分器判断。

## 数据结构清单

除标有默认值的字段外，其余字段必须显式提供；可空字段也需要提供，除非标有默认值。
`Any` 只接受有限数值、字符串、布尔、null、列表和字符串键字典。

| 类型 | 字段 |
|---|---|
| `SandboxReference` | `reference_id: str, path: str` |
| `Observation` | `episode_id, variant_id, session_id, observation_id: str; role: system/user/assistant/tool; text: str; observed_at: str; sandbox_references: list[SandboxReference] = []` |
| `Probe` | `episode_id, variant_id, session_id, probe_id: str; query, observed_at: str; sandbox_references: list[SandboxReference] = []` |
| `Slot` | `name: str; value_type: string/number/boolean/version/path; state: answer/unknown/forgotten/conflict; value: Any; aliases: list[Any] = []` |
| `EvidenceLocation` | `observation_id: str; start: int或null = null; end: int或null = null` |
| `Gold` | `probe_id: str; slots: list[Slot]; evidence: list[EvidenceLocation]; canonical_state_ledger: list[dict]; expected_actions: list[dict]; forget_policies: list[dict]; technical_categories: list[str]; official_capabilities: list[str]` |
| `Episode` | `episode_id, variant_id, story_id: str; split: dev/test; session_ids: list[str]; observations: list[Observation]; probes: list[Probe]; golds: list[Gold]` |
| `Prediction` | `episode_id, variant_id, session_id, probe_id: str; status: ok/unsupported/error/timeout; text: str或null; answered_at: str; state: answer/unknown/forgotten/conflict或null = null; slots: list[Slot]或null = null; retrieved_evidence: list[str]或null = null; usage: dict或null = null` |
| `AdapterCapabilities` | `native_answer, retrieved_evidence, write_usage, flush, restart, storage_inspection`，各为 `supported/unsupported/unknown`，默认 `unknown` |
| `ModelRecord` | `provider, endpoint_id, requested_model: str; returned_model: str或null; parameters: dict; version, digest: str或null; recorded_at: str` |
| `RunManifest` | `run_id: str; mode: component/native_agent; execution: offline/online/replay; adapter_id, adapter_version: str; capabilities: AdapterCapabilities; models: list[ModelRecord]; started_at: str; finished_at: str或null; code_hash, data_hash, scorer_hash: str; schema_version: str = "0.2"` |

`Slot` 保留键值对应关系，不能平铺答案。number 不接受 bool；version/path 不做全局小写。
非 answer 状态要求 value=null、aliases=[]；冲突候选、遗忘值和旧值存入私有账本或策略。
证据 start/end 是 observation.text 的 Python 字符偏移 `[start, end)`，不是字节或 token；
两者均 null 表示整条观察。Gold 至少有一个 slot 或 expected action。

账本、预期动作、遗忘政策为评测器私有的 JSON 记录，具体事件/动作语义由卡2、3、5定义；
本合同只验证其 JSON 类型，不假装已验证业务真值。所有用于定位观察的依据统一置于
`evidence`，不要依赖自由字典中的自定义 ID 自动得到引用检查。
沙箱 path 只允许相对路径且拒绝 `..`、反斜杠、NUL；这里只做语法验证。
符号链接、实际文件访问、工具白名单和权限隔离属于卡5。cwd 不构成安全边界。

## 两套分类保持独立

`TECHNICAL_CATEGORIES`：`recall, update, multi, temporal, forget, abstain`。
`OFFICIAL_CAPABILITIES` 是独立映射：

| ID | 命题能力 |
|---|---|
| `long_term_retention` | 长期保持 |
| `memory_retrieval` | 记忆调用 |
| `dynamic_update` | 动态更新 |
| `similarity_discrimination` | 相近区分 |
| `boundary_recognition` | 边界识别 |
| `task_reuse` | 任务复用 |

名称沿用仓库 `docs/plan-v2/FULL_RESPONSE.md` 的命题对齐说明。
每题在 Gold 分别记录非空分类列表，不存在自动一对一转换。
一个 recall 标签不能自动证明长期保持或记忆调用已覆盖；覆盖仍需数据审核和实际结果。
分类、story_id、split 均不发送给被测系统。

## 公开和私有边界

- `Observation.to_public()`、`Probe.to_public()` 使用固定字段白名单，输出独立 JSON 副本。
- `Episode.to_public()` 仅输出 episode_id、variant_id、session_ids、observations、probes。
  它用于公开数据导出，不能一次性送给适配器；未来观察需由唯一 runner 按时序投递。
- `Gold.to_public()` 直接拒绝。`Gold`/`Episode` 的 repr 不含私有内容。
- `adapter_payload(value)` 只接受精确类型 Observation/Probe，不接受 Gold、Episode、字典或子类。
- `public_log_record(value)` 同样只接受 Observation/Probe，只留下 ID、role、observed_at。
  不透传文本、query、沙箱字段、对象 repr 或任意 metadata。
- `to_dict()/to_json()` 是完整存盘接口，Gold/Episode 的结果只能进入评测器私有文件。
  禁止把它们、异常原始 payload 或 `dataclasses.asdict(gold)` 写入公开日志。

白名单防止结构字段泄漏，不会识别人为塞入 text/query/ID 的秘密。
公开数据的语义审核仍由数据作者负责；native agent 必须通过实际权限隔离看不到 gold 文件。
模型原始输出与可披露的公开输入需要另存时，由 runner 明确选择字段，不能复用私有序列化。

## 适配器合同

从 `memobench.protocol_v2` 导入：

```python
# component：每个 episode/variant 创建新实例，结束会话保留记忆。
class ComponentAdapter:
    capabilities: AdapterCapabilities
    def observe(self, observation: Observation, operation_id: str) -> WriteReceipt: ...
    def end_session(self, session_id: str, operation_id: str) -> WriteReceipt: ...
    def recall(self, probe: Probe) -> RecallResult: ...

# native_agent：同一个 episode/variant 多会话不能重复 reset_case。
class NativeAgentAdapter:
    capabilities: AdapterCapabilities
    def reset_case(self, episode_id: str, variant_id: str, operation_id: str) -> WriteReceipt: ...
    def begin_session(self, session_id: str, operation_id: str) -> WriteReceipt: ...
    def observe(self, observation: Observation, operation_id: str) -> WriteReceipt: ...
    def end_session(self, session_id: str, operation_id: str) -> WriteReceipt: ...
    def query(self, probe: Probe, operation_id: str) -> Prediction: ...
    def close(self) -> None: ...
```

`WriteReceipt(operation_id, status, usage=None)`：status 为 ready/durable/unknown/failed。
ready 只证明本次写入可供后续读取；durable 还需要适配器有持久化证据；unknown 不能当成功。
`require_ready(receipt)` 拒绝 unknown/failed。异步适配器需在 observe/end_session 返回前等待
可读取状态，或明确返回失败/未知并阻止依赖该写入的 query；等待超时不能伪装 ready。

`RecallResult(status, context, retrieved_evidence=None, usage=None)`：status 为
ok/unsupported/error/timeout，context 为按读取顺序排列的文本列表；证据为 observation ID 列表。
component 只将 recall 的公开内容交给固定公共 Reader。
native_agent 的 Prediction 必须来自被测系统，不能拿 Reader 替代；manifest 要求 native_answer=supported。
不提供结构化答案的系统可以只填 text，state/slots 置 null，后续评分器解析。

`require_capability(capabilities, name)` 对 unsupported/unknown 抛出
`UnsupportedCapability(ContractError)`；未知能力名称属于合同错误。
null 表示不可观察，[] 表示观测到空结果，0 仅用于确实测得零的用量。
`usage` 保留传输层实际返回的 JSON；没有可观察用量就填 null，不估成零。
flush/restart/storage_inspection 的具体操作由真实适配器另行实现和举证，本合同不提供伪实现。

operation_id 标识一次逻辑操作，尤其包括会产生写入的 query。
相同 ID 和相同 payload 重试应返回原结果，不再次写入；同 ID 不同 payload 必须报错。
真实进程重启后重试需要持久去重或明确拒绝重试；内存假实现不承诺跨进程去重。
跨 episode 以及同故事两个 variant 必须隔离；end_session 不清空长期记忆。

## 字段样例及最小假适配器调用

```python
from memobench.schema_v2 import Observation, Probe, Gold, Slot, EvidenceLocation, Episode
from memobench.protocol_v2 import FakeNativeAdapter, require_ready, adapter_payload

o = Observation("e1", "v1", "s1", "o1", "user", "编辑器用 Vim。", "2026-10-14T10:00:00Z")
p = Probe("e1", "v1", "s2", "p1", "编辑器用什么？", "2026-10-14T11:00:00Z")
g = Gold("p1", [Slot("editor", "string", "answer", "Vim")],
         [EvidenceLocation("o1")], [{"editor": "Vim"}], [], [],
         ["recall"], ["long_term_retention"])
e = Episode("e1", "v1", "story1", "dev", ["s1", "s2"], [o], [p], [g])
assert "golds" not in e.to_public()
assert "gold" not in adapter_payload(p)

a = FakeNativeAdapter()
require_ready(a.reset_case("e1", "v1", "op1"))
require_ready(a.begin_session("s1", "op2"))
require_ready(a.observe(o, "op3"))
require_ready(a.observe(o, "op3"))  # 重试不会再次写入
require_ready(a.end_session("s1", "op4"))
require_ready(a.begin_session("s2", "op5"))
prediction = a.query(p, "op6")
assert prediction.text == "编辑器用 Vim。"
a.close()
```

`FakeNativeAdapter` 回显所有观察（含 assistant/tool/system），不理解问题、不执行工具、不持久化。
`FakeComponentAdapter` 提供相同的观察保留行为；每个 episode/variant 需创建新实例。
两者仅服务合同测试，不能作为“两款真实智能体”，不能进入正式真实智能体榜。

## 运行清单

```json
{
  "run_id": "r1", "mode": "component", "execution": "offline",
  "adapter_id": "fake-component", "adapter_version": "contract-0.2",
  "capabilities": {
    "native_answer": "unsupported", "retrieved_evidence": "supported",
    "write_usage": "unsupported", "flush": "unsupported", "restart": "unsupported",
    "storage_inspection": "unsupported"
  },
  "models": [],
  "started_at": "2026-10-14T10:00:00Z", "finished_at": null,
  "code_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "data_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "scorer_hash": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "schema_version": "0.2"
}
```

以上哈希仅为格式样例，不能作为实测运行清单。正式运行必须对实际输入字节计算 SHA256，
多文件对象需先生成确定排序、包含相对路径与各文件 SHA256 的清单，再对清单字节取 SHA256；
产物需保留该清单和序列化规则以便复核。哈希字段固定为64位小写十六进制。

模型记录样例：
```json
{
  "provider": "fixture-provider", "endpoint_id": "endpoint-1",
  "requested_model": "requested-snapshot", "returned_model": "returned-alias",
  "parameters": {"temperature": 0, "max_tokens": 128},
  "version": null, "digest": null, "recorded_at": "2026-10-14T10:00:00Z"
}
```

models 包括实际使用的读取、写入/embedding、回答及 judge 模型记录；未调用模型时可以为空。
请求名和返回名分别记录，未返回模型名或不能确认权重版本/摘要时填 null，不能推测相同。
endpoint_id 是无凭据的稳定服务标识；参数仅含有效生成参数，不含 API key、授权头或账户秘密。
记录时间、真实 adapter 版本、代码/数据/评分器哈希；finished_at 在运行中为 null，完成时不得早于 started_at。
online/replay 必须分开统计；假实现标 offline，不声称测过真实服务。

## 验收

```bash
python -m unittest discover -s tests -p 'test_contract_v2.py' -v
python3 -m unittest discover tests
```

测试覆盖 JSON 往返、必填项、枚举与类型、重复 ID、错误引用、时间与字符位置、真值剥离、
日志边界、分类隔离、未支持能力、写入就绪、重试去重、新会话保留及 episode/variant 隔离。
协议通过不等于数据真值通过人工审核、真实系统接入或 openKylin 验收通过。
