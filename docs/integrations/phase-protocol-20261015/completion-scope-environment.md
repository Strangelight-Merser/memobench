# 原生 completion scope 离线测试环境

准备阶段在 macOS Darwin arm64、Python 3.13.12 本地运行，8项通过。未在VM运行这组测试，未覆盖VM产品文件，也没有模型调用。临时patched源码与原始本地副本分别为：

- `/var/folders/qh/smby8tjs56s7zrmf7_0klzhc0000gn/T/memobench-execution-scope-886qa71t/agent/`：两个修改后文件，通过 importlib 直接加载被测 completion_review。
- `/tmp/memobench-agent-runtime`：其余原生模块（如 iteration_budget、session_detail_logger、usage_pricing）的实际本地源码，PYTHONPATH引用。

准确命令（cwd为仓库根）：

```sh
KYLIN_SCOPE_PATCH_ROOT=/var/folders/qh/smby8tjs56s7zrmf7_0klzhc0000gn/T/memobench-execution-scope-886qa71t PYTHONPATH=/tmp/memobench-agent-runtime python3 patches/kylin/test_completion_execution_scope.py -v
git -C /tmp/memobench-agent-runtime apply --check /Users/huaiyi/Documents/oschina/memobench/patches/kylin/completion-execution-scope.patch
```

测试包括真实payload和两调用点传递、普通无scope原协议、candidate不能伪造scope、scope-only completed拒绝、mixed可见证据保持原行为、blocked/continue仍非完成，以及mock blocked原生控制流不被提升。mock仅用于控制流测试，未声称验证模型语义。部署后仍须用VM原生.venv运行同8项和py_compile，再进行新Kylin smoke及完整probe。
