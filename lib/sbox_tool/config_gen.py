from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .models import DeployPlan


def build_dns_server(tag: str, address: str) -> dict:
    if address == "local":
        return {"type": "local", "tag": tag}
    if "://" in address:
        parsed = urlparse(address)
        scheme = parsed.scheme.lower()
        if scheme == "https":
            return {
                "type": "https",
                "tag": tag,
                "server": parsed.hostname,
                "server_port": parsed.port or 443,
                "path": parsed.path or "/dns-query",
                "tls": {},
            }
        if scheme == "tls":
            return {
                "type": "tls",
                "tag": tag,
                "server": parsed.hostname,
                "server_port": parsed.port or 853,
                "tls": {},
            }
        if scheme == "quic":
            return {
                "type": "quic",
                "tag": tag,
                "server": parsed.hostname,
                "server_port": parsed.port or 853,
                "tls": {},
            }
        if scheme == "tcp":
            return {
                "type": "tcp",
                "tag": tag,
                "server": parsed.hostname,
                "server_port": parsed.port or 53,
            }
        if scheme == "udp":
            return {
                "type": "udp",
                "tag": tag,
                "server": parsed.hostname,
                "server_port": parsed.port or 53,
            }
    host_port_match = re.fullmatch(r"([^:]+):(\d+)", address)
    if host_port_match:
        return {
            "type": "udp",
            "tag": tag,
            "server": host_port_match.group(1),
            "server_port": int(host_port_match.group(2)),
        }
    return {
        "type": "udp",
        "tag": tag,
        "server": address,
        "server_port": 53,
    }


def build_config(plan: DeployPlan) -> dict:
    node = plan.node
    inbound = {
        "type": "vless",
        "tag": node.tag,
        "listen": "::",
        "listen_port": node.listen_port,
        "users": [
            {
                "uuid": node.uuid,
                "flow": node.flow,
                "name": node.user_label,
            }
        ],
        "tls": {
            "enabled": True,
            "server_name": node.server_name,
            "reality": {
                "enabled": True,
                "handshake": {
                    "server": node.server_name,
                    "server_port": 443,
                },
                "private_key": node.reality.private_key,
                "short_id": [node.reality.short_id],
            },
        },
    }

    dns_servers = [build_dns_server(plan.local_dns_tag, "local")]
    route_rules: list[dict] = []

    if plan.streaming_dns:
        dns_servers.append(
            build_dns_server("streaming-dns", plan.streaming_dns.dns_server)
        )
        route_rules.append({"inbound": [node.tag], "action": "sniff"})
        route_rules.append(
            {
                "domain_suffix": plan.streaming_dns.match_suffixes,
                "action": "resolve",
                "server": "streaming-dns",
            }
        )
        route_rules.append(
            {
                "inbound": [node.tag],
                "action": "resolve",
                "strategy": "prefer_ipv4",
            }
        )
    else:
        route_rules.append({"inbound": [node.tag], "action": "sniff"})

    config = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": dns_servers,
            "strategy": "prefer_ipv4",
            "disable_cache": False,
            "independent_cache": True,
            "final": plan.local_dns_tag,
        },
        "inbounds": [inbound],
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {
            "auto_detect_interface": True,
            "final": node.detour_tag,
            "default_domain_resolver": plan.local_dns_tag,
            "rules": route_rules,
        },
    }
    return config


def build_service(service_name: str, binary_name: str, config_path: str) -> str:
    return "\n".join(
        [
            "[Unit]",
            f"Description={service_name}",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"ExecStart=/usr/local/bin/{binary_name} run -c {config_path}",
            "Restart=always",
            "RestartSec=3",
            "LimitNOFILE=1048576",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
