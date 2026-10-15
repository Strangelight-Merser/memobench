# openKylin 虚拟机操作通道

2026-10-14（America/Chicago；运行证据使用 UTC）。虚拟机为 `openKylin-MemoBench`，UTM UUID `F0FB2E54-B2EB-4BAF-91B4-43D00C67E89E`。实际系统 openKylin 2.0 SP2 / aarch64 / Linux 6.6.0-25-generic。

## 已验收的入口

在 `/Users/huaiyi/Documents/oschina` 执行：

```sh
ssh -F .local-vm/ssh_config memobench-vm
```

- UTM 模拟 VLAN：客户机 `10.0.2.15:22` → 主机 `127.0.0.1:2222`，不监听局域网地址。
- 仅允许 `mb` 公钥登录，禁用 SSH 密码登录和 root 登录。
- 客户机服务 `memobench-ssh.service` 已启动并设为开机启动；实际重启后重新 SSH 登录成功，服务为 active。
- 主机公钥指纹经串口与 SSH 双向核对：`SHA256:jV/N556tz7/4jPtp8YxXiC0nGaeCiSWxZ1VYMGkRLgg`。
- 专用私钥与 SSH 配置保存在仓库外的 `../.local-vm/`，不应加入源码包。私钥权限 0600，目录 0700。

## 修复依据

原桥接网络在当前 Wi-Fi 下无法获得 DHCP 地址。改为模拟 VLAN 后取得 `10.0.2.15`，实际访问 PyPI 返回 HTTP 200，openKylin 官方源软件下载成功。

原 `openssh-server` 被系统 apt 包装器安装在 KARE 环境；原服务的 `ExecStartPre=/usr/sbin/sshd -t` 指向不存在的文件。系统 `/usr` 为只读挂载。本次从系统已配置的官方 apt 源下载 `openssh-server` 和 `openssh-sftp-server`（`1:9.6p1-ok6`），解包到 `/opt/memobench/openssh`，复用已存在的系统库；未修改只读分区。

运行配置位于 `/etc/memobench-ssh/sshd_config`，主机密钥在同目录，systemd 单元位于 `/etc/systemd/system/memobench-ssh.service`。原 KARE 安装保留，未作为新服务的执行路径。

9p 设备虽然存在，但运行内核没有 `9p` 文件系统模块，因此共享目录没有挂载成功。项目中的历史 `vmshare/runner.sh` 未启动。文件传输改用 SCP/SFTP，不依赖轮询执行脚本。

## 诊断

```sh
ssh -F .local-vm/ssh_config memobench-vm 'systemctl status memobench-ssh --no-pager'
/Applications/UTM.app/Contents/MacOS/utmctl status openKylin-MemoBench
/Applications/UTM.app/Contents/MacOS/utmctl attach openKylin-MemoBench
```

当前 UTM 的 `attach` 仅返回串口设备路径，不直接提供交互终端。本次串口设备为 `/dev/ttys000`，重启后应重新查询。串口登录及 sudo 使用现有虚拟机账户，密码不保存在项目中。

真实智能体版本及接入验收见 [native VM 记录](../integrations/NATIVE_VM.md)。这份记录只证明操作通道，不等同于正式数据集、软件商店包或比赛材料验收。
