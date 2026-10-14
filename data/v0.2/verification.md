# 本地离线验收记录

2026-10-14，本工作树实际执行，未联网：

- `python3 -m unittest discover -s tests -p 'test_data_v2.py' -v`：14项，OK（2.796s）。
- `python3 tools/build_dataset_v2.py --validate-only --dataset data/v0.2`：退出0，validation=ok，release_status=pending_review，n_story=18，formal_test_n_query=0。
- `python3 -m unittest discover tests`：60项，OK（3.002s），包括已有测试。

只说明代码、冻结协议、离线数据一致性和门禁检查通过。没有人工批准、API结果、openKylin适配或真实智能体成绩。
当前正式test为空。距离60故事目标还差42个独立故事，全部现有故事仍需人工签收。
已有12故事配对规模样本；只有2个测试候选和1个开发故事直接包含文件动作真值，不声称已完成12个真实文件任务。
仓库忽略data目录，需集成者显式纳入data/v0.2；本卡未修改.gitignore、未git commit。
