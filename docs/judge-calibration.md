# 卡3：评分与人工校准

本次只交付标准库代码、离线回归 fixture 和校准流程。真实语义裁判、人与模型一致率和 openKylin 实测均为 **NOT_VERIFIED**。当前无卡6 `llm_v2.py`、无 DeepSeek 凭据、无真实留出输出；在线裁判接入为 **blocked**，用户盲标为 **pending_review**。没有发布纯 judge 排名。

## 接口与边界

复用 `schema_v2.Gold/Slot/Prediction/Probe/Observation/AdapterCapabilities`，公开查询经 `protocol_v2.adapter_payload` 提取，证据引用经 `validate_prediction` 检查。没有修改协议或旧版文件，没有新增 runner。

- `scoring_v2.score(gold, prediction, *, task_checks=None)` 返回逐题评分字典。
- `judge_v2.judge(gold, prediction, probe, observations, capabilities, *, transport=None, task_checks=None)` 补充硬规则无法判断的语义项。
- `scoring_v2.summarize(scores)` 返回各指标计数、分母和待复核数。
- `judge_v2.overall_label(scored)` 将完整评分转换为整体校准标签，pending保持null。
- `judge_v2.agreement([(human_bool_or_null, model_bool_or_null), ...])` 计算一致率、Cohen kappa、混淆矩阵及错误放行率。
- `judge_v2.prepare_blind(records, development)` 构造至少60个独立故事的留出盲标包，要求至少20个开发输出，故事与情节模板均不相交。
- `judge_v2.calibrate(annotations, judgments)` 按 item_id 对齐、保留逐条标签并检查本项目门槛。

评分结果包含 `probe_id/status/source/metrics/eligible/errors/review_reason`，语义评分另含 `evidence_ids/reason`。这些是评分产物字段，不是第二套被测输入或 Gold。调用方须按 episode/variant/probe 存放，不能只按 probe_id 全局合并。

六个独立指标为 `answer_correct`、`current_value_misuse`、`forgotten_disclosure`、`unknown_assertion`、`evidence_supported`、`task_completed`。前三种风险指标中 current_value_misuse/forgotten_disclosure，以及 unknown_assertion 的 true 代表发生错误，其余 true 代表成功。`errors` 记录已确认的错误；解析失败、证据缺失、服务失败不伪装成业务错误。

每个指标有 numerator（true数）、denominator（已判定数）、eligible（适用数）、pending（适用但未判定数）。零分母 rate=null。不适用与未验证均不填0，须结合 eligible/pending 区分。报告不能只展示已判定分数而隐藏 pending。

## 硬规则

按 slot.name、value_type、state 对应比较，不平铺答案。number 用十进制值精确比较，拒绝bool冒充数值；不隐含容差、单位转换。string/version/path 区分大小写、空格和完整值；不做版本子串、路径小写或文件系统解析。替代表达必须由 Gold.slots.aliases 明确声明，候选自报别名无效。

结构化正文使用 `{"slots": [Slot.to_dict(), ...]}`，或使用 text="" 加 Prediction.slots。这只是冻结 Slot 的承载格式。含散文、未知/重复键、无效类型、正文与侧字段不一致时进入语义复核；不通过“抽取出一个对的值”覆盖回答中的否定或矛盾。

四种状态 answer/unknown/forgotten/conflict 分开判断。拒答不能满足本应给值的题，也不能完成任务。任务检查只能来自可信文件/动作验证器：`task_checks` 必须与 Gold.expected_actions 等长，元素为 bool/null；任何false即失败，剩余未知保持null。裁判输出 task_completed 非null会被拒收，不能把“我已创建文件”当成功。

## 私有政策约定（供卡2/卡5接入）

冻结合同允许私有账本/策略为 JSON 字典，本卡仅定义以下业务记录，不新增协议顶层字段：

```json
{"slot":"editor","scope":"current","previous_values":["Emacs"]}
```

放在 Gold.canonical_state_ledger，表示本题询问当前值，旧值列表用于识别误用。合法历史问题使用 scope="historical"，不纳入当前值误用分母。其他账本记录不自动猜测成过期规则。对于复杂时序/自然语言，交给语义裁判；无法解释的政策必须人工复核。

```json
{"slot":"secret","mode":"literal_disclosure","values":["虚构CANARY-27"]}
```

放在 Gold.forget_policies，表示本题已经在删除请求之后；精确、区分大小写的明文出现即算披露，包含否定句和结构化值。这是明确用例政策，不宣称检测所有编码/转述，更不代表物理存储擦除。政策应用时点由数据作者及 runner 负责；其他删除政策不擅自套用明文规则。

