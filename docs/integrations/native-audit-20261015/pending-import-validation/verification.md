# 本地离线验收记录

2026-10-14，本工作树实际执行；未使用外网或生成 API：

- `python3 -m unittest discover tests`：159项，OK。
- `python3 tools/build_dataset_v2.py --validate-only --dataset data/v0.2`：退出0，validation=ok，release_status=pending_review，n_story=60，formal_test_n_query=0。
- 审核页内联 JavaScript 提取至临时文件后，`node --check` 通过（仅开发验收；Python 核心和交付页不依赖 Node）。
- 单元测试核对审核页嵌入的60个源故事与源摘要、12个三档配对故事、脚本数据转义和无外部加载代码。
- 浏览器视觉检查未完成：IAB 不可用，Chrome 安全策略禁止打开本地 file:// 页面。未绕过此限制；尚未实测页面布局、勾选交互或浏览器下载。

数据数量为60故事/120主要问答；每项官方能力2开发/8测试候选，共12开发/48测试。
原18个故事和原12故事的三档配对JSONL保持不变，新增42条源记录及42条待审记录。
全部60条审核状态仍为pending_review，正式test为空。拒收清单为空表示尚无人签收或拒收，不能解读为审核通过。

仅说明代码、冻结协议、离线数据一致性和门禁检查通过。没有人工批准、API结果、openKylin适配或真实智能体成绩。
7个测试候选和2个开发故事直接包含文件动作真值；没有执行这些任务，不声称完成12个真实文件任务。
仅修改任务授权路径，未修改协议、runner或其他卡文件；未git commit。
