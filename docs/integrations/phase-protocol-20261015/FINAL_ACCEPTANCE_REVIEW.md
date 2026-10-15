# 最终完整案例独立验收

**结论：两产品均完成并通过选定原始案例的完整任务验收；通用语义评分仍为 pending_review，不能称作正式排名或全基准通过。** 本文仅基于已有真实 raw 离线复核，未调用模型、未改原始数据/评分/原始证据。

选样严格使用 story `e6a7a9059f826b02f8edd920` 与 variant `d012611aa89b90909fcea7b9` 的精确组合，episode `5668053304ca40ac9ef62563`。不能用可跨 story 重复的 variant 单独指认案例。

| 产品 | 完整运行证据 | 桥 SHA-256 | 独立任务验收 |
|---|---|---|---|
| Kylin | cli-final/raw-kylin/2cea8868451a41d7afdc4c52a23a4656.json | 66428d8276ff544a2c24234f619ac586cba8e0e876399884f7e1425a744bf02e | passed |
| OpenClaw | cli-openclaw-direct-schema/raw-openclaw/223c691091f14ffaa424d8cffaeaa15c.json | d1e29805c756dd99aff69d2f4a906f52163d87df274000d64acedc99daaf541d | passed |

这不是同一次或同桥摘要的运行。独立只读比较过两桥源码，差别仅为 OpenClaw 配置 toolSearch=false/codeMode=false；Kylin 执行路径不变，另有新 d1 桥 Kylin 完整工程 probe 通过，故未无因重复其 80 条原始观察。

## 原始输入与阶段

两 case public_input 均与当前原始数据精确一致，单次 attempt，80 个 observe、2 个 begin_session、2 个 end_session、1 个 query，另有 reset/close 各 1。逐条核对原文和公开文本摘要、session 绑定以及独立 phase 策略；原始最终 query 未改写。

两产品所有 observe 的 task workspace before/after 均为空且不变，观察期没有提前创建任务文件。产品原生记忆保持启用，不由桥代写约定；Kylin 原始完整运行 81 个 turn 的 profile_completed 与 completion_review:completed 均成立。OpenClaw 本轮真实工具表面保留原生记忆；完整运行最终 query 工具摘要为 write/read 共 2 调用、0 失败，没有 tool_call 包装。

## 严格文件与调用链

独立审查分别从原始 query native_records 重新运行 native_file_audit，与已保存 audit 完全一致；再将原 Gold、原 Prediction、checkpoint 和 artifacts 传入现有 verify_remote_task，均得到 passed。

两次 query baseline 均为空，query 后首次出现 markers/ready.txt；解码字节均精确为 READY，大小 5，无换行，SHA-256 为 `c2e3ac47f4a325469c1a2d5f117e463ec943c721986d5d9f09ac4540b7d80526`。轨迹包含各自原生直接文件工具成功写入的参数和结果；OpenClaw 为直接 write、path=markers/ready.txt、content=READY、succeeded=true。任务结论依据首次创建字节和原生执行链，不依据 scope 或候选回答自称。

## 完整性与版本

两 namespace 全部操作 completed，cleanup receipts ready、cleanup_error=null、control.closed=true。原始 raw/case 摘要与 PRIMARY_KYLIN_COMPLETE_RUN_REVIEW.json、PRIMARY_OPENCLAW_COMPLETE_RUN_REVIEW.json 一致；OpenClaw 当前桥源码摘要与 d1 原始运行绑定一致，未发现版本漂移。

- Kylin raw SHA-256：3b7d6c13cbecfe5938feadbc8a6df5792a80b831ceedbcbdfa3e0532811527e3；case：393a3ef80ef5c1ab1ec5cdae13f0c28ae6bb24ce38171b2bf538362c2c4fe695。
- OpenClaw raw SHA-256：b50dee9ddccc571fb4ce9f9a10776d2a10e404da9844185e9e88863553dba1ab；case：625f6a1fc9053c07d1942eccdd034be02a2109c429e49ea8abb5a49f23ee274f。

原生工厂和实际工具表面另含 apply_patch/skills_read 等派生工具，不把五项 allowlist 误称最终恰好五个工具。

## 结论边界

两原始 score 均保留 status=pending_review，review_reason 为 blocked: judge_transport_unavailable；规则 task_completed=true，其余通用语义指标仍为 null。本次完成的是原始完整案例的严格 task 验收及相应接入验证，不是补造语义分数、产品全面能力结论或排行榜。

旧无阶段权限导致提前文件的失败、旧 OpenClaw 动态包装遗漏及失败 write 的运行均保留，未被本次成功覆盖或离线追认为通过。新协议、新配置下的成功运行独立记录。
