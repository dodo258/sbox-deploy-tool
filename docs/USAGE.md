# 使用说明

## 一、服务器端主流程

### 1. 登录服务器

先通过 SSH 登录到目标服务器。

### 2. 执行一键脚本

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)
```

### 3. 进入交互首页

首页目前提供：

- 部署 `sing-box` 节点
- 部署 `xray` 节点
- 查看节点状态
- 查看 `VLESS` 地址
- 查看 `BBR` 状态
- 调整防火墙
- 查看本地域名优选说明

## 二、部署时会让你选择什么

### 1. 后端

- `sing-box`
- `xray`

默认推荐 `sing-box`。

### 2. 节点模式

- 主节点
- 流媒体专用节点
- 主节点 + 流媒体 DNS

### 3. 常见输入项

- 地区标记
- 监听端口
- Reality 伪装域名
- 节点名称
- 是否附加流媒体 DNS
- 流媒体规则集合或自定义域名

## 三、流媒体 DNS

支持：

- `IP`
- `IP:PORT`
- `https://...`
- `tls://...`
- `quic://...`

如果你要自定义解锁范围，可以在交互流程里选择：

- 内置规则集合
- 自定义域名后缀列表

## 四、BBR

脚本会在部署前自动检查：

- 内核是否支持 `BBR`
- 当前是否已启用 `BBR`
- `fq` 是否已就位

如果未启用，会自动尝试启用。

手动查看：

```bash
./bin/sboxctl bbr-status
```

手动启用：

```bash
sudo ./bin/sboxctl enable-bbr
```

## 五、防火墙

脚本默认会自动处理 `ufw`，并按收口模式执行：

- 保留 `22/tcp`
- 保留当前 SSH 端口
- 保留当前节点端口
- 保留历史已部署节点端口
- 关闭其余未放行端口

手动执行：

```bash
sudo ./bin/sboxctl firewall --show-status
```

## 六、常用命令

查看入口说明：

```bash
./bin/sboxctl init
```

进入交互首页：

```bash
sudo ./bin/sboxctl menu
```

查看节点状态：

```bash
./bin/sboxctl show-status
```

查看节点地址：

```bash
./bin/sboxctl show-links
```

从旧 `xray` 配置导入：

```bash
./bin/sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <us|jp|sg> --backend sing-box
```

## 七、本地域名优选

Reality 域名优选应在本地电脑执行，而不是在服务器执行。

### macOS / Linux

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) us
```

### Windows PowerShell

```powershell
irm https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.ps1 | iex
```

优选完成后，把结果填回服务器端向导即可。
