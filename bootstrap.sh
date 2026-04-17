#!/usr/bin/env bash
set -euo pipefail

REPO_SLUG="${SBOXCTL_REPO_SLUG:-dodo258/sbox-deploy-tool}"
REPO_REF="${SBOXCTL_REPO_REF:-main}"
INSTALL_DIR="${SBOXCTL_INSTALL_DIR:-/opt/sbox-deploy-tool}"
ARCHIVE_URL="https://codeload.github.com/${REPO_SLUG}/tar.gz/refs/heads/${REPO_REF}"

RESET='\033[0m'
CYAN='\033[38;5;45m'
GREEN='\033[38;5;41m'
YELLOW='\033[38;5;220m'

print_logo() {
  printf "${CYAN}   _____ __                ____             ${RESET}\n"
  printf "${CYAN}  / ___// /_  ____  _  __ / __ )____  _  __${RESET}\n"
  printf "${CYAN}  \\__ \\/ __ \\/ __ \\| |/_// __  / __ \\| |/_/${RESET}\n"
  printf "${CYAN} ___/ / /_/ / /_/ />  < / /_/ / /_/ />  <  ${RESET}\n"
  printf "${CYAN}/____/_.___/\\____/_/|_|/_____/\\____/_/|_|  ${RESET}\n"
  printf "dodo258 deploy tool | sing-box / xray | reality | media dns\n\n"
}

info() {
  printf "${CYAN}[INFO]${RESET} %s\n" "$1"
}

ok() {
  printf "${GREEN}[OK]${RESET} %s\n" "$1"
}

step() {
  printf "${YELLOW}[STEP]${RESET} %s\n" "$1"
}

spinner_wait() {
  local pid="$1"
  local message="$2"
  local frames=('|' '/' '-' '\\')
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r${CYAN}[INFO]${RESET} %s %s" "$message" "${frames[$i]}"
    i=$(( (i + 1) % 4 ))
    sleep 0.15
  done
  printf "\r\033[K"
}

download_archive() {
  local url="$1"
  local output="$2"
  local err_file="$3"
  curl -fsSL "$url" -o "$output" 2>"$err_file" &
  local curl_pid=$!
  spinner_wait "$curl_pid" "正在下载最新工具包，请稍等"
  if ! wait "$curl_pid"; then
    err_msg="$(tr '\n' ' ' <"$err_file" | sed 's/[[:space:]]\+/ /g' | sed 's/^ //; s/ $//')"
    if [[ -z "${err_msg}" ]]; then
      err_msg="下载失败，请检查网络后重试"
    fi
    echo "[ERR] ${err_msg}"
    exit 1
  fi
  ok "工具包下载完成"
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERR] 请用 root 执行引导脚本"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ERR] 当前引导脚本仅支持 Debian/Ubuntu"
  exit 1
fi

MISSING_PKGS=()
command -v curl >/dev/null 2>&1 || MISSING_PKGS+=("curl")
command -v tar >/dev/null 2>&1 || MISSING_PKGS+=("tar")
command -v gzip >/dev/null 2>&1 || MISSING_PKGS+=("gzip")
if [[ ! -f /etc/ssl/certs/ca-certificates.crt ]]; then
  MISSING_PKGS+=("ca-certificates")
fi

if (( ${#MISSING_PKGS[@]} > 0 )); then
  step "正在安装引导依赖: ${MISSING_PKGS[*]}"
  apt-get update -o Acquire::Retries=3 -o Acquire::ForceIPv4=true
  apt-get install -y "${MISSING_PKGS[@]}"
else
  ok "引导依赖已就绪"
fi

run_installer() {
  if [[ -r /dev/tty ]]; then
    SBOXCTL_SUPPRESS_MENU_LOGO_ONCE=1 bash "${INSTALL_DIR}/install.sh" </dev/tty
  else
    SBOXCTL_SUPPRESS_MENU_LOGO_ONCE=1 bash "${INSTALL_DIR}/install.sh"
  fi
}

if [[ -x "${INSTALL_DIR}/install.sh" && -x "${INSTALL_DIR}/bin/sboxctl" && "${SBOXCTL_FORCE_UPDATE:-0}" != "1" ]]; then
  print_logo
  ok "检测到现有安装: ${INSTALL_DIR}"
  info "正在直接打开已安装菜单"
  info "如需强制从 GitHub 更新，请先设置 SBOXCTL_FORCE_UPDATE=1"
  run_installer
  exit $?
fi

TMP_DIR="$(mktemp -d)"
ARCHIVE_PATH="${TMP_DIR}/sboxctl.tar.gz"
ERR_PATH="${TMP_DIR}/curl.err"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

print_logo
step "正在下载最新工具包"
info "首次安装或强制更新时会先下载工具包，然后进入菜单"
download_archive "${ARCHIVE_URL}" "${ARCHIVE_PATH}" "${ERR_PATH}"

rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
step "正在解压工具包"
tar -xzf "${ARCHIVE_PATH}" -C "${INSTALL_DIR}" --strip-components=1

chmod +x "${INSTALL_DIR}/install.sh"
chmod +x "${INSTALL_DIR}/bin/sboxctl"
chmod +x "${INSTALL_DIR}/bin/sboxctl-backend"
chmod +x "${INSTALL_DIR}/shell/menu.sh"

ok "已解压到 ${INSTALL_DIR}"
step "正在进入交互菜单"
run_installer
