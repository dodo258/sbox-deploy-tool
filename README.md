# dodo258 / SBox Deploy Tool

一个运行在服务器端的 `VLESS + Reality + Vision` 一键部署工具。

- 支持 `sing-box` 和 `xray` 双后端
- 默认优先 `sing-box`
- 自动安装基础依赖
- 自动检查并启用 `BBR`
- 自动写入并收口脚本自带防火墙
- 支持主节点、流媒体专用节点、主节点附加流媒体 DNS

## 一键启动

先 SSH 登录到你的服务器，再执行：

```bash
curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh | sudo bash
```

安装完成后，可以直接运行：

```bash
sboxctl menu
```

说明：

- 第一次安装，或者你再次用 raw 一键命令拉最新版本时，会下载脚本包
- 如果只是重新进入菜单，不需要再执行 raw 命令，直接运行 `sboxctl menu`

## 仓库结构

- `bootstrap.sh`：服务器端 raw 一键入口
- `install.sh`：启动脚本
- `bin/sboxctl`：主命令入口
- `scripts/probe-reality.sh`：macOS / Linux 本地域名优选
- `scripts/probe-reality.ps1`：Windows 本地域名优选
- `docs/USAGE.md`：中文使用说明
- `docs/ROADMAP.md`：开发路线

## 流媒体 DNS

- 支持 `IP`
- 支持 `IP:PORT`
- 支持 `https://...`
- 支持 `tls://...`
- 支持 `quic://...`

注意：

- `xray` 后端建议优先使用 `IP`、`IP:PORT`、`https://...` 或 `quic://...`
- 脚本不会全局改系统 DNS
- 只会把选中的流媒体域名后缀交给流媒体 DNS 解析

## 防火墙

脚本默认自动处理防火墙，并按收口模式执行：

- 永远保留 `22/tcp`
- 永远保留当前服务器检测到的 SSH 端口
- 自动放行当前节点端口
- 自动保留其他已部署节点端口
- 其余端口默认关闭

## 常用命令

```bash
sboxctl init
sudo sboxctl menu
sboxctl show-status
sboxctl show-links
sboxctl show-logs
sudo sboxctl remove-node
sboxctl bbr-status
sudo sboxctl firewall --show-status
```

## 说明

- Reality 域名由部署流程按服务器地区自动匹配内置候选池，并直接给出推荐编号让用户选 `1 / 2 / 3`
- 对外默认只开放内置地区池，不让普通用户手填自定义域名
- 详细使用说明见 [docs/USAGE.md](docs/USAGE.md)
