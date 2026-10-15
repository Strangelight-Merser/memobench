# 分阶段协议真实执行结果

两产品均完成原样完整案例：各80条观察、两会话、最终1次query。观察阶段任务目录保持为空，query前baseline为空，最终原生直接write创建 `markers/ready.txt`，内容精确为5字节 `READY`（无换行），严格task审计通过，cleanup ready且namespace closed。没有改题、清除提前文件、伪造记忆、裁剪输入、放宽评分或自动重跑旧版本。

- Kylin：`cli-final/run-kylin/`，桥版本66428d，原生completion execution_scope补丁已启用。80观察全部task_workspace_unchanged=true，81轮profile_completed=true，最终task passed、进程exit0、两会话正常结束。原始namespace在 `cli-final/raw-kylin/`。
- OpenClaw：`cli-openclaw-direct-schema/run-openclaw/`，桥版本d1e298，仅新增原生tools.toolSearch=false/codeMode=false。80观察全部task_workspace_unchanged=true，最终task passed、进程exit0、两会话正常结束。原始namespace在 `cli-openclaw-direct-schema/raw-openclaw/`。

两个版本的函数/阶段与审计实现相同，后一版本仅修改OpenClaw原生配置；没有为了桥hash变化重跑已通过的Kylin80条观察。旧664桥完整快照在 `cli-final/bridge-source.py`。两个运行结束均复核桥及两原生补丁文件摘要没有漂移。

关键修复依据：observe是记忆摄入，task workspace只读而native memory/profile仍可写；query恢复任务写入且沿用原生session。OpenClaw原生agent workspace与任务cwd分离，AGENTS系统阶段说明独立于原样用户文本。Kylin原生完成评审接收可信ephemeral execution_scope，不把观察里延期的动作误当本轮任务；scope不能单独证明completed。OpenClaw固定工具原生schema直接暴露，避免catalog分发器缺参；没有新增wrapper兼容审计，失败write仍闭锁。

旧失败全部保留：首轮Kylin精确回答多句号、下一轮Kylin完成评审忽略scope，以及旧OpenClaw wrapper缺参失败及审计unsupported，不被新成功覆盖或追认。

本阶段实际产品调用合计295：首轮14、格式修订15、原生review修复9、双产品完整CLI162、direct配置probe/smoke14、最终OpenClaw完整CLI81。供应商内部请求次数、费用未知；没有批跑94variants或发布排名。

全套254项通过见 `direct-tools-revision/tests-all.log`，VM原生8项completion scope测试与完整当前源码清单见 `native-review-revision/deployment.json`。本地运行结果摘要分别见两个CLI目录的 `execution-receipt.json`；模型原始Prediction与自然语言slot score均保持原值，score pending_review并未伪造为通过。任务字节验收与语义评分分开报告，主代理另做独立证据复算。
