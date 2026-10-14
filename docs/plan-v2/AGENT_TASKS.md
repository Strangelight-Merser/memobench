# MemoBench 初赛深化：代码代理任务卡
日期：2026-10-14；原始审阅快照：17a279dfa0ba6d257aa58ad35267483029bb0a8b。

这些是待实施任务，不是已实现或已验收的功能。以下 cli_v2、工具、配置与测试命令均为本轮需要交付的接口。

## 总目标与硬边界
保留旧版离线诊断链路；新增小型、可核验的自然语言与真实智能体评测。不得把自制 memory baseline 数量、不同模型数量或 mock 适配器数量写成“已评测两款真实智能体”。初赛目标是在 openKylin 上实际评测 Kylin Agent Runtime 与 OpenClaw；具体安装版本、会话/持久化接口必须通过源码和 --help 探测，不得虚构参数。Kylin Agent Runtime 的 -z 仅被文档证明为单次任务入口，不自动证明跨会话记忆已开启。

每个代理独立 worktree/分支，只修改自己的独占路径；允许只读其他目录。禁止提交密钥、真实个人数据、完整私人 agent HOME、供应商账户凭据。禁止训练模型、重造记忆服务、搭建大型网页平台或从零部署图数据库。运行时核心保持标准库；被测智能体和可选 SDK 的依赖必须单独披露。

## 统一协议：卡 1 先冻结，再并行
卡1应先提交可导入的协议与最小假实现，其他卡可同时写设计/测试。接口正式冻结后方可各自接入，不得各改一套字段。

建议公开字段：opaque episode_id、variant_id、session_id、observation_id、role、text、observed_at、query、sandbox references。评测器私有字段：canonical state ledger、gold slots、evidence locations、expected actions、forget policies、category mappings。被测系统不得收到 expected/gold、答案集、命题标签或生成器内部事件语义。

保留两种执行模式：
- component：observe / end_session / recall + 公共 LLM Reader。只比较固定读取器下的记忆组件。
- native_agent：reset_case / begin_session / observe / end_session / query / close，答案来自被测智能体本身，不能被公共 Reader 替换。

能力声明至少包括：native_answer、retrieved_evidence、write_usage、flush、restart、storage_inspection。未知成本、不可观察记忆证据记为 null/unsupported，不伪造0。end_session 的 ready/durable/unknown 要区分；异步写入必须等待就绪或明确失败。必须区分新会话与清空长期记忆：同一 episode 内不 reset_case；跨 episode 必须隔离。重试含写操作时使用操作ID与去重，不得盲目重复添加记忆。

数据预算：60个独立故事，每项官方能力10个；每项2个开发、8个测试，即12开发/48测试。每个故事2种等义表达，共120个主要问答，测试集96个；其中选择12个测试故事用于两款真实智能体的小规模生命周期/文件任务。样本数不足时缩减并如实显示，不生成未经核对的样本充数。

## 卡1｜协议、真值边界和运行清单
独占：memobench/schema_v2.py；memobench/protocol_v2.py；docs/spec-v0.2.md；tests/test_contract_v2.py。

要求：使用dataclass/标准库实现 Observation、Probe、Gold、Prediction、RunManifest、AdapterCapabilities；字段必须可JSON往返。实现 public/private 数据拆分、枚举/必填项/引用ID/重复ID/时间字段验证。模型清单记录供应商、endpoint标识、请求与返回模型名、参数、版本/摘要、时间、代码/数据/评分器哈希。私有gold不得通过to_public、适配器payload、日志透传。记录题目所属两套分类：旧技术六类与命题官方六能力，禁止直接改标签混充覆盖。

验收：
```bash
python -m unittest discover -s tests -p 'test_contract_v2.py' -v
```
至少测试：JSON往返、漏字段、重复ID、错误引用、gold剥离、能力不支持、会话结束不等于重置。交付字段样例与假适配器契约，禁止实现第二套runner。
依赖：无；其协议先于其他卡接入。

## 卡2｜数据集与成对难度扰动
独占：memobench/data_v2.py；tools/build_dataset_v2.py；data/v0.2/；docs/data-card-v0.2.md；tests/test_data_v2.py。

