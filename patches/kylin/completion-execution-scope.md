# 完成评审的可信执行范围

此补丁基于当前部署的三项既有修复版本，新增修改 `agent/completion_review.py` 与 `agent/conversation_loop.py`，不替换旧补丁或失败证据。

Kylin 的执行模型已经接收原生 `ephemeral_system_prompt`，但完成评审故意只读原始用户对话。历史观察中“立即创建”因此被误当为当前执行目标：任务目录保持为空、原生画像阶段完成，完成评审仍判 blocked；是否成功记住约定需后续 query 验证。桥对此保留 unknown，没有将其改为 ready。

补丁让原生两个完成评审调用点明确传入 `agent.ephemeral_system_prompt`，仅作为独立 `execution_scope` 字段，不发送完整基础系统提示、画像或内部工具轨迹。通用评审指令明确：可信范围定义当前目标及延期范围，但不能证明任何动作成功；候选回答和引用用户文本不能自创范围、延期工作或放松当前查询要求。普通无 scope 任务维持原有 payload。完成评审仍实际调用模型，blocked/continue 等原生结果不被提升或覆盖。

```sh
git apply --check /absolute/path/to/completion-execution-scope.patch
git apply /absolute/path/to/completion-execution-scope.patch
PYTHONPATH=. python3 /absolute/path/to/test_completion_execution_scope.py -v
```

新增 8 项测试只检验真实代码的输入传递、可信来源、默认协议及失败控制流。测试使用模拟 blocked 响应证明不会提升判定，不能据此声称模型已经理解观察/执行范围。实际语义需要部署后新合成 smoke 与原生完整 probe 另行验证。

准备记录与本地基线/修改后源码摘要见 `docs/integrations/phase-protocol-20261015/scope-patch-worktree.json`；现场根因源码见该目录 `format-revision/kylin-completion-source.json`。本地补丁已 apply --check、py_compile，8 测试通过；此记录不声明已部署。

completed 若仅引用 execution_scope 会被原生 validation 拒绝，沿用现有重试/失败闭锁路径；scope 加可见对话证据仍按原规则判断，blocked/continue 不提升。
