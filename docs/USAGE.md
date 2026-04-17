# 使用说明

## 一、服务器端主流程

### 1. 登录服务器

先通过 SSH 登录到目标服务器。

### 2. 执行一键脚本

```bash
curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh | sudo bash
```

说明：

- 第一次安装会下载脚本包并进入菜单
- 如果服务器里已经安装过，再次执行 raw 一键命令会直接进入已安装菜单
- 后续更新脚本，直接在首页菜单里选择“更新脚本”
- 如果只是重新进入菜单，也可以直接运行 `sboxctl menu`

### 3. 进入交互首页

首页目前提供：

- 部署 `sing-box` 节点
- 部署 `xray` 节点
- 查看节点状态
- 查看 `VLESS` 地址
- 查看节点日志
- 删除节点
- 查看 `BBR` 状态
- 设置 `UFW` 防火墙
- 修改流媒体 DNS
- 查看 `Reality` 域名说明

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

脚本不会全局改系统 DNS，只会把选中的流媒体域名后缀交给流媒体 DNS 解析。

## 四、BBR

脚本会在部署前自动检查：

- 内核是否支持 `BBR`
- 当前是否已启用 `BBR`
- `fq` 是否已就位

如果未启用，会自动尝试启用。

手动查看：

```bash
sboxctl bbr-status
```

手动启用：

```bash
sudo sboxctl enable-bbr
```

## 五、UFW 防火墙

脚本默认会自动安装并启用 `ufw`，并按收口模式执行：

- 保留 `22/tcp`
- 保留当前 SSH 端口
- 保留当前节点端口
- 保留历史已部署节点端口
- 关闭其余未放行端口

`ufw` 规则会持久化到系统里，重启后仍然有效。

手动执行：

```bash
sudo sboxctl firewall --show-status
```

## 六、修改流媒体 DNS

如果你已经部署了流媒体专用节点，或者主节点启用了流媒体 DNS，后面不需要重部署。

可以直接在菜单里进入“修改流媒体 DNS”，也可以手动执行：

```bash
sudo sboxctl update-streaming-dns --tag <节点标记> --streaming-dns <DNS>
```

如果要关闭某个节点的流媒体 DNS：

```bash
sudo sboxctl update-streaming-dns --tag <节点标记> --disable
```

## 七、常用命令

查看入口说明：

```bash
sboxctl init
```

进入交互首页：

```bash
sudo sboxctl menu
```

查看节点状态：

```bash
sboxctl show-status
```

查看节点地址：

```bash
sboxctl show-links
```

查看某个节点最近日志：

```bash
sboxctl show-logs
```

修改某个节点的流媒体 DNS：

```bash
sudo sboxctl update-streaming-dns --tag <节点标记> --streaming-dns <DNS>
```

删除某个已部署节点：

```bash
sudo sboxctl remove-node
```

从旧 `xray` 配置导入：

```bash
sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <REGION_LABEL> --backend sing-box
```

## 八、Reality 域名选择

部署流程会根据服务器地区自动匹配内置候选池，并直接给出推荐域名编号，让用户只选 `1 / 2 / 3`。

脚本只使用内置地址池，不对普通用户开放手填自定义域名。
