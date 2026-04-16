#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
  apt-get update -o Acquire::Retries=3 -o Acquire::ForceIPv4=true
  apt-get install -y "${MISSING_PKGS[@]}"
fi

chmod +x "${ROOT_DIR}/bin/sboxctl"
ln -sf "${ROOT_DIR}/bin/sboxctl" /usr/local/bin/sboxctl

if [[ ! -t 0 && -r /dev/tty ]]; then
  exec </dev/tty
fi

exec "${ROOT_DIR}/bin/sboxctl" menu
