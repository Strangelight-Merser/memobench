# 可选 deb（P1，未适配验收）

候选合同：`memobench_0.2.0_all.deb`，Architecture: all，Depends: python3 (>= 3.9)。legacy模块`__version__`仍为0.1.0，不修改卡外代码来伪装统一版本。

```sh
# 正式路径：P0缺口存在时返回2，停止打包
bash tools/build_deb.sh
# 仅验证包构造的明确本地候选；不表示P0或openKylin通过
bash tools/build_deb.sh --candidate
```

默认输出 `packaging/dist/`（卡8独占路径），可传 `--out /tmp/memobench_0.2.0_all.deb`。包内入口 `/usr/bin/memobench-v2` 使用 `/usr/bin/python3` 调用 `/usr/share/memobench/memobench/cli_v2.py`。包含核心源码与judge提示；数据许可待签收，包不携带数据、配置、gold或实验结果。运行完整评测需从源码仓库根目录使用其中配置与数据；包本身提供CLI，不是独立数据发行版。路径参数按调用者cwd解析。

构建只用标准库生成deb的ar/control/data归档，不依赖dpkg-deb，不下载模型，不调用API，不写HOME，不安装服务或maintainer scripts。最低3.9来自核心使用的标准库API；实际测试版本见submission/VALIDATION.md，CI矩阵不能代替未运行的版本验证。

仅在openKylin专用测试机且用户明确同意安装后执行（本轮未执行）：

```sh
sudo dpkg -i packaging/dist/memobench_0.2.0_all.deb
memobench-v2 --help
# 在仓库根目录，使用新的可写输出目录
memobench-v2 validate --dataset data/v0.2
memobench-v2 run --config configs/experiments/offline.json --out /tmp/memobench-deb-smoke
sudo dpkg -r memobench
# 核对入口/包文件已移除，用户主动指定的实验输出不应被删除
```

保存系统版本、安装/运行/卸载返回码、文件清单与完整日志。现在均为NOT_VERIFIED；没有商店上架声明。正式发布阻塞不能靠候选构建成功取消。