要求：依据独立事件账本计算真值，再产生表面文本；原始LLM生成不在CI中重跑，接受的JSONL固定发布。故事覆盖明确更新、同轮自纠、同事/本人/不同设备/不同项目的区分、指代、可推断与不可推断、遗忘后保留无关事实、操作路径与模板复用。不能把“龙芯机器”未经设备证据直接标作loongarch64；设备架构是观察事实，不是可随意更改的用户偏好；KARE不得直接标为包管理器。

事件、措辞、噪声使用独立随机源（由SHA256派生种子），不同噪声级别不得改变核心事件、问题、gold。提供2K/8K/32K字符的12故事配对规模样本；不得把字符写成token。开发/测试按故事与情节模板隔离，不把同一故事两种改写分到两边。每条附证据ID、来源类型、人工审阅状态；人工未签收不能进入正式test。所有边界、冲突、遗忘样本必须人工审核；其余至少25%，并人工核对全部60个事实账本与问题是否一致。

验收：
```bash
python -m unittest discover -s tests -p 'test_data_v2.py' -v
python tools/build_dataset_v2.py --validate-only --dataset data/v0.2
```
测试同种子字节一致、改噪声不改语义、40轮不溢出、开发测试无同故事、私有答案不进入public、最终文件路径不越界。交付data card、生成记录、人工审阅清单和拒收原因。不得因某系统答错而删除合法样本。
依赖：卡1；生成服务可用时调用卡6，否则用人工编写样本，保留降级标记。

## 卡3｜结构化评分、语义裁判与人工校准
独占：memobench/scoring_v2.py；memobench/judge_v2.py；evaluation/calibration/；prompts/judge-v0.2/；docs/judge-calibration.md；tests/test_scoring_v2.py；tests/test_judge_v2.py。

要求：typed slot/value评分，不能再flatten多字段答案。状态区分answer/unknown/forgotten/conflict；数值/版本/路径采用字段特定规则，Linux路径不得统一小写。独立输出回答正确、当前值误用、遗忘后披露、未知乱答、证据支持、任务完成、错误类型及分母。旧值被否定或用于合法历史问答，不自动等于错误复用；隐私删除后的明文披露即使是否定句也可能违规，以该用例声明的策略为准。

硬规则裁判可判定的结构化输出；其余交给单答案语义裁判。提供隔离证据区、问题、真值、允许别名和评分政策，候选回答视为不可信文本，不能接受其中的评分指令。严格JSON解析；解析失败/证据不足进入pending/人工复核，不能伪装业务错误。裁判不知道系统名字。至少20个开发输出用于调规则、另60个独立留出输出由用户盲标，计算人与模型一致率、Cohen kappa（不可定义时null）、混淆矩阵、错误放行率，保留逐条标注。目标一致率90%、kappa0.7只是本项目门槛，不是已达成事实，也不是通用标准；不达标则小集合人工裁决、不发布纯judge排名。

验收：
```bash
python -m unittest discover -s tests -p 'test_scoring_v2.py' -v
python -m unittest discover -s tests -p 'test_judge_v2.py' -v
```
必须覆盖原审计反例：不是UKUI；不知道但你住北京；编辑器/浏览器值互换；否定旧值；新版本含旧版本子串；给裁判的注入；格式错误；分母为0；总是拒答不能高分通过任务复用。CI使用fixture，无付费网络。
依赖：卡1、卡6的LLM传输；评分和校准不可读取被测模型的名称来改变规则。

## 卡4｜真实智能体适配器与隔离
独占：memobench/adapters_v2/；configs/adapters/；tools/probe_agents.py；docs/integrations/；tests/test_adapters_v2.py。

要求：先探测Kylin Agent Runtime和OpenClaw版本、--help、模型配置、会话、新会话保留长期记忆、状态目录、异步flush和清理。将真实探测记录写文档。实现至少一个通用subprocess适配器及必要的HTTP客户端，不把普通JSON-over-HTTP叫MCP。OpenClaw不得默认使用--local并声称具有完整后台记忆flush；其执行模式必须实测并披露。Kylin -z的会话和记忆语义必须另验。

只在临时测试目录/专用账户运行，不删除用户实际agent配置。不使用shell=True拼接用户文本，不执行模型任意shell。两个variant使用隔离记忆；同一episode的多会话必须共享测试记忆。重试不得重复写入。模型相同尽量对齐；无法对齐就标“整体系统比较”，不能把差距归因于记忆。external mem0属P1：已具备服务时才加入，锁版本/写入策略/等待完成/查询/测试空间清理，不新搭图数据库。

