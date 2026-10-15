# 独立 AI 审核已完成并接入内部评测

用户不需要再填写 60 条审核表。独立 AI 已审核全部故事，主 AI 逐条复核；接受 59 个、拒收青禾 1 个。新目录 `data/v0.2-ai-reviewed` 已实际导入并验证为 **accepted_internal**：12 个 dev 故事，47 个内部 test 故事、94 个改写 case。原 `data/v0.2`、既有测试和历史审核原件保持原样。

## 当前入口

默认 `configs/experiments/native.json` 已指向新目录，purpose 为 `internal_evaluation`。无需手改哈希或选择公开许可证：

```sh
python3 tools/build_dataset_v2.py --dataset data/v0.2-ai-reviewed --validate-only
python3 tools/prepare_native_run.py --ssh-config ../.local-vm/ssh_config --out /尚不存在的新计划目录
```

本次实际默认计划在 `internal-plan-final/plan.json`。数据审核和内部使用均已通过，**仅缺两产品当前完整接入 probe 原始证据**；没有“等待人工填表/公开许可”的阻塞。已有单文件开发验收不冒充完整跨会话 probe。本批没有调用网络、模型或 VM。

计划为两个产品共 188 cases、15,228 次 observe/query 产品调用，另列 1,128 次生命周期操作、48 次文件证据检查；不是 15,228 次供应商 API 请求。请求数与费用未知，保持 null。没有开始实际批跑，也没有生成假成绩。

## 审核机制与真实身份

- human 0.2 继续是合法的人审格式；新 independent_ai 0.3 明确 AI 身份、独立审阅与不同身份主复核。二者不互相伪装，也不转换旧签名。
- AI 逐条最终结论必须匹配主复核原件；通过项还须独立审阅同意，且主审原件确实检查 gold 和两种表述。不能只改包内 accepted/布尔字段抬为通过。
- 绑定源故事、候选/dev/public/三档配对文件的实际摘要，以及当前生成/评分/审核规则指纹。缺原件、哈希失配、错误引用、同一审核身份、变体改变或原件事后修改均会被拒绝。
- 原件逐字节归档到新包和新数据目录的 `evidence/<sha256>.json`。主复核原件同时绑定独立原件 SHA。没有覆写原始审核文件或冻结旧人审包。

新审核包：`/Users/huaiyi/Documents/oschina/deliverables/memobench-ai-reviewed-20261015/`

审核指纹：`e3260d1a75d09157b4fe8391a881e2ca878ae13166d536a9ae0061c80c5593f5`。

## 内部使用与公开许可分开

`usage-approval.json` 绑定用户本次原文授权、AI 来源核查原件、源文件和生成记录摘要，仅允许 `internal_evaluation_only`。来源是本地离线 AI 辅助创作的虚构合成故事，没有把代码许可证或内部使用授权冒充数据公开许可证。

公开数据许可仍未授予；不替任何人署名，不擅自选择 CC 或 Mulan。它不再阻塞用户已授权的项目内部评测。accepted_internal 不能以 frozen_evaluation 用途运行，也不能被当成公开发布/排名许可。旧 check_release 检查原数据的公开发布限制，与本目录的内部验收结果明确分开。

## 曝光与拒收

两个 AI 审核者均阅读了全部 60 个故事，审核曝光完整记录。已知框架/开发者曝光另列青禾和先前被审批回归借用过结构的 archive_delayed_lookup；不能把这种曝光错误说成已给被测模型训练/调参。本轮审核没有模型训练/调参调用，以前历史不作无依据声明。

所有 AI 审阅材料均不宣称独立未见留出或公开排名。内部用途可以保留框架开发已曝光、语义合法的题目；青禾被排除的原因是 gold 漏掉明确禁止路径、改写等义性待修，不是因为某系统答错。原故事和原 gold 没有被静默改写。

## 验证

新增 7 项测试，包括：两份原件与身份/引用/逐条判定负例、缺失/篡改/变体变化、未查完原件不得提升、内部用途不得伪装公开许可，以及 **AI 包导入 → accepted_internal → 默认同类内部 recipe → prepare → 正式 CLI run/report（mock SSH）** 的完整操作链。

全套 **237 项通过，57.442 秒**，见 `engineering/tests-all.log`；新增结果见 `engineering/ai-tests-final.log`。实际打包/导入日志见 `engineering/package-command.log`、`engineering/import-command.log`。主代理独立复核 `final-review.json` 确认 87 份保护材料未变、源字节一致、青禾排除、原件归档一致及两条开发曝光。

本次没有进一步真实模型调用、推送或发布；下一项实际技术条件是当前完整产品接入证明和执行范围/预算确认，不再要求用户先完成自设的人工审核表。
