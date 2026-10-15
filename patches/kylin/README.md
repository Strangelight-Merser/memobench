# Kylin 原生画像 DeepSeek 请求修复

基线为官方 `https://gitee.com/openkylin/agent-runtime.git` 的 `246652c0fdb687953ef8ef25973081bf1298f0c6`。本地运行版本 = 此基线 + `profile-deepseek-bounded.patch` + `completion-output-contract.patch` + `profile-lifecycle-guidance.patch`；没有宣称为上游已发布版本。

画像补丁只修改 `agent/user_profile/extractors.py`。当实际 client 的服务域名是 `api.deepseek.com` 时，画像预检和 JSON 提取显式使用同模型的非推理模式，通过 SDK 原始 HTTP 流逐块检查 60 秒累计时限，单次 I/O timeout 15 秒，提取最多 4096 tokens，预检仍为一个 token。JSON 达到长度上限时报告失败，不解析成成功。未修改画像 schema、证据校验、记忆工具、存储加密、会话持久化或画像注入机制。

DeepSeek 当前默认启用推理；原生一个 token 的预检可能只消耗推理预算，导致正文为空，原生提取则未设置单独的输出长度与超时。官方依据：[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)、[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。这解释了缺少请求边界的问题；此前单次 300 秒等待没有响应体，不能据此断言服务端具体在执行哪一步。

在固定基线源码根目录应用并运行测试：

```sh
git apply --check /absolute/path/to/profile-deepseek-bounded.patch
git apply /absolute/path/to/profile-deepseek-bounded.patch
git apply --check /absolute/path/to/completion-output-contract.patch
git apply /absolute/path/to/completion-output-contract.patch
git apply --check /absolute/path/to/profile-lifecycle-guidance.patch
git apply /absolute/path/to/profile-lifecycle-guidance.patch
cp /absolute/path/to/test_profile_deepseek_bounded.py tests/agent/
cp /absolute/path/to/test_profile_lifecycle_guidance.py tests/agent/
scripts/run_tests.sh tests/agent/test_user_profile_runtime.py tests/agent/test_user_profile_cli.py tests/agent/test_profile_deepseek_bounded.py
```

现有上游测试文件保持原样。新增测试覆盖参数实际传递、预检的一 token 正文预算、截断/非法/空 JSON 不计成功、其他服务不收到 DeepSeek 参数。该 DeepSeek 画像请求关闭 SDK 内部重试，由原生画像层最多尝试两次。原始 HTTP 流不改变模型的非 SSE 请求：检查累计 60 秒时限，静默读取最多 15 秒，因此可能在截止点后最多等待一个 I/O 超时才退出；桥接仍保留 300 秒整进程硬期限。

客户机已部署路径：`~/memobench-native/agent-runtime/agent/user_profile/extractors.py`。主机 `/tmp/memobench-agent-runtime` 为本次源码工作副本，补丁和测试保存在项目中以便复现。


`completion-output-contract.patch` 修改原生完成评审提示词，要求遵守当前用户的明确输出格式。画像修复后的 004 轮检索正确却附带来源说明，被旧评审误判完成。此补丁让执行智能体自行返回符合要求的答案；桥接不截取代号、不重写回答、不放宽精确匹配。补丁不含测试代号、答案或数据集内容。真实评审对照检查已保存：多余说明 → continue；仅代号 → completed。

验收脚本现在为 Kylin 执行九项检查：原五项保持不变，另加每轮画像收尾、加密画像持久化、原生新会话提示词载入、昵称跨会话精确回答。只读画像检查调用上游 `agent.user_profile.inspection.load_profile`，不导出加密密钥。提示词片段来自上游 `state.db` 的实际 system_prompt；评测器不向产品填充画像或答案。

`profile-lifecycle-guidance.patch` 修复 005 轮实测暴露的生命周期误解：智能体反复查找旧 USER.md，耗尽预算后，原生退出提取器实际成功保存昵称。补丁在原生画像运行时存在时说明自动提取时机、memory 工具只负责检索，并要求不为保存偏好查找或改写内部文件。不开画像时不会宣称启用；不虚构持久化完成，不改变真实保存实现。

006 轮的 py-spy 栈证明等待发生在 HTTP 响应体接收。DeepSeek 官方说明排队期间会持续发送空行保活，因此仅设置 idle timeout 不能限制总等待。最终补丁在 SDK 原始响应流中检查累计时限、按上下文管理器关闭响应，用 SDK ChatCompletion 类型解析完整响应，再走原生画像校验与存储；超时和截断不保存为成功。详见 [官方保活机制](https://api-docs.deepseek.com/quick_start/rate_limit/)。
