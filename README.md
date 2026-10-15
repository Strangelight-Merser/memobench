# MemoBench v2

当前内部数据已完成独立 AI 审核与主复核，无需用户填写审核表：59 故事通过、青禾 1 故事排除，内部 test 为47故事/94改写。默认 native recipe 已切换到 `data/v0.2-ai-reviewed` + `internal_evaluation`；[当前审核与内部运行说明](docs/integrations/ai-review-20261015/ENGINEERING.md)。公开数据许可另行处理，不阻塞已授权内部使用。

**面向 openKylin 智能体的证据驱动记忆回归评测工具。** 检查跨会话信息是否被正确用于后续回答与文件任务，保留输入、输出、评分理由和版本证据，服务开发者复现与定位回归。

原始 `data/v0.2` 候选快照仍保留 `pending_review`：60 个合成候选故事、120 个问答，原目录正式测试集为 0，历史许可状态为 `pending_maintainer_signoff`。当前内部审核结果在上述新目录，尚未开展正式产品比较批跑。openKylin 操作通道和两款真实智能体接入已实跑：当前桥的 OpenClaw 6 项、Kylin 10 项完整接入检查均通过；两产品各 80 条观察、两会话和最终文件创建的真实案例通过严格验收，原生记忆与画像保持启用，原始失败证据保留。见 [当前验收与原始证据](docs/integrations/phase-protocol-20261015/README.md)。离线 v2 使用 fixture，只验证执行与记录链路，不发布排名。详见 [数据卡](docs/data-card-v0.2.md)、[接入状态](docs/integrations/README.md)、[环境验证](docs/openkylin/VALIDATION.md)。

核心运行时仅使用 Python 标准库。最低代码要求 Python 3.9（包括 `Path.is_relative_to`）；当前机器验证版本见 [验收记录](docs/submission/VALIDATION.md)。外部智能体、模型服务和可选 SDK 有独立依赖与许可，不包含在“零第三方依赖”声明内。

## 离线一键体验

在仓库根目录执行，无需密钥、模型下载或联网。输出目录须是新的目录；v2 复用完整旧运行时显式加 `--resume`。

```sh
# legacy：模板 + 规则读取器诊断
python3 -m memobench.cli run --distract 6 --out /tmp/memobench-legacy
# v2：校验固定候选数据，然后运行开发集 fixture
python3 -m memobench.cli_v2 validate --dataset data/v0.2
python3 -m memobench.cli_v2 run --config configs/experiments/offline.json --out /tmp/memobench-v2-offline
# 打开各输出目录的 report.html；也可重新生成 v2 报告
python3 -m memobench.cli_v2 report --run /tmp/memobench-v2-offline --out /tmp/memobench-v2-offline/report.html
python3 -m unittest discover tests
python3 tools/check_release.py --root .
```

`offline.json` 是不能执行文件工具的 echo fixture：当前生成 24 个 case 的报告，4 个文件任务明确拒绝，退出码为 2（`completed_with_errors`），不是程序崩溃，也不是文件任务通过。CI 精确检查这 4 个拒绝原因；其他错误仍失败。

对原始 `data/v0.2` 的 validate 退出 0 仅表示结构与门禁验证通过，仍保留 `pending_review`。以下为历史离线 fixture 验证口径。v2 运行保留 `manifest.json`、`hashes.json`、`run.json`、逐 case 记录、`summary.json` 和静态 HTML。echo fixture 不理解自然语言；分数不能解释为记忆模型性能。本次实跑为12故事、24个case，评分均待复核。报告还列出卡2/卡5文件动作、卡3/卡5遗忘政策和审核状态的接口差异，文件任务未验收；仅卡7负责后续集成，详见 [实际报告](docs/submission/evidence/offline/report.html)。

## 显式在线路径

示例中的 SSH 配置路径需替换为自己的配置；不随源码提供作者的私钥或 VM 配置。历史运行证据中的绝对路径仅表示当时环境，不是本机运行要求。当前可交付性、源码版本与原始证据的区别见 [交付说明](docs/delivery/README.md)。

先按 [适配说明](docs/integrations/README.md) 与 [环境说明](docs/openkylin/README.md) 核实版本、会话语义及权限隔离，在专用账户或 VM 中操作。密钥通过配置指定的环境变量提供，不写入配置、命令行或报告。LLM 参数和预算见 [配置说明](configs/experiments/README.md)。

