#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RESET='\033[0m'
CYAN='\033[38;5;45m'
GREEN='\033[38;5;41m'
YELLOW='\033[38;5;220m'

info() {
  printf "${CYAN}[INFO]${RESET} %s\n" "$1"
}

ok() {
  printf "${GREEN}[OK]${RESET} %s\n" "$1"
}

step() {
  printf "${YELLOW}[STEP]${RESET} %s\n" "$1"
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "请使用 root 运行安装器"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "当前版本仅支持 Debian/Ubuntu"
  exit 1
fi

MISSING_PKGS=()
command -v python3 >/dev/null 2>&1 || MISSING_PKGS+=("python3")

if (( ${#MISSING_PKGS[@]} > 0 )); then
  step "正在安装运行依赖: ${MISSING_PKGS[*]}"
  apt-get update -o Acquire::Retries=3 -o Acquire::ForceIPv4=true
  apt-get install -y "${MISSING_PKGS[@]}"
else
  ok "运行依赖已就绪"
fi

chmod +x "${ROOT_DIR}/bin/sboxctl"
ln -sf "${ROOT_DIR}/bin/sboxctl" /usr/local/bin/sboxctl
ok "全局命令已就绪: sboxctl"

if [[ ! -t 0 && -r /dev/tty ]]; then
  exec </dev/tty
fi

info "正在启动交互菜单"
exec "${ROOT_DIR}/bin/sboxctl" menu
