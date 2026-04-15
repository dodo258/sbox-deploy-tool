from __future__ import annotations

from .models import NodeSpec


def export_vless_url(server: str, node: NodeSpec) -> str:
    return (
        f"vless://{node.uuid}@{server}:{node.listen_port}"
        f"?encryption=none&flow={node.flow}&security=reality"
        f"&sni={node.server_name}&fp=chrome"
        f"&pbk={node.reality.public_key}&sid={node.reality.short_id}"
        f"&type=tcp#{node.name}"
    )


def export_mihomo_proxy(server: str, node: NodeSpec) -> dict:
    return {
        "name": node.name,
        "type": "vless",
        "server": server,
        "port": node.listen_port,
        "uuid": node.uuid,
        "flow": node.flow,
        "network": "tcp",
        "tls": True,
        "sni": node.server_name,
        "client-fingerprint": "chrome",
        "reality-opts": {
            "public-key": node.reality.public_key,
            "short-id": node.reality.short_id,
        },
        "udp": node.enable_udp,
    }
