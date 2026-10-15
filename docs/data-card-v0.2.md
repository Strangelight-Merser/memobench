# MemoBench v0.2 候选数据卡

本卡前半部分记录原始 `data/v0.2` 候选快照（**pending_review**，原目录 test 为 0），保留其生成时口径。当前内部使用目录 `data/v0.2-ai-reviewed` 已完成独立 AI 审核与主复核：59 故事接受、1 故事拒收，12 dev、47 test / 94 改写，状态 **accepted_internal**；无需用户填写审核表，不宣称人工签收或未见留出。详见[当前工程说明](integrations/ai-review-20261015/ENGINEERING.md)。
原始数据生成没有调用 DeepSeek 或其他生成 API；本候选快照的生成记录不包含产品实测，后续真实接入证据另见集成文档。
核心代码仅用标准库；沿用卡1的 Episode、Observation、Probe、Gold、Slot、EvidenceLocation、
SandboxReference 及 adapter_payload。没有修改冻结协议或新增 runner。

## 原始 data/v0.2 候选快照规模与状态

| 项目 | 已提供 | 原计划 |
|---|---:|---:|
| 独立候选故事 | 60 | 60 |
| 开发故事 / 问答 | 12 / 24 | 12 / 24 |
| 测试候选故事 / 问答 | 48 / 96 | 48 / 96 |
| 正式测试故事 / 问答 | 0 / 0 | 48 / 96 |
| 配对规模故事 | 12 | 12 |
| 两种改写 × 三档规模 | 72条 episode | 72条 episode |

每项官方能力有2个开发故事、8个测试候选故事，共10个独立候选故事。原技术六类独立保留；类别标签只是作者的候选映射，
不能代替能力有效性审核。版本升级题同时询问最初与当前版本，保留历史值槽位；原始快照的分类审核状态保持待审。
新增42个候选保留不同情节关系，不以改名字、改数值或增加噪声充数。
原18个故事保持原样；新增每项能力1个开发、6个测试故事。原始快照的60条待审记录保持原样；新目录的实际 AI 审核结果不覆写这些历史记录。
语义上的近重复及分类适切性需实质审核，模板ID隔离本身不是独立性证明。

保留原来的12个测试候选作为配对子集，均提供2048、8192、32768字符规模（2K/8K/32K，K=1024）。
长度为所有 `observation.text` 的 Python `len` 之和，不含问题、JSON包装或角色标签，绝不是 token 数。
每个 episode 有两个会话，每会话40条观察；两种表述不跨集合。
噪声为可重复的无关闲聊，末条补足字符预算，尾部可能截断一条闲聊；这是受控负载，非真实用户日志。
两种改写和三个规模均不能当独立故事计入统计。

## 原始 data/v0.2 文件与入口

- `data/v0.2/sources.jsonl`：固定、AI辅助编写的合成情节与独立事件账本，包含两种措辞。
- `candidates.jsonl`：60故事 × 2改写，完整私有 Episode。
- `public.jsonl`：上述候选的 `Episode.to_public()` 导出；只含协议白名单。
- `dev.jsonl`：12故事 × 2改写，供离线开发，不代表人工批准。
- `test.jsonl`：正式测试入口，当前为空；无签收不能进入。
- `paired-2048.jsonl`、`paired-8192.jsonl`、`paired-32768.jsonl`：相同12个测试候选的配对版本，仍是私有、未审阅候选。
- `review.jsonl`：每故事的来源类型、证据ID、源内容摘要、状态、审阅者、时间和核对结果。
- `manifest.json`：生成参数、真实文件SHA256、数量与阻塞状态。
- `generation-record.md`、`review-checklist.md`、`rejections.jsonl`：生成记录、人工清单、拒收规则。

```bash
python3 tools/build_dataset_v2.py --validate-only --dataset data/v0.2
python3 -m unittest discover -s tests -p 'test_data_v2.py' -v
python3 -m unittest discover tests
```

`--validate-only` 不写文件，不访问网络。退出0表示结构、内容与门禁验证通过，**不表示正式发布获批**；
输出明确保留 `release_status: pending_review` 和正式题数。
构建命令去掉 `--validate-only`；默认种子42。保留 `review.jsonl` 已有行，只为新增故事追加 pending_review 记录，不自动批准或替换过期签收。
构建后仍须验证。CI不调用生成服务；固定JSONL是实际读取材料，不在测试中在线生成。

集成可用 `load_dataset(root, split='dev'|'test'|'candidates')`，返回冻结协议的 Episode 列表；
正式测试必须选 `test`。调用 `generate` 仅供离线构建与开发验证，不能绕过审阅门禁开展正式测试。
公开传输用 `adapter_payload(observation_or_probe)`；不可向被测系统传整份私有 Episode。
公开观察本身会包含用户提供的事实，这是题目输入，不是泄漏私有gold；不得以“答案字符串不得出现在观察中”检查边界。
本目录含私有真值，native agent 的实际权限隔离由卡4/5/7落实；文件名或cwd不构成安全沙箱。

## 真值与成对扰动

先通过 `truth(events, targets)` 回放账本得到 Slot，再选择表面措辞；不从自然语言用正则抽取gold。
账本自由字典位于协议允许的 `Gold.canonical_state_ledger`，不是另一套公开协议：

