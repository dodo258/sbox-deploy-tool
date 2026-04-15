# Usage Guide

## 1. Choose a deployment path

There are three practical ways to use this tool:

- raw-link bootstrap on the server
- local deployment from a cloned repository
- remote deployment from another machine

### Recommended: raw-link bootstrap on the server

SSH to the target server first, then run:

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)
```

This path is intended for beginners.

### Local deployment from a cloned repository

Use this when you are already logged into the target server.

```bash
sudo ./install.sh
```

or:

```bash
sudo ./bin/sboxctl deploy-local ...
```

### Remote deployment

Use this when you want to run the tool from your own machine and push it to a server through SSH.

```bash
./bin/sboxctl deploy-remote ...
```

`deploy-remote` packages the current project, uploads it with `scp`, unpacks it on the target host, and then runs `deploy-local` there.

Authentication choices:

- recommended: `--identity-file ~/.ssh/id_ed25519`
- optional: `--ssh-password your-password`

If you use `--ssh-password`, your local machine must have `sshpass` installed.

## 2. Probe a Reality target domain

```bash
./bin/sboxctl probe --region us
./bin/sboxctl probe --region jp
./bin/sboxctl probe --region sg
```

Look for domains that satisfy:

- `tls13=True`
- `h2=True`
- HTTP status `200-399`
- lower `ttfb`

## 3. Deploy a main node

Example:

```bash
sudo ./bin/sboxctl deploy-local \
  --role main \
  --region us \
  --port 443 \
  --domain www.uline.com \
  --name US-MAIN \
  --service-name sing-box-us-main
```

What this does:

- installs dependencies if needed
- installs sing-box if needed
- generates new Reality keys
- writes config to `/etc/sing-box/us-main.json`
- writes systemd unit to `/etc/systemd/system/sing-box-us-main.service`
- enables and restarts the service
- creates a backup before overwrite
- updates UFW if firewall mode is enabled

## 4. Deploy a media DNS node

Example:

```bash
sudo ./bin/sboxctl deploy-local \
  --role media \
  --region us \
  --port 2443 \
  --domain www.uline.com \
  --name US-MEDIA \
  --service-name sing-box-us-media \
  --streaming-dns 138.2.89.178 \
  --streaming-profile common-media
```

This mode:

- enables route-based sniffing
- sends matching streaming domains to the user-supplied DNS server
- leaves other domains on the local resolver

## 5. Custom streaming DNS profiles

Built-in profiles:

- `common-media`
- `netflix`
- `disney`
- `max`
- `primevideo`
- `hulu`

Custom override:

```bash
sudo ./bin/sboxctl deploy-local \
  --role media \
  --region us \
  --port 2443 \
  --domain www.uline.com \
  --name CUSTOM-MEDIA \
  --streaming-dns tls://dns.example.com \
  --streaming-domains netflix.com,nflxvideo.net,disneyplus.com
```

## 6. Remote deployment example

```bash
./bin/sboxctl deploy-remote \
  --host 203.0.113.10 \
  --ssh-user root \
  --ssh-port 22 \
  --identity-file ~/.ssh/id_ed25519 \
  --role main \
  --region us \
  --port 443 \
  --domain www.uline.com \
  --name US-MAIN
```

For a media node:

```bash
./bin/sboxctl deploy-remote \
  --host 203.0.113.10 \
  --ssh-user root \
  --ssh-port 22 \
  --identity-file ~/.ssh/id_ed25519 \
  --role media \
  --region us \
  --port 2443 \
  --domain www.uline.com \
  --name US-MEDIA \
  --streaming-dns 138.2.89.178 \
  --streaming-profile common-media
```

Password-based example:

```bash
./bin/sboxctl deploy-remote \
  --host 203.0.113.10 \
  --ssh-user root \
  --ssh-port 22 \
  --ssh-password your-password \
  --role main \
  --region us \
  --port 443 \
  --domain www.uline.com \
  --name US-MAIN
```

## 7. Firewall management

If you want to adjust UFW separately:

```bash
sudo ./bin/sboxctl firewall --allow-ports 443,2443 --show-status
```

This command always preserves:

- `22/tcp`
- detected SSH ports on the current server

## 8. Backup and restore

Create a backup:

```bash
sudo ./bin/sboxctl backup \
  --label before-change \
  --paths /etc/sing-box/us-main.json,/etc/systemd/system/sing-box-us-main.service
```

Restore a backup:

```bash
sudo ./bin/sboxctl restore \
  --archive /var/backups/sboxctl/before-change-20260415-120000.tar.gz \
  --destination /root/restore-output
```

## 9. Check current state

```bash
./bin/sboxctl doctor --services sing-box-us-main,sing-box-us-media --ports 443,2443
```

## 10. Client imports

Each deployment bundle includes:

- a `vless://` link for Shadowrocket-style clients
- a Mihomo proxy fragment

The files are written into the local `output/<tag>/` directory when you run `generate` or `deploy-local` from that machine.
