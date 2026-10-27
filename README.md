# BJUT 有线校园网登录：无界面服务器版

面向通过 `lgn.bjut.edu.cn` 认证的北京工业大学有线校园网。适合无图形界面的 Linux 服务器，以及希望通过终端管理校园网登录的设备。使用 Python 标准库，无需安装 Python 第三方包。

脚本支持保存多个账号、选择当前账号、注销与切换账号。用户级 `systemd` 定时器每两分钟运行一次检查：门户显示在线时直接退出，离线时使用选定账号重新登录。Python 进程只在执行命令或定时检查时运行。

> 适用范围：本项目实现的是旧版 `lgn` 有线门户的 IPv4 登录流程；无线门户及新认证接口没有经过此版本验证。门户页面或响应格式变化时，脚本会在无法判断状态的情况下停止提交凭据。

## 环境要求

- Linux、Python 3.8 或更新版本。
- 当前服务器的网络可以访问 `https://lgn.bjut.edu.cn/`。
- 自动检查需要支持用户级服务的 `systemd`。

## 安装

在需要登录校园网的服务器上，以日常使用的账号执行：

```bash
git clone https://github.com/D-dragon5/bjut-login-server.git ~/bjut-login-server
cd ~/bjut-login-server
python3 manager.py status
```

仓库中的服务文件默认从 `~/bjut-login-server/manager.py` 启动。若克隆到其他目录，请先修改 `systemd/bjut-login.service` 的 `ExecStart` 路径。

安装并启动两分钟定时检查：

```bash
mkdir -p ~/.config/systemd/user
cp systemd/bjut-login.service systemd/bjut-login.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now bjut-login.timer
systemctl --user status bjut-login.timer
```

若要求退出 SSH 会话后以及重启后仍运行用户级定时器，请由管理员执行 `sudo loginctl enable-linger "$USER"`。定时器可以先安装；未添加并选择账号前，检查命令不会尝试登录。

## 账号与登录

在项目目录中运行以下命令。`main`、`second` 都是自定义别名：

```bash
python3 manager.py add main       # 交互输入校园网账号与密码
python3 manager.py add second     # 再保存一个账号
python3 manager.py list           # 查看别名和当前目标；不显示密码
python3 manager.py use main       # 注销当前会话，登录 main，开启自动重登
python3 manager.py use second     # 切换账号并更新自动重登目标
python3 manager.py status         # 查看门户在线状态与自动重登设置
```

`use` 会先关闭自动重登、注销当前门户会话，再登录目标账号。登录得到确认后才重新开启自动重登。门户确认注销与重新认证期间，网络连接会短暂中断；通过 SSH 远程操作时请预留重新连接的条件。

其余命令：

```bash
python3 manager.py logout        # 注销，并关闭自动重登
python3 manager.py disable       # 保留当前会话，仅关闭自动重登
python3 manager.py remove second # 删除保存的账号
python3 manager.py check         # 手动执行一次定时检查
```

自动检查只判断门户是否在线。若另一工具已将当前会话切换为不同账号，在线状态下本脚本不会自动抢占；需要时运行 `use <别名>` 主动切换。

## 运行状态与排查

```bash
systemctl --user list-timers bjut-login.timer
systemctl --user status bjut-login.service
journalctl --user -u bjut-login.service -n 30 --no-pager
```

停止定时检查：`systemctl --user disable --now bjut-login.timer`。再次启用：`systemctl --user enable --now bjut-login.timer`。

如果 `status` 报“门户状态未知”，先确认服务器能访问校园网门户，并检查门户页面是否改版。若认证失败，服务日志会给出错误信息；请检查账号状态后再运行 `use <别名>`。

离线功能检查可在 Linux 上运行 `python3 -m unittest discover -s tests -v`。测试使用模拟门户响应和临时账号文件，不会操作当前校园网会话。

## 凭据保存

账号与密码保存在当前 Linux 用户的 `~/.config/bjut-login/accounts.json` 中，目录权限为 `700`，文件权限为 `600`。文件采用明文 JSON，便于本人在服务器上管理；`add` 通过终端交互输入密码，避免将密码放入命令参数或 shell 历史。该文件位于仓库之外，仓库的 `.gitignore` 也排除了常见凭据文件名。不要提交、分享或粘贴此文件内容。

## 来源与致谢

- [WuSiYu/BJUT-autologin-both46](https://github.com/WuSiYu/BJUT-autologin-both46)：早期 BJUT 有线门户 Python 登录脚本及门户请求流程。本项目最初从该脚本的服务器副本出发，保留并调整了 `lgn` 门户的认证思路。原项目采用 **GPL-3.0** 许可证；本仓库也按 GPL-3.0 发布，见 [LICENSE](LICENSE)。
- [key-zhzr/BJUT-Auto-Login](https://github.com/key-zhzr/BJUT-Auto-Login)：查阅了该项目的校园网注销和账号切换实现，以核对服务器版的操作流程。本仓库不包含其 Tauri 图形客户端代码。

本仓库集中提供服务器实际使用的 `manager.py` 与 `systemd` 配置。旧版手动脚本会把密码放入命令参数，故未作为公开仓库的运行入口。
