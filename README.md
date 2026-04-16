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
curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh | sudo bash
```

脚本会进入交互首页。

安装完成后，可以直接在服务器里输入：

```bash
sboxctl menu
```

首页会提供这些主选项：

- 部署 `sing-box` 节点
- 部署 `xray` 节点
- 查看节点状态
- 查看 `VLESS` 地址
- 查看节点日志
- 删除节点
- 查看 `BBR` 状态
- 单独调整防火墙
- 查看 `Reality` 域名选择说明

## 2. Reality 域名选择

部署流程会根据服务器地区自动匹配内置候选池，并直接给出推荐域名编号让用户选 `1 / 2 / 3`。

对外默认只开放内置地区池，不让普通用户手填自定义域名。

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
sboxctl show-links
```

查看某个节点最近日志：

```bash
sboxctl show-logs
```

删除某个已部署节点：

```bash
sudo sboxctl remove-node
```

查看 `BBR` 状态：

```bash
sboxctl bbr-status
```

手动重新收口防火墙：

```bash
sudo sboxctl firewall --show-status
```

从旧 `xray` 配置导入：

```bash
sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <REGION_LABEL> --backend sing-box
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