```sh
python3 tools/probe_openkylin.py --out /tmp/memobench-openkylin-env.json
python3 tools/probe_agents.py --config configs/adapters/native.json --out /tmp/memobench-agent-probe.json --live
python3 tools/prepare_native_run.py --ssh-config /path/to/your/ssh_config \
  --acceptance kylin=docs/integrations/phase-protocol-20261015/direct-tools-revision/probe-kylin/probe.json \
  --acceptance openclaw=docs/integrations/phase-protocol-20261015/direct-tools-revision/probe-openclaw/probe.json \
  --out /tmp/memobench-native-plan
```

**`native.json` 是准备 recipe；先生成 plan 和每产品配置。内部数据审核与当前桥版本的完整接入证据均已通过门禁，最新离线准备 blockers 为空。** 当前真实运行及协议修复见 [完整接入与真实验收记录](docs/integrations/phase-protocol-20261015/README.md)。观察期任务目录只读、原生记忆可写，最终查询才执行文件任务；两产品选定完整案例均通过，原负结果保留，不据此发布排名。 [准备入口](docs/integrations/native-preparation-20261015/ENGINEERING.md) 自动计算哈希并给出正式运行命令，不联网、不代签人审。 已可单独运行的真实 VM 接入入口见 [NATIVE_VM.md](docs/integrations/NATIVE_VM.md)。 以上为显式验收入口，不是可用性承诺。在线调用可能产生费用，不能在未审查 PR 中自动运行。旧 CLI 的 `--reader llm` 没有 v2 的 `--live` 门禁，本项目离线说明和 CI 均不使用该入口。

## 三区不混榜

| 区域 | 对象与解释边界 |
|---|---|
| Controlled / v1 legacy | 模板、RuleReader、自制策略；仅用于受控诊断与实现回归 |
| Component / v2 | 自然语言历史、记忆组件、固定公共 LLM Reader；当前离线 echo-fixture 只是管线测试 |
| Native Agent / v2 | 智能体自己的回答与工具行为；不允许公共 Reader 代答后称为原生结果 |

online 与 replay 还须分区；fixture 不进入真实榜。底模不同只能比较整体系统，不能把差值归因于记忆算法。同故事改写不算独立样本；未知用量和未测指标是 null/未测，不是零。字符数不是 token，也不是费用。遗忘输出测试不证明物理擦除。

旧版 [真实归档](docs/experiments/distract-6/summary.json) 中，规则读取器下 full_context、hybrid、session_summary 为 100%，profile_store 83.33%，bm25_rag 75%，sliding_window 37.50%；这不证明自然语言或真实智能体效果。原分布“始终拒答”基线为 **33.33%**，旧子串评分存在否定、字段互换等误判，详见 [作品介绍](docs/作品介绍.md)。

## 接入与交付

v2 接口及 public/private 边界见 [协议合同](docs/spec-v0.2.md)。同一 episode 的新会话保留长期记忆，跨 episode/variant 隔离；gold 不能提供给被测系统。`cwd` 不是权限沙箱。静态 HTML 是现有展示入口，不增加账号或数据库。

- [作品介绍：10 页内容结构](docs/作品介绍.md)（尚非最终 PDF）
- [提交清单与邮件模板](docs/submission/CHECKLIST.md)、[3 分钟视频脚本](docs/submission/VIDEO.md)、[10/29 路演与答辩](docs/submission/ROADSHOW.md)
- [贡献、版本与结果提交](CONTRIBUTING.md)、[安全边界](SECURITY.md)、[引用信息](CITATION.cff)
- [离线 CI](.github/workflows/ci.yml)：配置入库不等于远端运行成功，实际日志状态见验收记录。
- [可选 deb](packaging/README.md)：候选合同版本 `0.2.0`，`memobench-v2` 指向 `memobench.cli_v2`。legacy 模块版本仍为 `0.1.0`，两者分别披露。未完成 openKylin 安装、运行、卸载，不标记已适配。

代码沿用 [MulanPSL-2.0](LICENSE)。自建数据公开再分发须维护者单独确认许可；第三方数据和系统保留各自许可，不重许可为木兰。数据与代码包含 AI 辅助开发；当前内部数据已完成明确标识的独立 AI 审核与主复核，不宣称人工签收或未见留出。

[2026-10-15 远端文件审计与审批闭环](docs/integrations/native-audit-20261015/ENGINEERING.md)：两产品各一次真实合成开发文件任务通过；该历史记录之后，内部数据已完成上述 AI 审核，公开许可仍未授予，未产生正式比较成绩。
