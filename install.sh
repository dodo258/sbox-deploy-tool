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
  echo "please run as root"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "this first version supports Debian/Ubuntu only"
  exit 1
fi

MISSING_PKGS=()
command -v python3 >/dev/null 2>&1 || MISSING_PKGS+=("python3")

if (( ${#MISSING_PKGS[@]} > 0 )); then
  step "installing runtime dependencies: ${MISSING_PKGS[*]}"
  apt-get update -o Acquire::Retries=3 -o Acquire::ForceIPv4=true
  apt-get install -y "${MISSING_PKGS[@]}"
else
  ok "runtime dependencies ready"
fi

chmod +x "${ROOT_DIR}/bin/sboxctl"
ln -sf "${ROOT_DIR}/bin/sboxctl" /usr/local/bin/sboxctl
ok "global command ready: sboxctl"

if [[ ! -t 0 && -r /dev/tty ]]; then
  exec </dev/tty
fi

info "launching interactive menu"
exec "${ROOT_DIR}/bin/sboxctl" menu
