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

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERR] please run bootstrap as root"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ERR] this bootstrap currently supports Debian/Ubuntu only"
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
  step "installing bootstrap dependencies: ${MISSING_PKGS[*]}"
  apt-get update -o Acquire::Retries=3 -o Acquire::ForceIPv4=true
  apt-get install -y "${MISSING_PKGS[@]}"
else
  ok "bootstrap dependencies ready"
fi

run_installer() {
  if [[ -r /dev/tty ]]; then
    bash "${INSTALL_DIR}/install.sh" </dev/tty
  else
    bash "${INSTALL_DIR}/install.sh"
  fi
}

if [[ -x "${INSTALL_DIR}/install.sh" && -x "${INSTALL_DIR}/bin/sboxctl" && "${SBOXCTL_FORCE_UPDATE:-0}" != "1" ]]; then
  print_logo
  ok "existing install found at ${INSTALL_DIR}"
  info "opening the installed menu directly"
  info "set SBOXCTL_FORCE_UPDATE=1 if you want to refresh from GitHub"
  run_installer
  exit $?
fi

TMP_DIR="$(mktemp -d)"
ARCHIVE_PATH="${TMP_DIR}/sboxctl.tar.gz"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

print_logo
step "downloading latest tool package"
info "first install or update will download the package, then enter the menu"
curl -#fL "${ARCHIVE_URL}" -o "${ARCHIVE_PATH}"
printf "\n"

rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
step "unpacking package"
tar -xzf "${ARCHIVE_PATH}" -C "${INSTALL_DIR}" --strip-components=1

chmod +x "${INSTALL_DIR}/install.sh"
chmod +x "${INSTALL_DIR}/bin/sboxctl"

ok "unpacked to ${INSTALL_DIR}"
step "starting interactive menu"
run_installer
