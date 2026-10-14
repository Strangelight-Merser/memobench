# MemoBench 上传源码复核

审阅日期：2026-10-14。输入：用户上传 oschina.zip。解包快照git HEAD：17a279dfa0ba6d257aa58ad35267483029bb0a8b。

## 验证范围
已在Linux x86_64 / Python 3.13.5环境运行原始单元测试、原始离线CLI和自建反例。没有修改原项目源码。没有调用真实LLM，没有连接mem0，没有在openKylin、KylinBot、Kylin Agent Runtime或OpenClaw上实测；没有验证远程CI实际运行结果。不能将本审计记为上述系统的兼容认证。

已执行：
```bash
python -m unittest discover -s tests -v
python -m memobench.cli run --distract 6 --out <审计输出目录>
```
23个测试全部通过。离线原始数据120题。结果如下：

| 系统 | 原版规则准确率 | 平均记忆上下文字符 |
|---|---:|---:|
| full_context | 100% | 865.59 |
| hybrid | 100% | 34.26 |
| session_summary | 100% | 121.30 |
| profile_store | 83.33% | 70.73 |
| bm25_rag | 75.00% | 78.54 |
| sliding_window | 37.50% | 217.47 |

额外“始终回答不知道”基线为33.33%。这些数字全部属于原版模板+RuleReader协议，不是自然语言/真实智能体排名。比例按原实现定义，bm25_rag的15.83%泄露率以所有120题为分母。

## 已复现的反例

| 反例 | 原实现返回 | 解释 |
|---|---|---|
| gold=UKUI，回答“不是UKUI。” | correct=True | 子串评分不识别否定 |
| 未知城市，回答“不知道，但你住在北京。” | correct=True | 拒答词与无依据断言并存仍通过 |
| 编辑器Vim、浏览器Firefox，回答“编辑器是Firefox，浏览器是Vim。” | correct=True | answers平铺列表丢失字段对应关系 |
| 当前Vim，旧值Emacs，回答“现在是Vim，不再是Emacs。” | correct=False, leaked=True | 符合旧版“出现旧值即泄露”的定义，但混淆正确历史否定与错误复用；属于指标定义需要拆分，不直接等同代码实现错误 |
| generate(n_per_category=1, turns_per_session=40) | ValueError | filler无放回采样容量不足 |
| 同一句先Vim再更正Emacs | profile_store仍返回Vim | 单轮只处理首个匹配；hybrid保留两段，因此不能将此故障同时归给hybrid |
| 相同model/prompt、两个不同base_url | 同一缓存答案 | 模拟磁盘缓存复现，无网络调用；跨服务串缓存 |

## 关键源码定位
- memobench/scorer.py:6-21：全局小写与去空格；答案子串检测；拒答词检测；过期与遗忘合并为forbidden。
- memobench/schema.py:24-39：Case仅有平铺answers和forbidden，缺slot键、证据位置与独立状态账本。
- memobench/reader.py:17-44：导入生成器ATTRS并用同一语法匹配。应称生成器/解析器结构耦合，不应误称直接读取gold。
- memobench/reader.py:69-88：缓存键只有model和prompt；API usage与返回模型信息未落盘。
- memobench/runner.py:14-24：写入与会话结束在计时之外；只测recall+reader；没有完整写入成本。
- memobench/runner.py:28-44：泄露率分母包含全部case；平均字符不是token或存储大小。
- memobench/generator.py:8-21：架构、版本、偏好等语义混为属性；包管理偏好含kare。
- memobench/generator.py:97,111-162：有限filler无放回采样；共享随机流使不同噪声设置改变故事语义，不能当严格配对消融。
- memobench/memory/baselines.py：full_context只保留user角色；profile_store对单个turn只取首匹配；bm25_rag是词法检索，不是所有RAG系统的代表。
- memobench/memory/advanced.py：session_summary是规则抽取摘要；mem0为可选入口，服务配置、SDK版本、异步就绪、成本和清理需进一步验证。

## 对现有文档的公平评价
README已经主动披露模板规则局限、未真实接入openKylin助手、LLM结果待补、字符不是token、行为遗忘不代表物理擦除、session_summary不是LLM摘要、sweep不严格成对。这些是诚实的边界说明，不应描述成项目故意造假。

## 结论
现有代码是可工作的受控合成诊断原型。首要缺口是测量有效性、评分健壮性、真实智能体接入和openKylin可验证任务闭环，而不是再提高自制hybrid的模板分数。保留v1诊断记录，v2另设自然语言与native_agent协议，不混榜、不拿上下文字符缩减直接宣称端到端性能提升。

证据文件同包提供：unit-tests.txt、probes.json、always-abstain.json、reproduced/summary.json、reproduced/results.jsonl、reproduced/report.html、portable_probe.py。
