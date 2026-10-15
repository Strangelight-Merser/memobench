> 本文保留早期验收记录。当前自建数据公开许可为 [CC BY 4.0](../../data/LICENSE.md)，独立 AI 审核数据与最新交付说明见 [交付入口](../delivery/README.md)。下文旧许可和测试集状态仅描述当时快照。

# 卡8离线验收记录

2026-10-14，本机 Python 3.13.12 / Darwin arm64。未联网，未 git commit，仅修改卡8独占路径。测试/CLI输出使用临时目录，保留副本在本目录evidence，未覆盖历史实验。

| 实际命令 | 结果 | 证据 |
|---|---|---|
| `python3 -m unittest discover tests` | 182 tests，OK，23.226秒 | [完整日志](unittest.log) |
| `python3 -m unittest discover -s tests -p test_release_v2.py -v` | 6 tests，OK | [卡8日志](release-tests.log) |
| legacy `run --distract 6` | 退出0 | [运行记录](offline-validation.json)、[报告](evidence/legacy/report.html) |
| v2 `validate --dataset data/v0.2` | 退出0，仍pending_review，正式题数0 | [运行记录](offline-validation.json) |
| v2 `run --config configs/experiments/offline.json` | 退出0，12故事/24case，0执行失败，24条待评分，禁止排名 | [报告](evidence/offline/report.html)、[摘要](evidence/offline/summary.json)、[manifest](evidence/offline/manifest.json) |
| `python3 tools/check_release.py --root .` | 离线检查passed；正式release_status blocked | [检查日志](release-check.json) |
| `bash tools/build_deb.sh` | 退出2，P0阻塞，未按正式路径构建 | [运行记录](offline-validation.json) |
| `bash tools/build_deb.sh --candidate`（指定临时输出） | 退出0；候选包已复制至packaging/dist | [运行记录](offline-validation.json) |

deb测试解析真实ar/control/data归档，检查Architecture/Depends/无服务脚本，并从提取的源码运行v2入口`--help`。测试仅为解包入口验证，不等于dpkg安装成功。默认包版本0.2.0，legacy源码版本仍0.1.0，已分别披露。

数据与已引用报告SHA256见 [evidence-sha256.json](evidence-sha256.json)，check_release逐一比对。复制的v2 manifest保留原始运行时间与代码/数据/评分器哈希；公开输入、回答及case记录在evidence/offline，未篡改为正式结果。离线报告没有可发布的模型能力分数，不能用0执行失败替代正确率。

## 已确认阻塞

- 数据pending_review，数据许可pending_maintainer_signoff，正式测试为空。
- native产品桥与外部权限隔离、真实智能体和openKylin未验证。
- 实际v2 summary列出：卡2 `write_file/content` 与卡5 `create/render` 不匹配；卡3 `literal_disclosure` 与卡5 `canary/retained_text` 不同；卡2 `accepted` 与卡5 `approved` 不同。卡8仅记录，卡7负责集成；不能声称文件任务闭环已通过。
- LLM结果、语义裁判及人工校准待补。当前fixture不入榜。
- 本轮没有远端CI运行日志、匿名访问或干净克隆验证；workflow会保留实际运行日志，但配置本身不证明运行成功。
- 当前作品介绍是10页内容稿，不是已排版并人工复核的PDF；视频是分镜脚本，路演是大纲，均未录制/制作成最终媒介。邮件未发送。
- 未在openKylin安装、运行或卸载deb，未上架软件商店。

`check_release`默认退出0表示工程检查通过，输出仍标正式发布blocked；`--strict`返回2。当前版本显式保留外部证据阻塞，未来只能凭新证据审阅更新，不能删除门禁来获得通过。扫描范围仅受控工作树，不包括git历史及外部服务。
