from __future__ import annotations

import base64
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

from .models import RealityKeys


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _parse_hex_block(label: str, text: str) -> bytes:
    match = re.search(rf"{label}:\n((?:\s+[0-9a-f:]+\n?){{1,4}})", text, re.IGNORECASE)
    if not match:
        raise RuntimeError(f"unable to parse {label} from openssl output")
    hex_text = match.group(1).replace(" ", "").replace("\n", "").replace(":", "")
    return bytes.fromhex(hex_text)


def generate_reality_keys(short_id_bytes: int = 8) -> RealityKeys:
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "x25519.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "X25519", "-out", str(key_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        completed = subprocess.run(
            ["openssl", "pkey", "-in", str(key_path), "-text", "-noout"],
            check=True,
            capture_output=True,
            text=True,
        )
    private_raw = _parse_hex_block("priv", completed.stdout)
    public_raw = _parse_hex_block("pub", completed.stdout)
    return RealityKeys(
        private_key=_b64u(private_raw),
        public_key=_b64u(public_raw),
        short_id=secrets.token_hex(short_id_bytes),
    )


def reality_keys_from_existing(private_key: str, short_id: str) -> RealityKeys:
    private_raw = _b64u_decode(private_key)
    with tempfile.TemporaryDirectory() as tmp:
        key_path = Path(tmp) / "x25519.pem"
        der_path = Path(tmp) / "x25519.der"
        der_body = bytes.fromhex("302e020100300506032b656e04220420") + private_raw
        der_path.write_bytes(der_body)
        subprocess.run(
            ["openssl", "pkey", "-inform", "DER", "-outform", "PEM", "-in", str(der_path), "-out", str(key_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        completed = subprocess.run(
            ["openssl", "pkey", "-in", str(key_path), "-text", "-noout"],
            check=True,
            capture_output=True,
            text=True,
        )
    public_raw = _parse_hex_block("pub", completed.stdout)
    return RealityKeys(
        private_key=private_key,
        public_key=_b64u(public_raw),
        short_id=short_id,
    )
