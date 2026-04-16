from __future__ import annotations

import json
from pathlib import Path

from .crypto import reality_keys_from_existing
from .models import NodeSpec


def _first(items: list, label: str):
    if not items:
        raise ValueError(f"xray config missing {label}")
    return items[0]


def _server_name_from_reality_settings(reality_settings: dict) -> str:
    server_names = reality_settings.get("serverNames") or []
    if server_names:
        return _first(server_names, "realitySettings.serverNames")
    target = reality_settings.get("target") or reality_settings.get("dest")
    if isinstance(target, str) and ":" in target:
        return target.rsplit(":", 1)[0]
    raise ValueError("xray config missing reality server name")


def load_xray_reality_node(
    path: Path,
    *,
    name: str,
    tag: str,
    role: str,
) -> NodeSpec:
    payload = json.loads(path.read_text())
    inbounds = payload.get("inbounds") or []
    inbound = None
    for item in inbounds:
        if item.get("protocol") != "vless":
            continue
        reality_settings = (
            item.get("streamSettings", {})
            .get("realitySettings", {})
        )
        if reality_settings.get("privateKey"):
            inbound = item
            break
    if inbound is None:
        raise ValueError("no VLESS Reality inbound found in xray config")

    settings = inbound.get("settings", {})
    clients = settings.get("clients") or []
    client = _first(clients, "settings.clients")

    stream = inbound.get("streamSettings", {})
    reality_settings = stream.get("realitySettings", {})
    short_ids = reality_settings.get("shortIds") or []

    server_name = _server_name_from_reality_settings(reality_settings)
    short_id = _first(short_ids, "realitySettings.shortIds")
    private_key = reality_settings.get("privateKey")
    if not private_key:
        raise ValueError("xray config missing realitySettings.privateKey")

    return NodeSpec(
        tag=tag,
        name=name,
        role="media" if role == "media" else "main",
        listen_port=int(inbound["port"]),
        uuid=client["id"],
        server_name=server_name,
        reality=reality_keys_from_existing(private_key, short_id),
        user_label=client.get("email") or name,
        flow=client.get("flow") or "xtls-rprx-vision",
    )