- `set`：按顺序赋值，同一轮可连续更正；设备架构只来自指定设备的观察。
- `copy`：复制已知状态；`join`：把明确给定的目录与文件名组合，缺依据则拒绝。
- `conflict`：保留未裁决候选，Slot值为null；不凭顺序覆盖明确的冲突。
- `forgotten`：目标Slot值为null，不清空其他键；未观察键为unknown。
- `utterance`：源表述索引，映射到 Gold.evidence 的观察ID；协议证据引用仍由 EvidenceLocation 校验。

证据按整条观察记录（start/end均null），当前保留完整核心观察链供人审阅。
问题选定的目标键位于私有源记录，不发送给系统。
设备甲/乙的架构来自故事中明确给出的 uname 输出，这是**虚构观察**，不是本机实测；
“龙芯机器”昵称无法推出架构，gold为unknown。没有将KARE标成包管理器。

事件、措辞、噪声的随机源分别由 SHA256(JSON([seed, stream, story_id])) 派生，
不依赖Python进程随机hash；事件流决定故事日期。噪声档位不改变核心观察、问题、账本、证据ID或gold。
所有对外ID是SHA256截断后的opaque标识，不能从ID直接读出类别或答案。
开发/测试使用不同故事和不同情节模板；代码验证模板ID不交叉，人工还需检查语义上的近重复。

## 文件任务与遗忘

7个测试候选、2个开发故事直接带文件动作真值；另一个任务复用测试故事只要求复述已约定操作流程。
文件故事包括路径/模板迁移、遗忘后保留模板、按文档种类选模板、目录与文件名组合及精确内容标记。
原12个配对故事的选择保持不变，其中只有2个直接包含文件动作；其余10个可供卡5组装生命周期任务。
本卡没有声称已交付12个完整文件执行场景。
`Gold.expected_actions` 中的动作约定是 `operation=write_file, path, content, sha256`，
哈希按UTF-8内容实际计算。路径仅沙箱内相对路径，大小写保留，不执行shell或创建目标任务文件。
文件动作和遗忘策略需卡3/5接入核对；本卡只验证数据与路径，不宣称任务已执行成功。
遗忘后的新回答/新文件禁止包含虚构canary，否定句也计披露；无物理擦除保证。

## 审核、内部用途与公开许可

当前支持两种真实审核类型：human 0.2 人审记录，或 independent_ai 0.3 独立 AI 审核与不同身份主复核。AI 路径绑定两份原件的 SHA-256、全故事逐条源摘要/结论和已审改写/配对材料的实际摘要；不能用单元测试、单一 accepted 字符串或 AI 署名冒充人工。

本次用户明确授权独立 AI 审核及项目内部使用。原始 data/v0.2 保持原样；新 data/v0.2-ai-reviewed 采用 accepted_internal，面向项目内部回归评测。独立及主审均阅读全 60 故事，审核曝光完整记录；框架开发曝光与被测模型训练/调参不能混同。本轮没有被测模型训练/调参调用，对以前历史不作无依据声明。AI 审阅后的材料不宣称未见留出或公开排名。

独立审核接受 59 故事，拒收青禾 1 个故事（gold 禁用路径约束不完整），不是因为被测系统答错而筛题。12 个 dev 故事、47 个内部 test 故事，每故事两改写；内部 test 共 94 variants，不是 94 个独立故事。内容修复须新审核与新指纹，不静默修改原件。

内部 usage-approval 只证明用户授权范围、来源核查与 internal_evaluation_only，不是数据公开许可证，也不继承代码许可证。维护者现已明确授权自建合成数据按 [CC BY 4.0](../data/LICENSE.md) 公开，当前授权及原始文件摘要见 [PUBLIC_LICENSE.json](../data/PUBLIC_LICENSE.json)。历史 usage-approval 保持原样，其内部用途字段不再限制本次公开许可。详情见 docs/integrations/ai-review-20261015/ENGINEERING.md。

仓库现有忽略规则覆盖 `data/`。本卡不改 `.gitignore`；集成者纳入版本控制时需显式强制添加 `data/v0.2/`，否则固定数据不会随仓库交付。

## 可选人工审核页（human 路径）

打开 `docs/review/data-review.html`，每次展示一个故事，三栏分别列出事件账本、两种表述的会话、问题与私有真值。
证据ID对应到核心观察；每个会话可展开全部40条观察。原12故事可切换2048/8192/32768字符负载。
通过/拒收均需填写实际审阅者和原因；通过还需确认账本问题一致、所有表述及适用负载已检查。
状态仅在当前页面内存中保存，关闭前用“导出审核 JSON”下载；不依赖外部脚本、服务或网络。
导出含整体源摘要、每故事源摘要及审核记录，不自动写回仓库，不自动进入正式test。
维护者核对摘要后，将导出 `records` 按行合入 `review.jsonl`，再重建并验证；不得把页面自检当人工签收。
此页内嵌私有真值，不能提供给被测智能体。

重建数据及审核页：
```bash
python3 tools/build_dataset_v2.py --dataset data/v0.2 --review-page docs/review/data-review.html
```
`--validate-only` 禁止与 `--review-page` 同用，保证验证命令不写文件。
