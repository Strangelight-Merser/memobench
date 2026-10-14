# 本次离线验收记录

日期：2026-10-14。运行环境以 local-env.json 的实际探测为准。

| 验收 | 实际结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_sandbox_v2.py' -v` | 17项通过 |
| `python3 -m unittest discover tests` | 63项通过，包含原有测试 |
| `python3 tools/probe_openkylin.py --out docs/openkylin/local-env.json` | 退出0；openKylin NOT_VERIFIED；acceptance NOT_VERIFIED |
| `git diff --check` | 无错误 |

环境为 Darwin arm64 / Python 3.13.12，未找到 dpkg；没有调用付费或联网 API。
探测输出位置改为本卡独占目录，没有创建任务卡示例中的 artifacts 路径。

未满足项：

- openKylin 虚拟机及两款真实 agent 的文件/生命周期实测：NOT_VERIFIED。
- 外部权限隔离后端与 gold 不可读实证：blocked，当前文件工具不能替代进程沙箱。
- 卡2既有12故事组装：blocked（本分支无卡2数据）；当前0/12，人工审核 pending_review。
- DeepSeek 等真实 API：blocked，当前无凭据，离线测试不依赖它。

人工与集成步骤见 README.md。以上单元测试结果不能用于真实智能体排名、平台适配声明或物理擦除声明。
未执行 git commit；原有源码、原有测试及其他任务卡文件未修改。
