# 工程交付候选

本目录记录交付审计后的修复；正式比赛提交还需要 PDF、真实桌面演示视频和可访问的远端仓库，本地压缩包不冒充这些材料。

当前源码包括独立 AI 审核数据、原生 VM 适配器、补丁和测试。自建合成数据已获维护者明确授权，以 [CC BY 4.0](../../data/LICENSE.md) 公开。accepted_internal 为冻结的质量审核快照，不再限制当前公开再分发。原始材料与失败证据不改写。

## 文件与复现

交付生成器 `python3 tools/build_delivery.py --out /新的输出目录` 从固定 Git HEAD 读取，拒绝脏工作区，不使用旧的 Pro 审查包。输出一个 memobench-complete.zip 与 SHA-256 清单。该 ZIP 包含全部源码、数据和原始证据，单独解压即可运行完整离线测试。

完整包不含私钥、provider.json、VM 磁盘或 Python 环境。原始证据保留历史绝对路径和私网地址以维持原始字节与哈希；这些是环境元数据，不是可运行配置。历史机器路径与私网地址按原样保留，避免破坏证据摘要；它们不构成凭据。源代码运行入口需使用自己的 SSH 配置、VM 与模型凭据。

```sh
unzip memobench-complete.zip -d check
cd check/memobench
python3 -m unittest discover tests
python3 -m memobench.cli_v2 validate --dataset data/v0.2
python3 -m memobench.cli_v2 validate --dataset data/v0.2-ai-reviewed
python3 -m memobench.cli_v2 run --config configs/experiments/offline.json --out /tmp/memobench-check-offline
python3 tools/check_release.py --root .
```

输出路径必须尚不存在。离线验证不调用模型。`offline.json` 会生成 24 个 case 的报告，并因 fixture 不支持真实文件工具而明确拒绝 4 个任务，退出码为 2；CI 检查这些精确拒绝原因，不将其当作任务通过。release 的工程检查通过与正式公开发布 ready 分别报告：语义裁判校准、远端 CI 与 PDF/视频尚未完成，不将其静默视为通过。

## 便携化与历史真实验收

`tools/native_vm_product.py` 的 Mac 个人路径缺失断言改为整个 `/Users` 树不可见；真实 private-canary 与 provider 隔离检查保持。两产品在真实 VM 上的无模型挂载隔离检查通过，见 [portability.json](portability.json)。已验证在线版本原字节保存在 `verified-native-bridge.py`，随完整包保留。当前便携源码与历史线上版本摘要不同，不能混称同一版本；当前 VM 部署未替换，新机器应重新执行完整接入 probe。

本次不为路径清理重跑付费长序列、不修改原评分，不删除任何失败记录。工程验收原始结论见 [完整真实任务验收](../integrations/phase-protocol-20261015/README.md)。
