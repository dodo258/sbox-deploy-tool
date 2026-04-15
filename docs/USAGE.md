# 使用说明

这份文档只保留最常用的内容。

## 1. 一键启动

先 SSH 登录到目标服务器，再执行：

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)
```

这是推荐入口。

## 2. 交互流程里你主要会填什么

脚本会逐步要求你填写这些信息：

- 节点类型
- 地区标记
- 监听端口
- Reality 伪装域名
- 节点名称
- 是否启用防火墙处理

如果你选择的是“流媒体专用节点”，还会继续让你填写：

- 你的流媒体 DNS 地址
- 使用内置流媒体域名集合，还是自定义域名后缀

## 3. 流媒体 DNS

支持输入格式：

- `IP`
- `IP:PORT`
- `https://...`
- `tls://...`
- `quic://...`

脚本会把匹配到的流媒体域名交给这条 DNS 处理，其它普通域名仍然走本地解析。

## 4. 防火墙

脚本的防火墙逻辑默认是安全模式：

- 永远保留 `22/tcp`
- 永远保留当前检测到的 SSH 端口
- 自动放行当前节点端口
- 可额外放行你自己指定的端口

如果后面想单独调整，可以执行：

```bash
sudo ./bin/sboxctl firewall --allow-ports <端口列表> --show-status
```

## 5. 常用命令

查看命令概览：

```bash
./bin/sboxctl init
```

Reality 域名探测：

```bash
./bin/sboxctl probe --region us
```

从旧 Xray 配置导入生成 sing-box bundle：

```bash
./bin/sboxctl import-xray --input <XRAY_JSON> --role <main|media> --region <us|jp|sg>
```

查看系统、服务、端口、BBR 状态：

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

## 6. 备份与恢复

脚本在覆盖配置前会自动备份。

如果你要手动备份：

```bash
sudo ./bin/sboxctl backup --label <标签> --paths <文件路径列表>
```

如果你要手动恢复：

```bash
sudo ./bin/sboxctl restore --archive <备份文件> --destination <恢复目录>
```

## 7. 说明

- 首页文档不再展示具体服务器信息
- 不再展示固定示例 IP、端口、优选域名
- 高阶玩家如需自行部署，可直接阅读源码或自行改命令
