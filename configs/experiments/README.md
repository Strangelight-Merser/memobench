# Native 当前准备入口

`native.json` 是准备 recipe，不是 run config。先用 `python3 tools/prepare_native_run.py --help`；默认使用独立 AI 审核后的 data/v0.2-ai-reviewed（内部用途）；提供 SSH 配置、两产品当前完整 probe.json 和新输出目录，生成可审阅 plan.json 及每产品运行配置。prepare 不联网；缺条件返回 blocked，不生成运行配置。无需人工填写审核表或哈希，公开许可证不阻塞内部用途；当前说明见 [AI 审核结果](../../docs/integrations/ai-review-20261015/ENGINEERING.md)，准备命令和边界见 [实际准备说明](../../docs/integrations/native-preparation-20261015/ENGINEERING.md)。

以下卡6内容保留为该阶段的历史接口与验收记录，不代表当前 native 接线状态。

# 卡6接口与待签收项

这里只提供传输策略，不创建卡7 runner。`llm-policy.json` 是待审核策略，不能直接当作已通过的在线运行配置。当前无已批准模型、真实调用结果或价格；无联网 CI。

```python
from memobench.llm_v2 import LLMClient, Limits
client = LLMClient.from_env(provider="维护者核实的供应商", limits=Limits(), cache_dir=None)
result = client.complete(messages, live=True, repeat=True, input_token_bound=4096)
prediction = result.to_prediction(probe)
model_record = result.model
```

endpoint 环境变量须为完整聊天 URL（含 `/chat/completions`），不含用户名、密码、查询参数。key 只从指定环境变量读取，不进入缓存键、日志、异常信息。不得在生成参数或 messages 中放凭据。缓存属于评测器私有目录，包含原始响应；不可给被测智能体访问。

`complete` 用于无工具执行的聊天 API；写入/embedding/检索由适配器执行后调用 `CostLedger.record_adapter` 或 `record` 记账，不能靠给聊天请求改阶段名声称完成 embedding。`answer(probe, RecallResult)` 仅为 component 公共 Reader；native 的回答由真实适配器给出。Gold 不进入 Reader；judge 的私有证据组装由卡3管理。

`LLMResult.status` 的 blocked/error/timeout 是传输诊断；`to_prediction` 将 blocked 映射为冻结协议的 error，详细 reason 由调用者另存诊断。`ModelRecord` 沿用卡1字段；未经核验的 version/digest 保持 null。无 usage 为 null，未调用阶段的费用为 null。`CostLedger.records` 保留每阶段、每次尝试；回放记录排除于在线费用。价格仅接受调用者审核的输入/输出每百万 token 单价，货币单位与价格出处应由正式实验配置保存，不在代码内写供应商价格。

每个 client 串行使用，计数器覆盖其生命周期；总运行应共享该 client/ledger，恢复进程前由总集成者恢复预算或停止继续调用，不能重建 client 后把已花预算归零。请求预算包括重试。调用前需提供保守的 `input_token_bound`（包含模板开销），输出由 max_tokens 限制；此上界不是实测用量。没有供应商 tokenizer 时不能把字符数直接当 token 数。429/5xx 可重试，按 Retry-After 秒或 HTTP 日期等待；超过等待上限直接停，不提前重试。超时不自动重试，避免未知完成状态造成重复工作。

累计 token/费用在成功且有 usage 时使用返回值；可重试 HTTP 失败缺 usage 时按本次输入/输出上界保留预算，账本实际用量和费用仍为 null。其他缺 usage 结果使预算变为未知，后续调用 blocked。上界依赖调用者正确提供，不能承诺抵御服务违反 token 上限或供应商计费规则。服务报告超限时后续请求会被阻止，当前结果保留。带 max_cost 时必须提供价格；价格模型仅适用普通输入/输出计费，特殊缓存折扣/工具费用需要外部记账，不声称覆盖未知费用。

缓存键含完整 endpoint、请求/解析协议版本、模型、所有显式有效参数和完整 messages；服务端未指定默认值不保证跨时间固定，正式实验须显式配置所需参数。成功缓存含 raw response、usage、模型记录、finish reason、UTC 时间、历史在线延迟。回放返回 online_latency_ms=null、独立 replay_latency_ms；不会重新计在线成本。重复实验 `repeat=True` 必须 cache_dir=None，否则 blocked。

统计调用 `summarize(episodes, samples, execution=..., expected_repeats=[...])`，其中 `Sample` 包含冻结 `Prediction`、卡3评分（0..1 或 null）、repeat_id 和执行模式。各系统分别汇总，严格分离 offline/online/replay。n_query 为计划中的 variant/probe 数，n_story 为独立故事数，n_repeat 为该模式有返回记录的重复 ID 数（回放恒为0），另报计划重复数、缺失和各能力评分分母；error_rate 分母是全部计划调用，分子含 error/timeout，不含 unsupported。没有返回记录的题也计缺失，不把未评分算成0。

`paired_bootstrap` 按题目引用及 repeat_id 匹配，仅使用双方都可评分的配对，报告丢失配对数；先把同故事所有配对差值平均，再以故事等权有放回抽样2000次，固定种子42，输出 left-right 差值及百分位95%区间。不足两个故事不提供区间。缺失可能引入选择偏差，需同时展示 summarize 的全部计划分母。Wilson 仅用于合适的独立二项样本，不应直接用于同故事改写、多 probe 或重复调用。单类 Cohen kappa 由卡3拥有的实现负责；卡6不另建同名统计实现。

人工后续：核验运行当天官方文档，选定模型与价格、保守输入 token 上界；配置环境变量，在明确启用 live 后做小预算健康探测；保存原始响应与 ModelRecord 再批准模型。Qwen 优先固定快照；DeepSeek alias 不等于冻结权重。openKylin 实测及真实模型稳定性目前均 NOT_VERIFIED。数据、裁判校准与人工盲标不属本卡签收范围。

离线签收（本工作树）：传输17项、统计9项、全量 `python3 -m unittest discover tests` 共72项通过；所有新增传输测试使用假 opener。单类 kappa 的集成验收 blocked：当前工作树无卡3 judge/scoring 实现，待卡3提供后由总集成者运行，不能将此项写为已通过。没有执行真实 API 健康探测、openKylin 实测或人工审核。
