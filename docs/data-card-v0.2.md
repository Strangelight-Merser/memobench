# MemoBench v0.2 候选数据卡

本交付是 **pending_review** 的离线合成候选集，不是已获人工签收的正式测试集。
没有调用 DeepSeek 或其他生成 API，没有实测 openKylin、真实智能体或文件执行结果。
核心代码仅用标准库；沿用卡1的 Episode、Observation、Probe、Gold、Slot、EvidenceLocation、
SandboxReference 及 adapter_payload。没有修改冻结协议或新增 runner。

## 实际规模与缺口

| 项目 | 已提供 | 原计划 |
|---|---:|---:|
| 独立候选故事 | 18 | 60 |
| 开发故事 / 问答 | 6 / 12 | 12 / 24 |
| 测试候选故事 / 问答 | 12 / 24 | 48 / 96 |
| 正式测试故事 / 问答 | 0 / 0 | 48 / 96 |
| 配对规模故事 | 12 | 12 |
| 两种改写 × 三档规模 | 72条 episode | 72条 episode |

每项官方能力有1个开发故事、2个测试候选故事。原技术六类独立保留；类别标签只是作者的候选映射，
不能代替能力有效性审核。版本升级题同时询问最初与当前版本，保留历史值槽位；所有分类仍待人工签收。
未将换名字、换数值或增加噪声算作新故事。剩余42个独立故事及相应开发/测试配额尚未完成，
需在人工核对现有小集后补写、审阅，不能用本集冒充60故事发布。

12个测试候选均提供2048、8192、32768字符规模（2K/8K/32K，K=1024）。
长度为所有 `observation.text` 的 Python `len` 之和，不含问题、JSON包装或角色标签，绝不是 token 数。
每个 episode 有两个会话，每会话40条观察；两种表述不跨集合。
噪声为可重复的无关闲聊，末条补足字符预算，尾部可能截断一条闲聊；这是受控负载，非真实用户日志。
两种改写和三个规模均不能当独立故事计入统计。

## 文件与入口

- `data/v0.2/sources.jsonl`：固定、AI辅助编写的合成情节与独立事件账本，包含两种措辞。
- `candidates.jsonl`：18故事 × 2改写，完整私有 Episode。
- `public.jsonl`：上述候选的 `Episode.to_public()` 导出；只含协议白名单。
- `dev.jsonl`：6故事 × 2改写，供离线开发，不代表人工批准。
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
构建命令去掉 `--validate-only`；默认种子42。不会覆盖已有 `review.jsonl`。
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

两个测试候选直接带文件动作真值，另有一个开发清单用例：
青禾周报迁移路径/模板并排除同事项目；遗忘虚构canary后仍按保留的日记模板创建文件。
其余10个规模故事可供卡5选择组装生命周期任务，本卡没有声称已交付12个完整文件执行场景。
`Gold.expected_actions` 中的动作约定是 `operation=write_file, path, content, sha256`，
哈希按UTF-8内容实际计算。路径仅沙箱内相对路径，大小写保留，不执行shell或创建目标任务文件。
文件动作和遗忘策略需卡3/5接入核对；本卡只验证数据与路径，不宣称任务已执行成功。
遗忘后的新回答/新文件禁止包含虚构canary，否定句也计披露；无物理擦除保证。

## 人工审阅、许可与限制

所有18个账本与问题、两种表述都待人工核对；边界、冲突、遗忘全部必须逐条审阅。
其他样本按原要求至少25%审阅表面文本；当前实现采用更简单严格的门禁：进入正式test的每个故事都审阅两种表述，
并确认三档噪声不改变语义。不能用agent自检或单元测试签成人工通过。
没有真实个人信息；虚构canary不是密钥。数据许可为 `pending_maintainer_signoff`，不自动继承代码许可证。
不得按被测系统是否答错筛除合法样本。详见人工清单与拒收规则。

仓库现有忽略规则覆盖 `data/`。本卡不改 `.gitignore`；集成者纳入版本控制时需显式强制添加 `data/v0.2/`，否则固定数据不会随仓库交付。
