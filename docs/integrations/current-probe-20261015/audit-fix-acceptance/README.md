# 审计修复后的真实开发验收

当前部署桥 SHA-256：`6b0ad695c89dc233901eca4561b73a5158db339dcef41e72932394c033da1c81`。部署前版本及回滚备份见 `deployment.json`，已核两端一致并通过 py_compile。

固定范围全部完成：每产品一次完整 probe（共 3 observe + 9 query），另每产品一次全新合成文件 query，总共 **14 次产品调用**，无自动重跑。供应商请求数、费用未知。旧 80 条观察案例没有重跑，原失败和评分保持原样。

两完整 probe 均 passed；两额外文件 query 均 task passed，audit complete=true，cleanup ready，closed=true。两产品原生轨迹都实际读取绝对路径 `/home/mb/case/workspace` 并得到预期目录读取错误，该 read 以 succeeded=false 保留；随后原生直接 write 创建随机新文件，字节与本地摘要一致，再回读成功。没有让失败 read 伪装成功，也未放宽失败 write 门禁。

`kylin/`、`openclaw/` 保存完整 probe 及原始 namespace JSON。`*-file-regression.json` 保存 execute_case 结果、原生回答与本地验收摘要；`*-file-raw-*.json` 保存原始桥导出，包括完整 native_records、query 前后字节、审计绑定和清理状态。`receipt.json` 汇总及记录各证据文件摘要。文件均为新合成开发材料，未读取正式内部数据。

OpenClaw 额外 query 启动后收到将输入写成绝对路径的补充要求，因此其最初公开输入仍写“workspace根目录”；原始轨迹证明模型实际 read 的 arguments.path 已是指定绝对路径。其公开输入以 `public_input_evidence` 从原 native_records 事后提取，明确标记来源。Kylin 启动前已将公开输入写为绝对路径，保存完整 public_input。两者均没有重跑。

这是修复后的有限接入/文件审计开发验收，不是重跑失败评测题、正式比较成绩或未见留出排名。
