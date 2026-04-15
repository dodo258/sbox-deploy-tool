# SBox Deploy Tool

`SBox Deploy Tool` is a sing-box deployment tool for people who want a cleaner replacement for large Xray shell scripts.

It focuses on two practical node types:

- a normal `VLESS + Reality + Vision` node
- a media-focused node that sends selected streaming domains to a user-supplied DNS unlock service

## What it does

- installs missing Debian/Ubuntu dependencies on fresh servers
- installs sing-box automatically
- generates Reality keys automatically
- deploys sing-box config and systemd unit files
- creates backups before overwrite
- exports standard `vless://` and Mihomo proxy fragments
- manages UFW with SSH-safe defaults
- checks and enables BBR
- probes candidate Reality domains
- supports both local deployment and remote deployment over `ssh/scp`

## Scope

- protocol: `VLESS + Reality + Vision`
- system: `Ubuntu / Debian`
- roles: `main` and `media`

## Repository layout

- `bin/sboxctl`: launcher
- `install.sh`: bootstrap entry for running directly on a server
- `lib/sbox_tool/`: Python implementation
- `templates/candidate_domains.json`: starter Reality candidate pools
- `tests/`: unit tests
- `docs/USAGE.md`: step-by-step usage guide
- `docs/ROADMAP.md`: next-stage planning

## Fast start

### Option A: run directly on the target server with a raw link

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)
```

This is the primary beginner path.

### Option B: clone the repository on the target server

```bash
git clone https://github.com/dodo258/sbox-deploy-tool.git
cd sbox-deploy-tool
sudo ./install.sh
```

### Option C: deploy remotely from your local machine

```bash
git clone https://github.com/dodo258/sbox-deploy-tool.git
cd sbox-deploy-tool
./bin/sboxctl deploy-remote \
  --host 203.0.113.10 \
  --ssh-port 22 \
  --ssh-user root \
  --identity-file ~/.ssh/id_ed25519 \
  --role main \
  --region us \
  --port 443 \
  --domain www.uline.com \
  --name US-MAIN
```

## Common commands

Show overview:

```bash
./bin/sboxctl init
```

Probe Reality candidates:

```bash
./bin/sboxctl probe --region us
```

Deploy a main node locally:

```bash
./bin/sboxctl deploy-local \
  --role main \
  --region jp \
  --port 443 \
  --domain www.u-can.co.jp \
  --name JP-DMIT
```

Deploy a media node locally:

```bash
./bin/sboxctl deploy-local \
  --role media \
  --region us \
  --port 2443 \
  --domain www.uline.com \
  --name US-Streaming-SG \
  --streaming-dns 138.2.89.178 \
  --provider-label my-dns-vendor \
  --streaming-profile common-media
```

Apply firewall rules manually:

```bash
./bin/sboxctl firewall --allow-ports 443,2443 --show-status
```

Inspect service and port state:

```bash
./bin/sboxctl doctor --services sing-box-us-main,sing-box-us-media --ports 443,2443
```

Show BBR state:

```bash
./bin/sboxctl bbr-status
```

Enable BBR:

```bash
sudo ./bin/sboxctl enable-bbr
```

## Firewall behavior

When firewall handling is enabled, the tool always preserves:

- `22/tcp`
- SSH ports detected from the current server
- the node listen port
- optional extra ports supplied by the user

This is deliberate. A deployment tool that closes SSH is not acceptable.

## Streaming DNS behavior

The tool does not hardcode a DNS unlock provider.

Users supply their own DNS address and choose either:

- a built-in streaming profile
- or their own suffix list with `--streaming-domains`

Built-in profiles:

- `common-media`
- `netflix`
- `disney`
- `max`
- `primevideo`
- `hulu`

Accepted streaming DNS formats:

- `138.2.89.178`
- `138.2.89.178:5353`
- `https://dns.example.com/dns-query`
- `tls://dns.example.com`
- `quic://dns.example.com`

## Notes

- `probe` depends on the current machine's outbound network and DNS reachability.
- `deploy-local` is intended to run directly on the target server as `root`.
- `deploy-remote` assumes `ssh/scp` access from the current machine.
- `bootstrap.sh` is the raw-link entry for server-side one-command installation.
- `deploy-remote` supports either:
  - key-based SSH with `--identity-file`
  - password-based SSH with `--ssh-password`, which requires local `sshpass`
- generated bundles are placed under `output/` locally, but the repository ignores that directory by default.

## More docs

See:

- `docs/USAGE.md`
- `docs/ROADMAP.md`
