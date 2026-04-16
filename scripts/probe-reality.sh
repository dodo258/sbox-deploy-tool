#!/usr/bin/env bash
set -euo pipefail

REGION="${1:-us}"
REPO_SLUG="${SBOXCTL_REPO_SLUG:-dodo258/sbox-deploy-tool}"
REPO_REF="${SBOXCTL_REPO_REF:-main}"
ARCHIVE_URL="https://github.com/${REPO_SLUG}/archive/refs/heads/${REPO_REF}.tar.gz"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERR] python3 is required"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "[ERR] curl is required"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
ARCHIVE_PATH="${TMP_DIR}/repo.tar.gz"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

curl -fsSL "${ARCHIVE_URL}" -o "${ARCHIVE_PATH}"
tar -xzf "${ARCHIVE_PATH}" -C "${TMP_DIR}"
ROOT_DIR="$(find "${TMP_DIR}" -maxdepth 1 -type d -name 'sbox-deploy-tool-*' | head -n 1)"

if [[ -z "${ROOT_DIR}" ]]; then
  echo "[ERR] failed to unpack repository"
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}/lib"
exec python3 -m sbox_tool.cli probe --region "${REGION}"
