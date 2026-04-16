# 使用说明

## 一、服务器端主流程

### 1. 登录服务器

先通过 SSH 登录到目标服务器。

### 2. 执行一键脚本

```bash
curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh | sudo bash
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
- Reality 推荐域名编号选择
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

如果你选的是 `xray` 后端，推荐填写 `IP`、`IP:PORT`、`https://...` 或 `quic://...`。

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

脚本默认会自动写入并启用脚本自带的防火墙服务，并按收口模式执行：

- 保留 `22/tcp`
- 保留当前 SSH 端口
- 保留当前节点端口
- 保留历史已部署节点端口
- 关闭其余未放行端口

防火墙规则会持久化到系统里，重启后仍然有效。

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
./bin/sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <REGION_LABEL> --backend sing-box
```

## 七、本地域名优选

Reality 域名优选应在本地电脑执行，而不是在服务器执行。

推荐流程：

1. 在本地电脑上运行仓库里的本地域名优选脚本。
2. 把目标服务器公网 IP 传给脚本。
3. 脚本会自动识别服务器地区，并匹配对应的内置候选域名池。
4. 查看输出结果，记录排名靠前的域名。
5. 回到服务器端向导，在推荐域名列表里直接选择 `1 / 2 / 3`。

补充说明：

- macOS / Linux 建议用 `bash` 或 `zsh` 执行。
- 如果本地默认 shell 是 `fish`，先切到 `bash` 或 `zsh` 再运行。
- Windows 端用 PowerShell 执行。
- 如果只是想先确认内置支持哪些地区池，可以使用“列出地区池”模式。

脚本会根据服务器 IP 自动匹配内置地区池。  
内置候选池已经覆盖 `us / eu / uk / de / fr / jp / kr / hk / tw / sg / sea / oceania / latam / africa / middle-east / in`。

对外默认只开放内置地区池，不让普通用户手填自定义域名。

服务器端部署流程也会根据地区池自动给出推荐域名编号，普通用户不需要自己复制域名。
