# 人工审阅清单

当前全部 pending_review。review.jsonl 一行对应一个故事，附源SHA256与证据ID。
审阅者须为实际执行检查的人；不得填虚构姓名、时间或让构建程序自动批准。

1. 对照 sources.jsonl 的全部事件、targets和两种queries，逐条核对真值；确认unknown/conflict/forgotten语义。
2. 在 candidates.jsonl 根据story_id找到两种表述，沿 Gold.evidence 读取公开观察，核对每条事件均有支持、无额外暗示。
3. 核对同事/本人、设备/项目、指代、版本和路径大小写；不能把架构当偏好，不凭机器昵称猜架构。
4. 边界、冲突、遗忘故事全部审核；遗忘检查新输出和新文件的禁披露政策，同时保留无关事实。
5. 检查开发/测试没有相同或近重复情节模板；两改写不可拆分，三档长度不可当新增故事。
6. 审核三个配对版本的噪声没有引入事实或指令，确认同一核心证据、问题和gold。
7. 文件任务核对最终路径、逐字模板及内容hash。运行和操作日志由卡5提供；本卡未实测文件任务。
8. 通过后在review.jsonl填 status=accepted、reviewer、带时区reviewed_at，两个checked字段设true；保留正确source_sha256。
   拒收则status=rejected并填写可复核的reason；不改掉原始证据，不以模型答错为拒收理由。
9. 运行构建命令更新固定JSONL和manifest，再运行validate-only。任何源修改导致摘要变化均需重新审阅。
10. 维护者核对总计60账本与问题、两种等义表述及开发测试模板独立性，签收数据许可，最后决定是否正式发布。

两checked字段：ledger_query_checked表示账本、问题一致；all_variants_checked表示两种表述和配对负载均检查。
当前采用全量签收门禁，高于其他样本至少25%表面审阅的最低要求。
正式test为空时不能发布排行榜。JSON签收记录只能记录人的声明，不能在技术上证明审阅真实发生。

可用 docs/review/data-review.html 逐故事审阅（从仓库根目录进入 docs/review/data-review.html）。
页面导出 records 数组与源摘要，须人工核对后按行合入 review.jsonl；页面不自动写回。
通过/拒收均填写具体原因，不允许 agent 代签。关闭页面前导出，当前页内存状态不会自动保存。
