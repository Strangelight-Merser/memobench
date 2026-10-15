# Native 实际运行准备入口 · 2026-10-15

接通了“审批导出 → 新副本导入 → 数据验证 → 接入证据验证 → 自动配置/调用计划 → 正式 run”操作路径。本批没有网络请求或模型调用，也没有修改已冻结的人工审核规则或人审包。

## 修复的实际断路

旧 native.json 是 blocked 占位；probe 真实产出 bridge/config 哈希和原始 exports，却没有 dataset_sha256，factory 又要求 probe 内有数据哈希。这样即使人真正签收数据、实际 probe 通过，也无法直接使用报告。

现在产品接入证明与数据审批分别绑定：probe 证明当前产品、桥、配置、隔离和跨会话检查；准备器现场验证已审批数据，并把数据内容哈希写进新 run config。没有补造历史 probe 字段，也没有放宽其必需检查。probe exports 改为相对文件名，factory 以 probe 所在目录解析并限制在该 bundle 内，整个报告目录搬移后仍可核验。

`configs/experiments/native.json` 现在明确为 `native-run-recipe-1` 准备 recipe，不是可运行配置。直接交给 run 会返回 blocked、n_case=0 并提示准备入口；不会联网。runner/报告也按 native、component、offline fixture 区分说明，不再给 native 正式路径写 echo-fixture 或“真实智能体未测”的固定错误提示。

## 操作入口

所有命令从仓库根目录执行。先将实际人审导出与独立许可导入新数据副本；可以分批审阅/导出保存进度，不需要为了技术接入立即完成 60 个故事。完整正式发布的审批口径仍按现有项目规则判断，未擅自删除门禁。

准备配置和 dry plan（纯读取，无 --live、无 transport）：

```sh
python3 tools/prepare_native_run.py \
  --dataset /实际人工签收后的新数据目录 \
  --ssh-config /Users/huaiyi/Documents/oschina/.local-vm/ssh_config \
  --acceptance kylin=/当前Kylin探针目录/probe.json \
  --acceptance openclaw=/当前OpenClaw探针目录/probe.json \
  --out /尚不存在的新准备目录
```

ready 时输出 plan.json、kylin.json、openclaw.json，自动计算所有哈希。plan.json 保存可直接执行的 `python -m memobench.cli_v2 run --config ... --out ... --live` 命令。仍须先确认调用范围和预算，再显式执行；prepare 不会替用户启动它们。

计划分别列出独立故事数、改写 case、产品 observe/query 调用、reset/begin/end/close 生命周期操作、文件 checkpoint/evidence 检查。产品调用数不等于供应商请求数；供应商请求及预计费用未知时为 null。

缺审批、许可、非空 test 或当前原始接入证据时，只生成 blocked 的 plan.json，不生成可运行配置。准备后数据、桥、SSH 配置、报告或原始 exports 变化，实际 run 会重新校验并在创建 transport 前阻断。既有未知写入不重放，native 不能 resume。

完整接入 probe 使用既有 tools/probe_native_vm.py；它独立于正式数据，不需要人工先审完 60 题。它会调用模型，须另行确认范围/预算后使用 --live。本批没有启动探针，也没有用先前两次开发文件 query 冒充完整跨会话接入证明。

## 已实际验证

新增 4 项回归全部使用完全自造数据及明确标记的合成签收/接入证据：

1. 从冻结的 review.html 提取并执行真实 save/export JavaScript（Node，本地 DOM 下载接口为测试替身），得到实际格式的下载 JSON；原字节导入新副本，许可独立验证；accepted 后自动 prepare，再通过真正 cli_v2 run/report 入口走 NativeAdapter 和 mock SSH，原生回答完整保存。prepare 期间 transport 构造为零。
2. pending/缺 probe 不生成任何 run config。
3. 搬移 probe bundle 相对 exports 仍可验证；改 SSH 配置则 blocked。
4. 准备后数据 inventory 改变，正式 run 在 transport 前阻断。

`synthetic-e2e/` 保存第一次完整操作链的实际临时产物；全部数据/签名/产品响应都是测试 fixture，根目录 SYNTHETIC_TEST_ONLY.json 作出明确标识。它的临时绝对路径按原执行证据保留，不是给人使用的正式配置。最终报告修正后的复核见新增测试与最终全套日志。

首次全套 230 项发现 recipe 被旧 CLI 测试看到 error 的回归，日志 tests-final.log 原样保留；修复为明确 blocked，未修改既有测试。原 CLI 6 项和新 E2E 4 项均通过。最终全量结果见 tests-final-confirmed.log。

## 真实剩余条件与人机分工

当前实际准备结果在 current-blocked-plan/plan.json：数据仍 60 pending、许可 pending、正式 test=0，且未提供当前完整产品 probe。没有生成任何正式 run config。

机器已承担结构、源/变体/规则指纹、签收字段、时间、许可绑定、配置哈希、原始 operation 归属与文件字节检查。人需要决定的是语义/证据与改写等义、开发暴露取舍、数据许可、最后的运行范围/预算及语义裁决。无需手填哈希，也不要求用户立即填写 60 张技术表。

当前“所有故事都有明确决策才进入全量发布”是项目自设的发布策略，不是本批核实的赛事强制逐条要求。它与技术接入验收不同：真实文件审计已在两个独立合成开发 case 通过，完整跨会话探针同样可以独立运行。正式发布审批暂作为单列待办，本批不自行降低门槛。

最终确认：230 项测试全部通过（52.619 秒，tests-final-confirmed.log），git diff --check 通过。87 份受保护原始数据/既有测试/补丁/历史证据文件全部未变；人审 context 仍为 4e5672f5a3b0403f506a4be6d08e31ae5d487d45eddbe952ac2e334d936ebb0c。详细机器记录见 final-protection.json。本批网络和模型调用均为 0。
