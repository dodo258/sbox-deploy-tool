#!/usr/bin/env bash
set -euo pipefail

REPO_SLUG="${SBOXCTL_REPO_SLUG:-dodo258/sbox-deploy-tool}"
REPO_REF="${SBOXCTL_REPO_REF:-main}"
INSTALL_DIR="${SBOXCTL_INSTALL_DIR:-/opt/sbox-deploy-tool}"
ARCHIVE_URL="https://github.com/${REPO_SLUG}/archive/refs/heads/${REPO_REF}.tar.gz"

if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERR] please run bootstrap as root"
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ERR] this bootstrap currently supports Debian/Ubuntu only"
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl tar gzip

TMP_DIR="$(mktemp -d)"
ARCHIVE_PATH="${TMP_DIR}/sboxctl.tar.gz"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

echo "[INFO] downloading ${ARCHIVE_URL}"
curl -fsSL "${ARCHIVE_URL}" -o "${ARCHIVE_PATH}"

rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${INSTALL_DIR}" --strip-components=1

chmod +x "${INSTALL_DIR}/install.sh"
chmod +x "${INSTALL_DIR}/bin/sboxctl"

echo "[INFO] unpacked to ${INSTALL_DIR}"
exec "${INSTALL_DIR}/install.sh"