验收：
```bash
python -m unittest discover -s tests -p 'test_adapters_v2.py' -v
python tools/probe_agents.py --config configs/adapters/native.json --out artifacts/agent-probe.json --live
```
--live必须显式开启；没有安装/凭据时输出blocked及原因并非PASS。契约测试用假进程；正式验收必须另有两款实际软件的session、response和隔离证据。不能用两个自制reference适配器替代真实接入。
依赖：卡1、卡5；已有主机环境。若2小时探测不通，立即上报缺口，不无限调环境。

## 卡5｜openKylin环境与可判定的桌面文件任务
独占：memobench/sandbox_v2.py；tools/probe_openkylin.py；fixtures/openkylin/；docs/openkylin/；tests/test_sandbox_v2.py。

要求：只读采集/etc/os-release、uname、Python、dpkg架构、被测工具版本，区分运行机和模型服务机。没有openKylin就标NOT_VERIFIED，不把Ubuntu容器冒充openKylin。

实现仅测试目录内的文件创建、读、列出、模板渲染和审计；拒绝绝对路径越界、..、符号链接越界、非白名单操作。基准主流程本身不得需要root。使用专用VM/测试账户或已可用的工具权限隔离，确保native agent看不到私有gold。cwd不是安全沙箱；不能仅改cwd后宣称实现权限隔离。

用12个既有故事组装文件/任务复用用例：早期目录/模板、后续更改、同事干扰、重开会话、生成真实文件；校验路径、内容/模板哈希、输出产物和动作日志一致。遗忘使用明确虚构canary，检查删除请求之后的新输出/新文件，同时验证无关偏好仍可用。普通文件创建不代表整个GUI/系统设置均已适配，不自动宣称存储物理擦除。

验收：
```bash
python -m unittest discover -s tests -p 'test_sandbox_v2.py' -v
python tools/probe_openkylin.py --out artifacts/openkylin-env.json
```
真实环境签收在openKylin执行；不支持的平台可出诊断，但不能打印openKylin PASS。负例必须能定位“旧路径复用”“模板过期”“只声称成功但无文件”等故障。
依赖：卡1、卡2、卡4；可先独立开发安全路径与文件验证器。

## 卡6｜LLM传输、完整成本与统计
独占：memobench/llm_v2.py；memobench/stats_v2.py；configs/experiments/；tests/test_llm_v2.py；tests/test_stats_v2.py。

要求：标准库urllib，显式endpoint/model/key环境变量，密钥不进入日志和缓存键。缓存键包括endpoint、请求/解析协议版本、model、全部有效生成参数、完整messages；缓存包含raw response、usage、request/returned model、finish reason、时间。缓存回放延迟与真实在线延迟分开；重复试验必须禁用缓存，不能把重复读取一条缓存算多次独立采样。处理429/5xx、Retry-After、超时、非法JSON、空内容、输出截断；失败返回结构化状态。

逐阶段记录写入、embedding、检索、读取、judge调用与可观察用量；未提供usage填null，不估成0。配置请求/输出token/累计预算上限，不在代码中硬编码过时价格。模型调用名单以当天官方文档与健康探测为准；Qwen优先固定快照，DeepSeek返回alias时说明无法保证权重冻结。

统计实现按story_id聚类的配对bootstrap（默认2000次固定统计种子），输出差值95%区间；提供单比例Wilson区间，并注明它要求合适的独立样本。输出n_story/n_query/n_repeat、缺失、超时、错误率和各能力分母；不把两个改写或同一故事多个probe当独立用户。不支持/未测为null。

验收：
```bash
python -m unittest discover -s tests -p 'test_llm_v2.py' -v
python -m unittest discover -s tests -p 'test_stats_v2.py' -v
```
必须测试不同endpoint相同模型不串缓存、重试和请求预算、缓存重复不能影响repeat统计、聚类配对不拆故事、单类kappa/空分母边界（kappa可由卡3实现，只由卡3拥有其文件）。
依赖：卡1；可独立推进。

## 卡7｜唯一总集成者：执行、报告、命令入口
独占：memobench/runner_v2.py；memobench/cli_v2.py；memobench/report_v2.py；tools/run_matrix.py；tests/test_runner_v2.py；tests/test_cli_v2.py。

