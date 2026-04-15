from __future__ import annotations

import base64
import secrets

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

from .models import RealityKeys


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64u_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def generate_reality_keys(short_id_bytes: int = 8) -> RealityKeys:
    private = x25519.X25519PrivateKey.generate()
    public = private.public_key()
    private_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return RealityKeys(
        private_key=_b64u(private_raw),
        public_key=_b64u(public_raw),
        short_id=secrets.token_hex(short_id_bytes),
    )


def reality_keys_from_existing(private_key: str, short_id: str) -> RealityKeys:
    private_raw = _b64u_decode(private_key)
    private = x25519.X25519PrivateKey.from_private_bytes(private_raw)
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return RealityKeys(
        private_key=private_key,
        public_key=_b64u(public_raw),
        short_id=short_id,
    )
