from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


NodeRole = Literal["main", "media"]


@dataclass(slots=True)
class RealityKeys:
    private_key: str
    public_key: str
    short_id: str


@dataclass(slots=True)
class NodeSpec:
    tag: str
    name: str
    role: NodeRole
    listen_port: int
    uuid: str
    server_name: str
    reality: RealityKeys
    user_label: str
    enable_udp: bool = True
    detour_tag: str = "direct"
    packet_encoding: str = "xudp"
    flow: str = "xtls-rprx-vision"


@dataclass(slots=True)
class StreamingDnsSpec:
    provider_label: str
    dns_server: str
    profile_name: str = "common-media"
    match_suffixes: list[str] = field(
        default_factory=lambda: [
            "netflix.com",
            "netflix.net",
            "nflxvideo.net",
            "nflximg.net",
            "nflximg.com",
            "nflxext.com",
            "nflxso.net",
            "nflxsearch.net",
            "fast.com",
        ]
    )


@dataclass(slots=True)
class DeployPlan:
    install_root: Path
    binary_name: str
    service_name: str
    node: NodeSpec
    local_dns_tag: str = "local"
    streaming_dns: StreamingDnsSpec | None = None
    sniff: bool = True
