# dodo258 / SBox Deploy Tool

一个面向 `Ubuntu / Debian` 服务器的 `sing-box` 一键部署工具。

目标很直接：

- 用户先连上自己的 SSH 服务器
- 执行一条命令
- 按提示填写端口、Reality 伪装域名、流媒体 DNS
- 自动完成依赖安装、sing-box 安装、systemd、备份、防火墙处理

这不是“大而全”的协议合集工具。当前只做一件事：

- `VLESS + Reality + Vision`

## 中文使用方式

先 SSH 登录到服务器，然后执行：

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)
```

执行后脚本会进入交互流程。

## 这个工具会帮你做什么

- 自动安装缺少的基础依赖
- 自动安装 `sing-box`
- 自动生成或导入 Reality 参数
- 生成 sing-box 配置和 systemd 服务
- 覆盖前自动备份旧文件
- 可选启用并检查 `BBR`
- 自动处理防火墙

## 流媒体 DNS 的使用方式

如果你要做“流媒体专用节点”，脚本会要求你填写自己的流媒体 DNS。

支持这几种格式：

- 纯 IP
- `IP:PORT`
- `https://...`
- `tls://...`
- `quic://...`

脚本只会把你指定的流媒体域名交给这个 DNS 解析，不会粗暴改掉整台机器的所有 DNS 请求。

## 防火墙规则

脚本内置了防火墙保护逻辑：

- 强制保留 `22/tcp`
- 强制保留当前服务器检测到的 SSH 端口
- 放行你部署节点使用的端口
- 你也可以额外填写自己要放行的端口

这样做是为了避免用户把自己锁死在服务器外面。

## 常用命令

查看工具说明：

```bash
./bin/sboxctl init
```

查看 Reality 域名探测结果：

```bash
./bin/sboxctl probe --region us
```

从旧的 Xray Reality 配置导入：

```bash
./bin/sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <us|jp|sg>
```

查看当前系统和服务状态：

```bash
./bin/sboxctl doctor --services <服务名> --ports <端口列表>
```

查看 BBR 状态：

```bash
./bin/sboxctl bbr-status
```

启用 BBR：

```bash
sudo ./bin/sboxctl enable-bbr
```

单独调整防火墙：

```bash
sudo ./bin/sboxctl firewall --allow-ports <端口列表> --show-status
```

## 适合谁

适合：

- 刚买 VPS，想尽快部署 sing-box 的用户
- 需要流媒体专用节点的用户
- 不想手动处理 systemd、备份、防火墙、BBR 的用户

不适合：

- 只想手搓全部配置的高级用户
- 需要一堆杂协议混装的人

## 仓库说明

- `bootstrap.sh`：服务器端一键入口
- `install.sh`：本地启动入口
- `bin/sboxctl`：CLI 入口
- `docs/USAGE.md`：中文简版使用说明
- `docs/ROADMAP.md`：后续规划

## 说明

- 首页只保留新手最需要看到的内容
- 更细的高级能力会继续保留在代码里，但不会堆在首页
- 如果你只是正常使用，一般只需要记住那条 raw 一键命令
