# dodo258 / SBox Deploy Tool

一个运行在服务器端的 `VLESS + Reality + Vision` 一键部署工具。

目标不是做协议大杂烩，而是把这几件事做好：

- `sing-box` 和 `xray` 双后端可选
- 默认优先 `sing-box`
- 自动安装缺少依赖
- 自动安装并检查 `BBR`
- 自动写入并收口脚本自带防火墙
- 支持主节点、流媒体专用节点、主节点附加流媒体 DNS
- 部署后自动自启动、自动后台常驻

## 1. 服务器端一键启动

先 SSH 登录到你的服务器，再执行：

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)
```

脚本会进入交互首页。

首页会提供这些主选项：

- 部署 `sing-box` 节点
- 部署 `xray` 节点
- 查看节点状态
- 查看 `VLESS` 地址
- 查看 `BBR` 状态
- 单独调整防火墙
- 查看本地域名优选说明

## 2. 本地优选 Reality 域名

Reality 域名优选不应该在服务器上跑，而应该在你自己的本地电脑上跑。

### macOS / Linux

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) us
bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) eu
bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) sea
bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) --list-regions
bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) --domains www.example.com,www.example.net
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.ps1 | iex
irm https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.ps1 | iex -Region eu
irm https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.ps1 | iex -ListRegions
irm https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.ps1 | iex -Domains 'www.example.com,www.example.net'
```

内置候选池已经扩到 `us / eu / uk / de / fr / jp / kr / hk / tw / sg / sea / oceania / latam / africa / middle-east / in`。  
如果你的机器地区不在这些内置池里，直接用 `--domains` 自己传候选域名列表。

优选好以后，再把域名填回服务器端一键脚本。

## 3. 流媒体 DNS

如果你要部署流媒体相关节点，脚本会要求你填写自己的流媒体 DNS。

支持输入格式：

- `IP`
- `IP:PORT`
- `https://...`
- `tls://...`
- `quic://...`

如果后端选择 `xray`，建议优先使用 `IP`、`IP:PORT`、`https://...` 或 `quic://...`。

脚本支持三种部署方式：

- 主节点
- 流媒体专用节点
- 主节点 + 流媒体 DNS

并且支持：

- 使用内置流媒体规则集合
- 自定义要解锁的流媒体域名后缀

## 4. 防火墙策略

脚本默认会自动处理防火墙，并且采用收口模式：

- 永远保留 `22/tcp`
- 永远保留当前服务器检测到的 SSH 端口
- 自动放行当前节点端口
- 自动保留其他已部署节点端口
- 其余端口默认关闭

这样做是为了减少误开口，同时避免把用户锁在服务器外面。

## 5. 常用命令

查看总入口说明：

```bash
./bin/sboxctl init
```

进入交互首页：

```bash
sudo ./bin/sboxctl menu
```

查看已部署节点状态：

```bash
./bin/sboxctl show-status
```

查看已部署节点的 `VLESS` 地址：

```bash
./bin/sboxctl show-links
```

查看 `BBR` 状态：

```bash
./bin/sboxctl bbr-status
```

手动重新收口防火墙：

```bash
sudo ./bin/sboxctl firewall --show-status
```

从旧 `xray` 配置导入：

```bash
./bin/sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <REGION_LABEL> --backend sing-box
```

## 6. 仓库结构

- `bootstrap.sh`：服务器端 raw 一键入口
- `install.sh`：启动脚本
- `bin/sboxctl`：主命令入口
- `scripts/probe-reality.sh`：macOS / Linux 本地域名优选
- `scripts/probe-reality.ps1`：Windows 本地域名优选
- `docs/USAGE.md`：中文使用说明
- `docs/ROADMAP.md`：开发路线

## 7. 说明

- 这个仓库不应该包含任何真实服务器信息、真实域名、真实测试 IP
- 首页只保留新手真正需要看到的内容
- 高阶玩家如果只想手动部署，可以直接阅读源码和生成逻辑
