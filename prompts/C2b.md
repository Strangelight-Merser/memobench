你在为 MemoBench 扩充 v2 数据。先阅读 docs/plan-v2/AGENT_TASKS.md 的“卡2”、docs/data-card-v0.2.md、memobench/data_v2.py、tools/build_dataset_v2.py、data/v0.2/ 现有内容。
任务：把候选故事从 18 个补到 60 个（每项官方能力 10 个：长期保持、记忆调用、动态更新、相近区分、边界识别、任务复用；按故事隔离划分 12 开发 / 48 测试），每故事两种等义表达。遵守卡2全部真值规则（设备架构是观察事实；KARE 不是包管理器；不可推断项不要标答案；主体区分同事/本人/不同设备/不同项目等）。全部新故事保持 pending_review，不得自行签收。
独占文件：memobench/data_v2.py、tools/build_dataset_v2.py、data/v0.2/、docs/data-card-v0.2.md、tests/test_data_v2.py。其余只读。标准库；不联网；不 git commit。
另外生成一个人工审核用的静态页 docs/review/data-review.html（只读展示每个故事的事件账本、会话、问题、真值、证据，按故事一屏，带“通过/拒收+原因”勾选并可导出 JSON 到本地下载；纯内联 HTML/JS，无外部依赖）——此文件也归你独占。
验收：python3 -m unittest discover tests 全部通过；python3 tools/build_dataset_v2.py --validate-only --dataset data/v0.2 通过。中文汇报。
