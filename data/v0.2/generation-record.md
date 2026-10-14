# 生成记录

生成日期：2026-10-14。方式：离线编写事件账本与成对文本，AI辅助合成，未由人工签收。
没有原始在线LLM响应；未调用生成服务或真实API。降级来源标记为 authored_synthetic_ai_assisted，
不可将其描述为已经人工审核的真人对话。DeepSeek凭据不可用：blocked。

实现：memobench/data_v2.py；入口：tools/build_dataset_v2.py；随机种子42。
冻结源：sources.jsonl。JSONL采用UTF-8、sort_keys=True、紧凑分隔符、每记录一个LF。
manifest.json保存实际文件摘要；相同源、审阅清单与种子重建应字节一致。
构建不覆盖审阅记录。没有模型实测分数、模型调用成本或openKylin实测数据。

当前18故事/36主要问答，12测试候选故事另提供三档配对负载。
60故事目标尚缺42故事；正式test当前0条。不能通过批量改写充当独立故事补齐。
数据许可等待维护者确认；openKylin为NOT_VERIFIED。
