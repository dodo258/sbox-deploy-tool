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

apt-get update
apt-get install -y ca-certificates curl tar gzip unzip openssl jq ufw python3 python3-cryptography

chmod +x "${ROOT_DIR}/bin/sboxctl"
exec "${ROOT_DIR}/bin/sboxctl" wizard