## 单答案裁判与卡6接入

`transport(messages) -> str` 是依赖注入点，输入只有评分消息，输出为单次裁判响应正文。卡6调用方负责真实 transport 状态、预算、截断检查、usage、模型版本、缓存/在线区分和请求留档；失败应抛异常。这里不猜测尚未存在的卡6函数名，也不重复实现网络、缓存、重试或模型配置。

提示词固定在 `prompts/judge-v0.2/system.txt`；系统指令、评测器证据/问题/真值/别名/政策、候选回答分别封装。候选只作为JSON字符串发送，不拼接为system角色。接口不接收适配器/模型名称，不传Prediction.usage。候选自行声称的身份仍属不可信正文，提示要求忽略。结构隔离与fixture测试不等于已经证明真实模型抗注入。

裁判必须返回严格JSON：status、metrics、evidence_ids、reason，禁止Markdown、重复键、非有限数值、错类型及未知证据引用。语义支持为true须有引用；引用合法本身不证明支持。证据不足或裁判主动pending不计为业务失败；独立任务检查与确定的硬规则结论不能被裁判覆盖。

原审计中的“不是UKUI”“不知道但你住北京”、否定旧值等自然语言反例，以预写裁判fixture验证接收/合并逻辑；它们不是在线模型能力测量。结构化字段互换、版本子串、Linux大小写、明文删除披露等由硬规则测试覆盖。

## 开发与留出流程

`evaluation/calibration/development.jsonl` 含20个固定、人工编写逻辑生成的合成开发候选输出，离线测试实际调用评分器核对。source明确为 authored_synthetic_fixture，人工审阅仍 pending_review；它们不是被测智能体的实测输出，也不是用户盲标结果。

`holdout.jsonl` 当前为空；60个独立留出输出尚未采集，不能通过复制改写开发fixture凑数。`status.json` 记录缺口。项目数据预算只有48个测试故事；若需要60个独立故事的校准留出输出，须另采独立校准故事，不能把96个成对改写当96个独立故事。

人工步骤：

1. 用真实输出补齐至少20个开发样本并审核规则/提示；固定代码、提示、数据和裁判配置的哈希，再开始留出。开发中的模型调用/规则调整过程单独留档。
2. 另采至少60个独立故事的输出。传入prepare_blind的每条记录包含story_id、template_id以及冻结协议格式的probe/gold/prediction/observations。与开发故事、模板完全隔离，输出按内容哈希排序。
3. 人工预检正文是否自报模型身份并处理盲化，保留私有原始对应关系；不要修改原始回答证据。盲标包不含模型名元数据或裁判标签；不要把私有gold发给被测智能体。用户逐条填human_label=true/false/null与review_status=reviewed。标签含义是整体可接受：所有适用的正确性/支持/任务项成功，且无任何适用风险项；无法判断保留null。
4. 独立裁判结果存为 `{"item_id":"…","model_label":true或false或null}`；只能从完整判定的评分结果导出标签，pending不能擅自转换成false/true。人工标注时不得显示它们。保留原始裁判JSON、理由与逐项指标供事后复核。
5. 用下列离线入口计算，或由卡7的统一calibrate命令调用同名函数：

```bash
python3 -m memobench.judge_v2 --annotations evaluation/calibration/holdout.jsonl \
  --judgments evaluation/calibration/judgments.jsonl \
  --out evaluation/calibration/report.json
```

一致率与kappa仅在双方均有标签的配对上计算，同时报告pending。混淆矩阵行是人工、列是模型；错误放行率=人工false且模型true / 人工false的有效配对数。单一类别导致kappa不可定义时null，空分母亦null。

至少60个有效留出配对、无缺失、一致率≥90%、kappa≥0.7才开放本项目纯judge排名门槛。两阈值只是项目门槛；当前没有达成证据。未达标或样本不足时用小集合人工裁决，不发布纯judge排名。不能在留出上调规则后重复宣称该集合是独立验证；调整后需要新留出集。

## 离线验证

```bash
python3 -m unittest discover -s tests -p 'test_scoring_v2.py' -v
python3 -m unittest discover -s tests -p 'test_judge_v2.py' -v
python3 -m unittest discover tests
```

CI不联网、不使用付费API。测试通过仅代表本地逻辑与fixture通过；openKylin不属于本卡评分代码的运行前提，但正式系统结果仍需在真实环境另行签收。

本次本地验收：评分12项、裁判14项均通过；完整 `python3 -m unittest discover tests` 共72项通过，包含已有46项。`git diff --check` 通过。空留出校准实际返回pending_review，n=0、agreement=null、cohen_kappa=null、publish_judge_ranking=false。以上均为离线结果。