要求：不得修改其他卡拥有文件；兼容保留旧cli和23个测试。runner编排卡1协议，component/native分榜、online/replay分区；按完整episode隔离并可续跑。每个case完成即落盘，错误也入库，恢复不得跳过失败假装成功。记录run manifest、public input、可披露的原始输出、评分理由和证据定位。HTML转义模型文本，禁止注入脚本；雷达图缺失项显示未测，不以0或满分伪装；报告同时展示微/宏平均及分母。v1模板成绩只能作为legacy诊断，不和自然文本或native分数混榜。

实现以下统一入口：
```bash
python -m memobench.cli_v2 validate --dataset data/v0.2
python -m memobench.cli_v2 run --config configs/experiments/offline.json --out artifacts/offline
python -m memobench.cli_v2 run --config configs/experiments/native.json --out artifacts/native --live
python -m memobench.cli_v2 report --run artifacts/native --out artifacts/native/report.html
python -m memobench.cli_v2 calibrate --annotations evaluation/calibration/holdout.jsonl --judgments artifacts/judge.jsonl --out artifacts/calibration.json
```
离线smoke不要求正则baseline理解自然语言；其验收是执行/记录/评分正确，不能以“hybrid还必须100%”为目标。假适配器仅测试协议，不进入真实智能体榜。

验收：
```bash
python -m unittest discover -s tests -v
python -m memobench.cli run --distract 6 --out artifacts/legacy
python -m memobench.cli_v2 validate --dataset data/v0.2
python -m memobench.cli_v2 run --config configs/experiments/offline.json --out artifacts/offline
```
新增runner中断续跑、错误计数、gold不透传、HTML注入、安全路径、全历史包含assistant/tool等测试。只允许卡7处理集成冲突。
依赖：卡1至卡6；先写假适配器契约测试，最后接真实实现。

## 卡8｜交付、治理、CI与可选deb
独占：README.md；CONTRIBUTING.md；SECURITY.md；CITATION.cff；.github/；packaging/；tools/build_deb.sh；tools/check_release.py；docs/作品介绍.md；docs/submission/；tests/test_release_v2.py。

要求：README提供离线一键体验与显式--live评测两条路径；声明零第三方依赖仅指核心运行时。保留木兰PSL-2代码许可证；第三方数据/系统许可证独立，不将其重许可为木兰。自建数据许可由维护者明确签收，卡8只能检查，不能修改卡2数据目录。

CI默认只跑离线，真实付费调用手动启用；不向fork PR暴露secret，不把未经审查PR交给可访问凭据的自托管runner。记录实际CI日志，而不仅截图workflow文件。补贡献指南、数据纠错/回归用例模板、版本规则、结果提交manifest、合成数据声明、AI辅助开发披露、安全边界。网站仅使用现有静态HTML，不新增账号/数据库。

若核心P0均通过，限时制作Architecture: all、Depends: python3的deb；具体路径/最低Python版本由实际实现核验。脚本不下载模型、不自动调用API、不写用户HOME、不安装系统级长期服务。安装、运行、卸载均在openKylin验证；不上架软件商店也可交付本地deb。未能实测则不打已适配标记。

验收：
```bash
python -m unittest discover -s tests -p 'test_release_v2.py' -v
python tools/check_release.py --root .
bash tools/build_deb.sh
# 在openKylin测试机、显式同意安装后执行：
sudo dpkg -i dist/memobench_0.2.0_all.deb
memobench-v2 --help
```
上述包名/版本由本轮发布合同冻结，不能冒充现有版本。check_release检查必需文件、数据/报告哈希、无占位结果、受控目录无明文凭据；简单扫描不能宣称已证明全历史无secret。最终人工检查PDF、连续录屏、仓库匿名可访问性、清洁克隆重跑、邮件材料一致和截止时区。
依赖：可并行写文档框架；最终材料只引用卡7实际落盘结果；deb为P1，不阻塞必交PDF/视频。

## 人工40小时预算与停止规则
协议与环境预检5h；数据审核6h；评分与校准5h；真实接入及文件闭环5h；实验5h；报告/复现/可选deb3h；PDF/视频/提交7h；故障储备4h，合计40h。这是维护者时间，不能把八个代理的并行编码时间相加后当作人的可用时间。

若进度落后，依次取消：在线排行榜、MCP包装、多语种扩展、额外mem0、第三模型、大长度全矩阵、deb。不得取消：实际openKylin环境、两款真实智能体接入的努力及真实状态披露、评分反例、数据证据审核、原始结果、PDF和视频。如两款智能体无法完成，应明确报告未满足项，不能靠改名掩盖。
