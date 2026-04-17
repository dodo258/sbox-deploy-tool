from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
import uuid
from pathlib import Path

from .config_gen import build_config, build_manifest, build_service, write_json
from .crypto import generate_reality_keys
from .domain_probe import ProbeResult, candidate_pool_for_region, rank_domains
from .exports import export_mihomo_proxy, export_vless_url
from .geo import lookup_ip_metadata
from .models import BackendType, DeployPlan, NodeSpec, RealityKeys, StreamingDnsSpec
from .profiles import STREAMING_PROFILES, get_profile
from .remote_ops import (
    cleanup_local_archive,
    package_project,
    render_prepare_remote_dir_command,
    render_remote_deploy_command,
    run_remote,
    upload_archive,
)
from .system_ops import (
    CommandError,
    MANIFEST_ROOT,
    backup_paths,
    bbr_status,
    collect_manifest_ports,
    collect_manifest_services,
    default_binary_name,
    default_install_root,
    default_service_prefix,
    detect_os,
    detect_primary_ipv4,
    detect_ssh_ports,
    enable_bbr,
    enforce_firewall_tcp_allowlist,
    ensure_apt_dependencies,
    ensure_bbr_enabled,
    firewall_status,
    install_backend,
    installed_backend_version,
    kernel_release,
    load_firewall_extra_ports,
    load_node_manifests,
    parse_port_list,
    port_is_listening,
    read_service_logs,
    require_root,
    remove_node_manifest,
    restore_backup,
    stop_and_disable_service,
    systemd_apply,
    systemd_status,
    validate_domain,
    validate_port,
    wait_for_service,
    write_node_manifest,
)
from .ui import err, info, ok, print_logo, section, warn
from .xray_import import load_xray_reality_node


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "output"
BACKUP_ROOT = Path("/var/backups/sboxctl")
_TTY_HANDLE = None


class BackToMenu(CommandError):
    pass


def _json_dump(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _prompt_input(prompt: str, allow_back: bool = False) -> str:
    global _TTY_HANDLE
    try:
        line = input(prompt)
    except EOFError:
        if _TTY_HANDLE is None:
            try:
                _TTY_HANDLE = open("/dev/tty", "r+", encoding="utf-8", buffering=1)
            except OSError as exc:
                raise CommandError("交互输入不可用，请在 SSH TTY 终端中运行") from exc
        _TTY_HANDLE.write(prompt)
        _TTY_HANDLE.flush()
        line = _TTY_HANDLE.readline()
        if line == "":
            raise CommandError("交互输入意外关闭")
        line = line.rstrip("\n")
    if allow_back and line.strip() == "0":
        raise BackToMenu()
    return line


def _default_name(role: str, region: str, backend: BackendType) -> str:
    suffix = "main" if role == "main" else "media"
    return f"{region.upper()}-{backend}-{suffix}"


def _normalize_region(region: str) -> str:
    token = region.strip().lower()
    if not token:
        raise CommandError("region label cannot be empty")
    return token


def _resolve_server_address(server: str | None) -> str:
    if server:
        return server
    try:
        return detect_primary_ipv4()
    except Exception:
        warn("unable to detect primary IPv4 automatically; using <SERVER_IP> in exports")
        return "<SERVER_IP>"


def _ensure_dependencies() -> None:
    ensure_apt_dependencies(
        [
            "ca-certificates",
            "openssl",
            "python3",
        ]
    )


def _build_streaming_dns(
    backend: BackendType,
    enabled: bool,
    streaming_dns: str | None,
    streaming_profile: str,
    streaming_domains: str | None,
    provider_label: str,
) -> StreamingDnsSpec | None:
    if not enabled:
        return None
    if not streaming_dns:
        raise CommandError("streaming DNS is required for media-enabled modes")
    if backend == "xray" and streaming_dns.startswith("tls://"):
        raise CommandError("xray backend does not accept tls:// streaming DNS directly; use IP, IP:PORT, https:// or quic://")
    suffixes = get_profile(streaming_profile)
    if streaming_domains:
        suffixes = [part.strip() for part in streaming_domains.split(",") if part.strip()]
    return StreamingDnsSpec(
        provider_label=provider_label,
        dns_server=streaming_dns,
        profile_name=streaming_profile,
        match_suffixes=suffixes,
    )


def _make_node(role: str, region: str, port: int, domain: str, name: str | None, backend: BackendType) -> NodeSpec:
    keys = generate_reality_keys()
    node_name = name or _default_name(role, region, backend)
    return NodeSpec(
        tag=node_name.lower().replace(" ", "-"),
        name=node_name,
        role="media" if role == "media" else "main",
        listen_port=port,
        uuid=str(uuid.uuid4()),
        server_name=domain,
        reality=keys,
        user_label=node_name,
    )


def _build_plan_from_args(args: argparse.Namespace) -> tuple[DeployPlan, str]:
    validate_port(args.port)
    validate_domain(args.domain)
    backend: BackendType = args.backend
    server = _resolve_server_address(args.server)
    region = _normalize_region(args.region)
    node = _make_node(args.role, region, args.port, args.domain, args.name, backend)
    streaming_dns = _build_streaming_dns(
        backend,
        bool(args.enable_streaming_dns),
        args.streaming_dns,
        args.streaming_profile,
        args.streaming_domains,
        args.provider_label,
    )
    install_root = Path(args.install_root) if args.install_root else default_install_root(backend)
    binary_name = args.binary_name or default_binary_name(backend)
    service_name = args.service_name or f"{default_service_prefix(backend)}-{node.tag}"
    plan = DeployPlan(
        backend=backend,
        install_root=install_root,
        binary_name=binary_name,
        service_name=service_name,
        node=node,
        streaming_dns=streaming_dns,
    )
    return plan, server


def _build_plan_from_xray(args: argparse.Namespace) -> tuple[DeployPlan, str]:
    backend: BackendType = args.backend
    server = _resolve_server_address(args.server)
    region = _normalize_region(args.region)
    node_name = args.name or _default_name(args.role, region, backend)
    node = load_xray_reality_node(
        Path(args.input),
        name=node_name,
        tag=node_name.lower().replace(" ", "-"),
        role=args.role,
    )
    streaming_dns = _build_streaming_dns(
        backend,
        bool(args.enable_streaming_dns),
        args.streaming_dns,
        args.streaming_profile,
        args.streaming_domains,
        args.provider_label,
    )
    install_root = Path(args.install_root) if args.install_root else default_install_root(backend)
    binary_name = args.binary_name or default_binary_name(backend)
    service_name = args.service_name or f"{default_service_prefix(backend)}-{node.tag}"
    plan = DeployPlan(
        backend=backend,
        install_root=install_root,
        binary_name=binary_name,
        service_name=service_name,
        node=node,
        streaming_dns=streaming_dns,
    )
    return plan, server


def _write_bundle(plan: DeployPlan, server: str) -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    bundle_dir = OUTPUT_ROOT / plan.node.tag
    bundle_dir.mkdir(parents=True, exist_ok=True)
    config_path = bundle_dir / f"{plan.node.tag}.json"
    service_path = bundle_dir / f"{plan.service_name}.service"
    exports_path = bundle_dir / "exports.json"
    manifest_path = bundle_dir / "manifest.json"

    try:
        config_payload = build_config(plan)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc

    write_json(config_path, config_payload)
    service_path.write_text(
        build_service(
            plan.service_name,
            plan.binary_name,
            str(plan.install_root / f"{plan.node.tag}.json"),
            plan.backend,
        )
    )
    exports_path.write_text(
        json.dumps(
            {
                "shadowrocket_vless": export_vless_url(server, plan.node),
                "mihomo_proxy": export_mihomo_proxy(server, plan.node),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    write_json(manifest_path, build_manifest(plan, server))
    return bundle_dir


def _apply_plan_result(plan: DeployPlan, server: str, args: argparse.Namespace) -> dict:
    bundle_dir = _write_bundle(plan, server)
    install_root = plan.install_root
    install_root.mkdir(parents=True, exist_ok=True)
    final_config = install_root / f"{plan.node.tag}.json"
    final_service = Path("/etc/systemd/system") / f"{plan.service_name}.service"
    final_manifest = MANIFEST_ROOT / f"{plan.node.tag}.json"
    service_content = build_service(
        plan.service_name,
        plan.binary_name,
        str(final_config),
        plan.backend,
    )

    backup = backup_paths(
        plan.node.tag,
        [final_config, final_service, final_manifest],
        Path(args.backup_root),
    )

    try:
        config_payload = build_config(plan)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    write_json(final_config, config_payload)
    systemd_apply(plan.service_name, service_content, final_service)
    write_node_manifest(plan.node.tag, build_manifest(plan, server))

    if args.firewall:
        extra_ports = parse_port_list(args.extra_allow_ports)
        manifests = load_node_manifests()
        allow_ports = {
            22,
            plan.node.listen_port,
            *detect_ssh_ports(),
            *collect_manifest_ports(manifests),
            *extra_ports,
        }
        enforce_firewall_tcp_allowlist(sorted(allow_ports), extra_ports=extra_ports)
    else:
        allow_ports = []

    active, listening = wait_for_service(plan.service_name, plan.node.listen_port)
    _, enabled = systemd_status(plan.service_name)
    exports = json.loads((bundle_dir / "exports.json").read_text())
    return {
        "ok": True,
        "message": "部署完成",
        "backend": plan.backend,
        "version": installed_backend_version(plan.backend) or "unknown",
        "service": {
            "name": plan.service_name,
            "active": active,
            "enabled": enabled,
            "listening": listening,
        },
        "node": {
            "name": plan.node.name,
            "tag": plan.node.tag,
            "role": plan.node.role,
            "port": plan.node.listen_port,
            "domain": plan.node.server_name,
        },
        "paths": {
            "backup": str(backup),
            "config": str(final_config),
            "service": str(final_service),
            "manifest": str(final_manifest),
            "bundle_dir": str(bundle_dir),
        },
        "exports": exports,
        "firewall_ports": sorted(allow_ports),
    }


def _apply_plan(plan: DeployPlan, server: str, args: argparse.Namespace) -> int:
    result = _apply_plan_result(plan, server, args)
    info(f"backup: {result['paths']['backup']}")
    if result["firewall_ports"]:
        ok(f"firewall active allowlist: {result['firewall_ports']}")
    info(f"backend={result['backend']} version={result['version']}")
    info(
        "service active="
        f"{result['service']['active']} enabled={result['service']['enabled']} "
        f"listening={result['service']['listening']}"
    )
    info(f"config path: {result['paths']['config']}")
    info(f"service path: {result['paths']['service']}")
    info(f"manifest path: {result['paths']['manifest']}")
    info(f"vless: {result['exports']['shadowrocket_vless']}")
    return 0


def _node_from_manifest(payload: dict) -> NodeSpec:
    node = payload["node"]
    reality = node["reality"]
    return NodeSpec(
        tag=node["tag"],
        name=node["name"],
        role=node["role"],
        listen_port=int(node["listen_port"]),
        uuid=node["uuid"],
        server_name=node["server_name"],
        reality=RealityKeys(
            private_key=reality["private_key"],
            public_key=reality["public_key"],
            short_id=reality["short_id"],
        ),
        user_label=node["user_label"],
        enable_udp=bool(node.get("enable_udp", True)),
        detour_tag=node.get("detour_tag", "direct"),
        packet_encoding=node.get("packet_encoding", "xudp"),
        flow=node.get("flow", "xtls-rprx-vision"),
    )


def _streaming_dns_from_manifest(payload: dict) -> StreamingDnsSpec | None:
    raw = payload.get("streaming_dns")
    if not isinstance(raw, dict):
        return None
    return StreamingDnsSpec(
        provider_label=str(raw.get("provider_label") or "custom-streaming-dns"),
        dns_server=str(raw.get("dns_server") or ""),
        profile_name=str(raw.get("profile_name") or "common-media"),
        match_suffixes=[str(item) for item in raw.get("match_suffixes") or []],
    )


def _plan_from_manifest(payload: dict) -> DeployPlan:
    backend = str(payload.get("backend") or "sing-box")
    if backend not in {"sing-box", "xray"}:
        raise CommandError(f"不支持的后端: {backend}")
    return DeployPlan(
        backend=backend,  # type: ignore[arg-type]
        install_root=Path(str(payload["install_root"])),
        binary_name=str(payload.get("binary_name") or default_binary_name(backend)),  # type: ignore[arg-type]
        service_name=str(payload.get("service_name") or ""),
        node=_node_from_manifest(payload),
        streaming_dns=_streaming_dns_from_manifest(payload),
    )


def _node_summary(payload: dict) -> dict:
    node = payload["node"]
    return {
        "name": node["name"],
        "tag": node["tag"],
        "backend": payload.get("backend", "unknown"),
        "service": payload.get("service_name", ""),
        "port": int(node["listen_port"]),
        "role": node["role"],
        "server": payload.get("server", ""),
        "streaming_enabled": bool(payload.get("streaming_dns")),
    }


def _config_path_from_manifest(payload: dict) -> Path:
    install_root = Path(str(payload["install_root"]))
    tag = str(payload["node"]["tag"])
    return install_root / f"{tag}.json"


def _service_path_from_manifest(payload: dict) -> Path:
    service_name = str(payload.get("service_name") or "").strip()
    return Path("/etc/systemd/system") / f"{service_name}.service"


def _list_manifest_choices(manifests: list[dict]) -> None:
    for index, payload in enumerate(manifests, start=1):
        node = payload["node"]
        print(
            f"  {index}) {node['name']} | 后端={payload.get('backend', 'unknown')} | "
            f"服务={payload.get('service_name', 'unknown')} | 端口={node['listen_port']}"
        )


def _select_manifest(manifests: list[dict], prompt: str) -> dict:
    if not manifests:
        raise CommandError("未发现已部署节点")
    _list_manifest_choices(manifests)
    print("  0) 返回上一层")
    valid = {str(index) for index in range(1, len(manifests) + 1)}
    choice = _prompt_choice(prompt, valid, "1", allow_back=True)
    return manifests[int(choice) - 1]


def _print_bbr_summary(status: dict[str, str | bool]) -> None:
    print(f"当前拥塞控制: {status['current']}")
    print(f"系统支持项: {status['available']}")
    print(f"默认队列: {status['qdisc']}")
    print(f"支持 BBR: {status['has_bbr']}")
    print(f"已启用 BBR: {status['enabled']}")
    print(f"fq 就绪: {status['fq_ready']}")


def _bbr_status_result() -> dict:
    status = bbr_status()
    return {
        "kernel": kernel_release(),
        "bbr": status,
    }


def _show_links_result() -> dict:
    manifests = load_node_manifests()
    links = []
    for payload in manifests:
        node = _node_from_manifest(payload)
        server = payload.get("server") or _resolve_server_address(None)
        links.append(
            {
                "backend": payload.get("backend", "unknown"),
                "name": node.name,
                "tag": node.tag,
                "url": export_vless_url(server, node),
            }
        )
    return {"nodes": links}


def _show_status_result() -> dict:
    manifests = load_node_manifests()
    nodes = []
    for payload in manifests:
        summary = _node_summary(payload)
        active, enabled = systemd_status(summary["service"])
        listening = port_is_listening(summary["port"])
        summary.update(
            {
                "active": active,
                "enabled": enabled,
                "listening": listening,
            }
        )
        nodes.append(summary)
    return {
        "bbr": _bbr_status_result(),
        "nodes": nodes,
    }


def _firewall_result(allow_ports_raw: str, show_status: bool) -> dict:
    manifests = load_node_manifests()
    extra_ports = parse_port_list(allow_ports_raw)
    allow_ports = {
        22,
        *detect_ssh_ports(),
        *collect_manifest_ports(manifests),
        *extra_ports,
    }
    enforce_firewall_tcp_allowlist(sorted(allow_ports), extra_ports=extra_ports)
    return {
        "ok": True,
        "allow_ports": sorted(allow_ports),
        "extra_ports": extra_ports,
        "status": firewall_status() if show_status else "",
    }


def _show_logs_result(service_name: str, lines: int) -> dict:
    return {
        "service": service_name,
        "lines": lines,
        "logs": read_service_logs(service_name, lines),
    }


def _remove_node_result(tag: str) -> dict:
    manifests = load_node_manifests()
    payload = next((item for item in manifests if item.get("node", {}).get("tag") == tag), None)
    if not payload:
        raise CommandError(f"未找到节点: {tag}")
    node = payload["node"]
    service_name = str(payload.get("service_name") or "").strip()
    config_path = _config_path_from_manifest(payload)
    service_path = _service_path_from_manifest(payload)
    if service_name:
        stop_and_disable_service(service_name)
    if config_path.exists():
        config_path.unlink()
    if service_path.exists():
        service_path.unlink()
    remove_node_manifest(str(node["tag"]))
    remaining = load_node_manifests()
    extra_ports = load_firewall_extra_ports()
    allow_ports = {
        22,
        *detect_ssh_ports(),
        *collect_manifest_ports(remaining),
        *extra_ports,
    }
    enforce_firewall_tcp_allowlist(sorted(allow_ports), extra_ports=extra_ports)
    return {
        "ok": True,
        "removed": {
            "name": node["name"],
            "tag": node["tag"],
            "service": service_name,
            "config": str(config_path),
            "service_path": str(service_path),
        },
        "allow_ports": sorted(allow_ports),
    }


def _update_streaming_dns_result(
    tag: str,
    dns_server: str | None,
    profile_name: str,
    streaming_domains: str | None,
    disable: bool,
) -> dict:
    payload = next((item for item in load_node_manifests() if item.get("node", {}).get("tag") == tag), None)
    if not payload:
        raise CommandError(f"未找到节点: {tag}")
    plan = _plan_from_manifest(payload)
    if not plan.service_name:
        raise CommandError("当前节点缺少可用的服务名")
    if disable:
        plan.streaming_dns = None
    else:
        provider_label = "custom-streaming-dns"
        if isinstance(payload.get("streaming_dns"), dict):
            provider_label = str(payload["streaming_dns"].get("provider_label") or provider_label)
        plan.streaming_dns = _build_streaming_dns(
            plan.backend,
            True,
            dns_server,
            profile_name,
            streaming_domains,
            provider_label,
        )
    final_config = _config_path_from_manifest(payload)
    final_service = _service_path_from_manifest(payload)
    manifest_path = MANIFEST_ROOT / f"{plan.node.tag}.json"
    backup = backup_paths(plan.node.tag, [final_config, final_service, manifest_path], BACKUP_ROOT)
    write_json(final_config, build_config(plan))
    systemd_apply(
        plan.service_name,
        build_service(plan.service_name, plan.binary_name, str(final_config), plan.backend),
        final_service,
    )
    server = payload.get("server") or _resolve_server_address(None)
    write_node_manifest(plan.node.tag, build_manifest(plan, server))
    active, listening = wait_for_service(plan.service_name, plan.node.listen_port)
    _, enabled = systemd_status(plan.service_name)
    return {
        "ok": True,
        "backup": str(backup),
        "node": {"name": plan.node.name, "tag": plan.node.tag},
        "service": {
            "name": plan.service_name,
            "active": active,
            "enabled": enabled,
            "listening": listening,
        },
        "streaming_dns": build_manifest(plan, server)["streaming_dns"],
    }


def cmd_generate(args: argparse.Namespace) -> int:
    section("生成配置包")
    plan, server = _build_plan_from_args(args)
    bundle_dir = _write_bundle(plan, server)
    ok(f"配置包已写入: {bundle_dir}")
    return 0


def cmd_deploy_local(args: argparse.Namespace) -> int:
    section("部署本机节点")
    require_root()
    info(f"系统: {detect_os().get('PRETTY_NAME', 'unknown')}")
    if not args.skip_install_deps:
        _ensure_dependencies()
        ok("基础依赖已就绪")
    try:
        status = ensure_bbr_enabled()
        ok("BBR 已就绪")
        _print_bbr_summary(status)
    except Exception as exc:
        warn(f"BBR 自动启用已跳过: {exc}")
    if not args.skip_install_backend:
        version = install_backend(args.backend, args.backend_version)
        ok(f"{args.backend} 已就绪: v{version}")
    plan, server = _build_plan_from_args(args)
    return _apply_plan(plan, server, args)


def cmd_import_xray(args: argparse.Namespace) -> int:
    section("导入 Xray Reality")
    plan, server = _build_plan_from_xray(args)
    info(f"已导入 Xray 文件: {args.input}")
    if args.deploy_local:
        require_root()
        if not args.skip_install_deps:
            _ensure_dependencies()
            ok("基础依赖已就绪")
        try:
            status = ensure_bbr_enabled()
            ok("BBR 已就绪")
            _print_bbr_summary(status)
        except Exception as exc:
            warn(f"BBR 自动启用已跳过: {exc}")
        if not args.skip_install_backend:
            version = install_backend(args.backend, args.backend_version)
            ok(f"{args.backend} 已就绪: v{version}")
        return _apply_plan(plan, server, args)
    bundle_dir = _write_bundle(plan, server)
    ok(f"配置包已写入: {bundle_dir}")
    return 0


def cmd_firewall(args: argparse.Namespace) -> int:
    section("防火墙")
    require_root()
    result = _firewall_result(args.allow_ports, args.show_status)
    ok(f"当前 UFW 放行端口: {result['allow_ports']}")
    if result["status"]:
        print(result["status"])
    return 0


def cmd_bbr_status(_: argparse.Namespace) -> int:
    section("BBR 状态")
    result = _bbr_status_result()
    print(f"内核版本: {result['kernel']}")
    _print_bbr_summary(result["bbr"])
    return 0


def cmd_enable_bbr(_: argparse.Namespace) -> int:
    section("启用 BBR")
    require_root()
    status = enable_bbr()
    ok("BBR 设置已应用")
    _print_bbr_summary(status)
    return 0


def cmd_show_links(_: argparse.Namespace) -> int:
    section("VLESS 地址")
    result = _show_links_result()
    if not result["nodes"]:
        warn("未发现已部署节点")
        return 0
    for item in result["nodes"]:
        print(f"[{item['backend']}] {item['name']}")
        print(item["url"])
        print("")
    return 0


def cmd_show_logs(args: argparse.Namespace) -> int:
    section("节点日志")
    manifests = load_node_manifests()
    payload = _select_manifest(manifests, "请选择要查看日志的节点（默认 1）: ")
    service_name = str(payload.get("service_name") or "").strip()
    if not service_name:
        raise CommandError("选中的节点没有可用的 systemd 服务名")
    result = _show_logs_result(service_name, args.lines)
    print(result["logs"])
    return 0


def cmd_remove_node(args: argparse.Namespace) -> int:
    section("删除节点")
    require_root()
    manifests = load_node_manifests()
    payload = _select_manifest(manifests, "请选择要删除的节点（默认 1）: ")
    node = payload["node"]
    service_name = str(payload.get("service_name") or "").strip()
    config_path = _config_path_from_manifest(payload)
    manifest_path = MANIFEST_ROOT / f"{node['tag']}.json"
    print("即将删除：")
    print(f"  节点名称: {node['name']}")
    print(f"  服务名: {service_name}")
    print(f"  配置文件: {config_path}")
    print(f"  清单文件: {manifest_path}")
    confirm = _prompt_input("确认现在删除这个节点吗？[y/N]: ").strip().lower()
    if confirm != "y":
        warn("已取消删除")
        return 0
    result = _remove_node_result(str(node["tag"]))
    if service_name:
        ok(f"服务已移除: {service_name}")
    ok(f"配置已移除: {result['removed']['config']}")
    ok(f"服务文件已移除: {result['removed']['service_path']}")
    ok(f"当前 UFW 放行端口: {result['allow_ports']}")
    return 0


def cmd_show_status(_: argparse.Namespace) -> int:
    section("节点状态")
    result = _show_status_result()
    if not result["nodes"]:
        warn("未发现已部署节点")
        return 0
    _print_bbr_summary(result["bbr"]["bbr"])
    for item in result["nodes"]:
        print(
            f"{item['name']} | 后端={item['backend']} | 服务={item['service']} | "
            f"端口={item['port']} | 运行中={item['active']} | 开机自启={item['enabled']} | 端口监听={item['listening']}"
        )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    section("环境体检")
    info(f"系统: {detect_os().get('PRETTY_NAME', 'unknown')}")
    print(f"内核版本: {kernel_release()}")
    try:
        print(f"主 IPv4: {detect_primary_ipv4()}")
    except Exception:
        print("主 IPv4: 无法自动检测")
    print(f"SSH 端口: {detect_ssh_ports()}")
    print(f"UFW 状态: {firewall_status()}")
    _print_bbr_summary(bbr_status())
    manifests = load_node_manifests()
    service_names = [part.strip() for part in args.services.split(",") if part.strip()] or collect_manifest_services(manifests)
    ports = [int(part) for part in args.ports.split(",") if part.strip()] or collect_manifest_ports(manifests)
    for service in service_names:
        active, enabled = systemd_status(service)
        print(f"{service}: 运行中={active} 开机自启={enabled}")
    for port in ports:
        print(f"端口 {port}: 监听中={port_is_listening(port)}")
    return 0


def cmd_update_streaming_dns(args: argparse.Namespace) -> int:
    section("修改流媒体 DNS")
    require_root()
    result = _update_streaming_dns_result(
        args.tag,
        args.streaming_dns,
        args.streaming_profile,
        args.streaming_domains,
        args.disable,
    )
    ok("流媒体 DNS 已更新")
    print(f"节点名称: {result['node']['name']}")
    if result["streaming_dns"]:
        print(f"DNS 地址: {result['streaming_dns']['dns_server']}")
        print(f"规则: {result['streaming_dns']['profile_name']}")
    else:
        print("当前节点已关闭流媒体 DNS")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    section("备份")
    require_root()
    paths = [Path(part.strip()) for part in args.paths.split(",") if part.strip()]
    archive = backup_paths(args.label, paths, Path(args.backup_root))
    ok(f"备份已创建: {archive}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    section("恢复")
    require_root()
    restore_backup(Path(args.archive), Path(args.destination))
    ok(f"已恢复: {args.archive} -> {args.destination}")
    return 0


def cmd_backend_detect_region(_: argparse.Namespace) -> int:
    region, country = _detect_server_region_label()
    try:
        server_ip = detect_primary_ipv4()
    except Exception:
        server_ip = ""
    return _json_dump(
        {
            "ok": True,
            "region": region,
            "country": country or "",
            "server_ip": server_ip,
        }
    )


def cmd_backend_recommend_domains(args: argparse.Namespace) -> int:
    options = _recommended_reality_domains(args.region, limit=args.limit, timeout=args.timeout)
    return _json_dump(
        {
            "ok": True,
            "region": args.region,
            "domains": [
                {
                    "domain": item.domain,
                    "latency_ms": int(round((item.ttfb or 0) * 1000)) if item.ttfb is not None else None,
                    "ok": item.ok,
                }
                for item in options
            ],
        }
    )


def cmd_backend_list_nodes(_: argparse.Namespace) -> int:
    return _json_dump({"ok": True, "nodes": [_node_summary(item) for item in load_node_manifests()]})


def cmd_backend_show_links(_: argparse.Namespace) -> int:
    result = _show_links_result()
    result["ok"] = True
    return _json_dump(result)


def cmd_backend_show_status(_: argparse.Namespace) -> int:
    result = _show_status_result()
    result["ok"] = True
    return _json_dump(result)


def cmd_backend_show_logs(args: argparse.Namespace) -> int:
    service_name = args.service
    if args.tag:
        payload = next((item for item in load_node_manifests() if item.get("node", {}).get("tag") == args.tag), None)
        if not payload:
            raise CommandError(f"未找到节点: {args.tag}")
        service_name = str(payload.get("service_name") or "").strip()
    if not service_name:
        raise CommandError("必须提供 --service 或 --tag")
    result = _show_logs_result(service_name, args.lines)
    result["ok"] = True
    return _json_dump(result)


def cmd_backend_bbr_status(_: argparse.Namespace) -> int:
    result = _bbr_status_result()
    result["ok"] = True
    return _json_dump(result)


def cmd_backend_firewall(args: argparse.Namespace) -> int:
    require_root()
    result = _firewall_result(args.allow_ports, args.show_status)
    return _json_dump(result)


def cmd_backend_remove_node(args: argparse.Namespace) -> int:
    require_root()
    result = _remove_node_result(args.tag)
    return _json_dump(result)


def cmd_backend_update_streaming_dns(args: argparse.Namespace) -> int:
    require_root()
    result = _update_streaming_dns_result(
        args.tag,
        args.streaming_dns,
        args.streaming_profile,
        args.streaming_domains,
        args.disable,
    )
    return _json_dump(result)


def cmd_backend_deploy_local(args: argparse.Namespace) -> int:
    require_root()
    if not args.skip_install_deps:
        _ensure_dependencies()
    bbr = ensure_bbr_enabled()
    if not args.skip_install_backend:
        install_backend(args.backend, args.backend_version)
    plan, server = _build_plan_from_args(args)
    result = _apply_plan_result(plan, server, args)
    result["bbr"] = {
        "kernel": kernel_release(),
        "status": bbr,
    }
    return _json_dump(result)


def _prompt_choice(prompt: str, valid: set[str], default: str, allow_back: bool = False) -> str:
    raw = _prompt_input(prompt, allow_back=allow_back).strip()
    if not raw:
        return default
    if raw not in valid:
        raise CommandError(f"无效选项: {raw}")
    return raw


def _prompt_region(default_region: str = "us") -> str:
    raw = _prompt_input(f"地区标记（默认 {default_region}，输入 0 返回）: ", allow_back=True).strip().lower()
    return raw or default_region


def _detect_server_region_label() -> tuple[str, str | None]:
    try:
        server_ip = detect_primary_ipv4()
        detected = lookup_ip_metadata(server_ip)
        country = detected["country"] or detected["country_code"] or None
        return detected["probe_region"], country
    except Exception:
        return "us", None


def _prompt_streaming_profile() -> tuple[str, str | None]:
    print("流媒体规则：")
    print("  1) common-media (全部常见流媒体)")
    index_to_profile = {str(index): name for index, name in enumerate(sorted(STREAMING_PROFILES), start=1)}
    for index, profile in index_to_profile.items():
        print(f"  {index}) {profile}")
    print("  c) 自定义")
    print("  0) 返回上一层")
    choice = _prompt_input("请选择规则（默认 1）: ", allow_back=True).strip() or "1"
    if choice == "c":
        custom = _prompt_input("请输入自定义域名后缀（逗号分隔，输入 0 返回）: ", allow_back=True).strip()
        return "common-media", custom
    profile = index_to_profile.get(choice)
    if not profile:
        raise CommandError(f"无效的流媒体规则选项: {choice}")
    return profile, None


def _recommended_reality_domains(region: str, limit: int = 3, timeout: int = 4) -> list[ProbeResult]:
    candidates = candidate_pool_for_region(region)
    if not candidates:
        raise CommandError(f"当前地区没有内置候选域名池: {region}")
    info(f"正在并行测速内置 Reality 域名，地区池: {region}，候选数量: {len(candidates)}")
    ranked = rank_domains(candidates, timeout=timeout)
    selected = [item for item in ranked if item.ok][:limit]
    if not selected:
        raise CommandError(f"当前地区没有通过严格校验的 Reality 候选域名: {region}")
    return selected


def _prompt_reality_domain(region: str) -> str:
    options = _recommended_reality_domains(region)
    print("推荐的 Reality 域名：")
    valid_choices = set()
    for index, item in enumerate(options, start=1):
        valid_choices.add(str(index))
        if item.ok and item.ttfb is not None:
            latency = f"{int(round(item.ttfb * 1000))}ms"
        elif item.ttfb is not None:
            latency = f"{int(round(item.ttfb * 1000))}ms"
        else:
            latency = "测速失败"
        print(f"  {index}) {item.domain} | 延迟 {latency}")
    print("  0) 返回上一层")
    choice = _prompt_choice("请选择 Reality 域名（默认 1）: ", valid_choices, "1", allow_back=True)
    return options[int(choice) - 1].domain


def _interactive_deploy(backend: BackendType) -> int:
    section(f"部署 {backend} 节点")
    info("任意子项输入 0 可返回上一层")
    print("节点模式：")
    print("  1) 主节点")
    print("  2) 流媒体专用节点")
    print("  3) 主节点 + 流媒体 DNS")
    print("  0) 返回上一层")
    mode = _prompt_choice("请选择模式（默认 1）: ", {"1", "2", "3"}, "1", allow_back=True)
    role = "media" if mode == "2" else "main"
    enable_streaming_dns = mode in {"2", "3"}
    detected_region, detected_country = _detect_server_region_label()
    print(f"自动识别地区池: {detected_region}" + (f" ({detected_country})" if detected_country else ""))
    region = _prompt_region(detected_region)
    default_port = "2443" if role == "media" else "443"
    port = int(_prompt_input(f"监听端口（默认 {default_port}，输入 0 返回）: ", allow_back=True).strip() or default_port)
    validate_port(port)
    domain = _prompt_reality_domain(region)
    default_name = _default_name(role, region, backend)
    name = _prompt_input(f"节点名称（默认 {default_name}，输入 0 返回）: ", allow_back=True).strip() or default_name
    service_name = None
    extra_allow_ports = None
    streaming_dns = None
    streaming_profile = "common-media"
    streaming_domains = None
    if enable_streaming_dns:
        streaming_dns = _prompt_input("流媒体 DNS 地址（输入 0 返回）: ", allow_back=True).strip()
        if not streaming_dns:
            raise CommandError("当前模式必须填写流媒体 DNS 地址")
        streaming_profile, streaming_domains = _prompt_streaming_profile()
    print("")
    print("部署摘要：")
    print(f"  后端: {backend}")
    print(f"  节点类型: {role}")
    print(f"  地区标记: {region}")
    print(f"  监听端口: {port}")
    print(f"  Reality 域名: {domain}")
    print(f"  节点名称: {name}")
    if enable_streaming_dns:
        print(f"  流媒体 DNS: {streaming_dns}")
        print(f"  流媒体规则: {streaming_profile}")
        if streaming_domains:
            print(f"  自定义域名后缀: {streaming_domains}")
    confirm = _prompt_input("确认现在部署吗？[Y/n，输入 0 返回]: ", allow_back=True).strip().lower()
    if confirm == "n":
        warn("已取消部署")
        return 0
    args = argparse.Namespace(
        backend=backend,
        role=role,
        region=region,
        server=None,
        port=port,
        domain=domain,
        name=name,
        enable_streaming_dns=enable_streaming_dns,
        streaming_dns=streaming_dns,
        streaming_profile=streaming_profile,
        streaming_domains=streaming_domains,
        provider_label="custom-streaming-dns",
        install_root=None,
        binary_name=None,
        service_name=service_name,
        backup_root=str(BACKUP_ROOT),
        backend_version="latest",
        skip_install_deps=False,
        skip_install_backend=False,
        firewall=True,
        extra_allow_ports=extra_allow_ports,
    )
    return cmd_deploy_local(args)


def cmd_menu(_: argparse.Namespace) -> int:
    require_root()
    suppress_logo_once = os.environ.pop("SBOXCTL_SUPPRESS_MENU_LOGO_ONCE", "") == "1"
    while True:
        if suppress_logo_once:
            suppress_logo_once = False
        else:
            print_logo()
        print("1) 部署 sing-box 节点 (推荐)")
        print("2) 部署 xray 节点")
        print("3) 查看节点状态")
        print("4) 查看 VLESS 地址")
        print("5) 查看节点日志")
        print("6) 删除节点")
        print("7) 查看 BBR 状态")
        print("8) 调整防火墙")
        print("9) Reality 域名选择说明")
        print("0) 退出")
        choice = _prompt_input("请选择: ").strip() or "1"
        try:
            if choice == "1":
                _interactive_deploy("sing-box")
            elif choice == "2":
                _interactive_deploy("xray")
            elif choice == "3":
                cmd_show_status(argparse.Namespace())
            elif choice == "4":
                cmd_show_links(argparse.Namespace())
            elif choice == "5":
                cmd_show_logs(argparse.Namespace(lines=80))
            elif choice == "6":
                cmd_remove_node(argparse.Namespace())
            elif choice == "7":
                cmd_bbr_status(argparse.Namespace())
            elif choice == "8":
                raw = _prompt_input("额外放行端口【可留空，逗号分隔】: ").strip() or ""
                cmd_firewall(argparse.Namespace(allow_ports=raw, show_status=True))
            elif choice == "9":
                print("脚本会按服务器地区自动匹配内置地址池，并直接给出推荐编号。")
                print("对外默认只开放内置地址池，不让普通用户手填自定义域名。")
            elif choice == "0":
                return 0
            else:
                warn("未知选项")
        except BackToMenu:
            info("已返回上一层")
        except CommandError as exc:
            err(str(exc))
        print("")
        _prompt_input("按回车继续...")


def cmd_init(_: argparse.Namespace) -> int:
    print_logo()
    section("工具概览")
    info("服务器端一键部署工具，协议固定为 VLESS + Reality + Vision")
    info("默认后端: sing-box")
    info("同时支持 xray，部署流程保持一致")
    print("")
    print("服务器端启动命令：")
    print("  curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh | sudo bash")
    print("")
    print("常用命令：")
    print("  sboxctl menu")
    print("  sboxctl show-status")
    print("  sboxctl show-links")
    print("  sboxctl show-logs")
    print("  sudo sboxctl remove-node")
    print("  sboxctl bbr-status")
    print("  sudo sboxctl firewall --show-status")
    print("  sboxctl import-xray --input <XRAY_JSON> --role main --region <REGION_LABEL> --backend sing-box")
    return 0


def _remote_deploy_args(args: argparse.Namespace) -> list[str]:
    deploy_args = [
        "--backend",
        args.backend,
        "--role",
        args.role,
        "--region",
        args.region,
        "--port",
        str(args.port),
        "--domain",
        args.domain,
        "--backup-root",
        args.backup_root,
        "--backend-version",
        args.backend_version,
    ]
    if args.name:
        deploy_args.extend(["--name", args.name])
    if args.service_name:
        deploy_args.extend(["--service-name", args.service_name])
    if args.install_root:
        deploy_args.extend(["--install-root", args.install_root])
    if args.binary_name:
        deploy_args.extend(["--binary-name", args.binary_name])
    if args.enable_streaming_dns:
        deploy_args.append("--enable-streaming-dns")
    if args.streaming_dns:
        deploy_args.extend(["--streaming-dns", args.streaming_dns])
    if args.streaming_profile:
        deploy_args.extend(["--streaming-profile", args.streaming_profile])
    if args.streaming_domains:
        deploy_args.extend(["--streaming-domains", args.streaming_domains])
    if args.provider_label:
        deploy_args.extend(["--provider-label", args.provider_label])
    if args.skip_install_deps:
        deploy_args.append("--skip-install-deps")
    if args.skip_install_backend:
        deploy_args.append("--skip-install-backend")
    deploy_args.append("--firewall" if args.firewall else "--no-firewall")
    if args.extra_allow_ports:
        deploy_args.extend(["--extra-allow-ports", args.extra_allow_ports])
    return deploy_args


def cmd_deploy_remote(args: argparse.Namespace) -> int:
    section("远程部署节点")
    validate_port(args.port)
    validate_port(args.ssh_port)
    validate_domain(args.domain)
    host = f"{args.ssh_user}@{args.host}"
    archive = package_project(PROJECT_ROOT)
    remote_archive = f"{args.remote_dir.rstrip('/')}/sboxctl.tgz"
    remote_cmd = render_remote_deploy_command(
        args.remote_dir,
        remote_archive,
        _remote_deploy_args(args),
    )
    try:
        info(f"本地打包完成: {archive}")
        run_remote(host, args.ssh_port, render_prepare_remote_dir_command(args.remote_dir), args.identity_file, args.ssh_password)
        upload_archive(archive, host, remote_archive, args.ssh_port, args.identity_file, args.ssh_password)
        ok(f"已上传到 {host}:{remote_archive}")
        result = run_remote(host, args.ssh_port, remote_cmd, args.identity_file, args.ssh_password)
        sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
    finally:
        cleanup_local_archive(archive)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sboxctl")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="show overview")
    init.set_defaults(func=cmd_init)

    menu = sub.add_parser("menu", help="interactive server-side main menu")
    menu.set_defaults(func=cmd_menu)

    generate = sub.add_parser("generate", help="generate config, service and exports")
    generate.add_argument("--backend", choices=["sing-box", "xray"], default="sing-box")
    generate.add_argument("--role", choices=["main", "media"], required=True)
    generate.add_argument("--region", required=True)
    generate.add_argument("--server")
    generate.add_argument("--port", type=int, required=True)
    generate.add_argument("--domain", required=True)
    generate.add_argument("--name")
    generate.add_argument("--enable-streaming-dns", action="store_true")
    generate.add_argument("--streaming-dns")
    generate.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    generate.add_argument("--streaming-domains")
    generate.add_argument("--provider-label", default="custom-streaming-dns")
    generate.add_argument("--install-root")
    generate.add_argument("--binary-name")
    generate.add_argument("--service-name")
    generate.set_defaults(func=cmd_generate)

    deploy = sub.add_parser("deploy-local", help="deploy on the current server")
    deploy.add_argument("--backend", choices=["sing-box", "xray"], default="sing-box")
    deploy.add_argument("--role", choices=["main", "media"], required=True)
    deploy.add_argument("--region", required=True)
    deploy.add_argument("--server")
    deploy.add_argument("--port", type=int, required=True)
    deploy.add_argument("--domain", required=True)
    deploy.add_argument("--name")
    deploy.add_argument("--enable-streaming-dns", action="store_true")
    deploy.add_argument("--streaming-dns")
    deploy.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    deploy.add_argument("--streaming-domains")
    deploy.add_argument("--provider-label", default="custom-streaming-dns")
    deploy.add_argument("--install-root")
    deploy.add_argument("--binary-name")
    deploy.add_argument("--service-name")
    deploy.add_argument("--backup-root", default=str(BACKUP_ROOT))
    deploy.add_argument("--backend-version", default="latest")
    deploy.add_argument("--skip-install-deps", action="store_true")
    deploy.add_argument("--skip-install-backend", action="store_true")
    deploy.add_argument("--firewall", action=argparse.BooleanOptionalAction, default=True)
    deploy.add_argument("--extra-allow-ports")
    deploy.set_defaults(func=cmd_deploy_local)

    import_xray = sub.add_parser("import-xray", help="import old xray reality config")
    import_xray.add_argument("--input", required=True)
    import_xray.add_argument("--backend", choices=["sing-box", "xray"], default="sing-box")
    import_xray.add_argument("--role", choices=["main", "media"], required=True)
    import_xray.add_argument("--region", required=True)
    import_xray.add_argument("--server")
    import_xray.add_argument("--name")
    import_xray.add_argument("--enable-streaming-dns", action="store_true")
    import_xray.add_argument("--streaming-dns")
    import_xray.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    import_xray.add_argument("--streaming-domains")
    import_xray.add_argument("--provider-label", default="custom-streaming-dns")
    import_xray.add_argument("--install-root")
    import_xray.add_argument("--binary-name")
    import_xray.add_argument("--service-name")
    import_xray.add_argument("--backup-root", default=str(BACKUP_ROOT))
    import_xray.add_argument("--backend-version", default="latest")
    import_xray.add_argument("--skip-install-deps", action="store_true")
    import_xray.add_argument("--skip-install-backend", action="store_true")
    import_xray.add_argument("--deploy-local", action="store_true")
    import_xray.add_argument("--firewall", action=argparse.BooleanOptionalAction, default=True)
    import_xray.add_argument("--extra-allow-ports")
    import_xray.set_defaults(func=cmd_import_xray)

    deploy_remote = sub.add_parser("deploy-remote", help="advanced: push deploy from another machine")
    deploy_remote.add_argument("--host", required=True)
    deploy_remote.add_argument("--ssh-user", default="root")
    deploy_remote.add_argument("--ssh-port", type=int, default=22)
    deploy_remote.add_argument("--identity-file")
    deploy_remote.add_argument("--ssh-password")
    deploy_remote.add_argument("--remote-dir", default="/root/sboxctl-release")
    deploy_remote.add_argument("--backend", choices=["sing-box", "xray"], default="sing-box")
    deploy_remote.add_argument("--role", choices=["main", "media"], required=True)
    deploy_remote.add_argument("--region", required=True)
    deploy_remote.add_argument("--port", type=int, required=True)
    deploy_remote.add_argument("--domain", required=True)
    deploy_remote.add_argument("--name")
    deploy_remote.add_argument("--enable-streaming-dns", action="store_true")
    deploy_remote.add_argument("--streaming-dns")
    deploy_remote.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    deploy_remote.add_argument("--streaming-domains")
    deploy_remote.add_argument("--provider-label", default="custom-streaming-dns")
    deploy_remote.add_argument("--install-root")
    deploy_remote.add_argument("--binary-name")
    deploy_remote.add_argument("--service-name")
    deploy_remote.add_argument("--backup-root", default=str(BACKUP_ROOT))
    deploy_remote.add_argument("--backend-version", default="latest")
    deploy_remote.add_argument("--skip-install-deps", action="store_true")
    deploy_remote.add_argument("--skip-install-backend", action="store_true")
    deploy_remote.add_argument("--firewall", action=argparse.BooleanOptionalAction, default=True)
    deploy_remote.add_argument("--extra-allow-ports")
    deploy_remote.set_defaults(func=cmd_deploy_remote)

    show_status = sub.add_parser("show-status", help="show deployed node statuses")
    show_status.set_defaults(func=cmd_show_status)

    show_links = sub.add_parser("show-links", help="show deployed VLESS links")
    show_links.set_defaults(func=cmd_show_links)

    show_logs = sub.add_parser("show-logs", help="show recent logs for a deployed node service")
    show_logs.add_argument("--lines", type=int, default=80)
    show_logs.set_defaults(func=cmd_show_logs)

    remove_node = sub.add_parser("remove-node", help="remove one deployed node and refresh firewall")
    remove_node.set_defaults(func=cmd_remove_node)

    update_streaming = sub.add_parser("update-streaming-dns", help="update streaming dns for a deployed node")
    update_streaming.add_argument("--tag", required=True)
    update_streaming.add_argument("--streaming-dns")
    update_streaming.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    update_streaming.add_argument("--streaming-domains")
    update_streaming.add_argument("--disable", action="store_true")
    update_streaming.set_defaults(func=cmd_update_streaming_dns)

    doctor = sub.add_parser("doctor", help="inspect system and deployed nodes")
    doctor.add_argument("--services", default="")
    doctor.add_argument("--ports", default="")
    doctor.set_defaults(func=cmd_doctor)

    firewall = sub.add_parser("firewall", help="apply ufw allowlist for ssh and node ports")
    firewall.add_argument("--allow-ports", default="")
    firewall.add_argument("--show-status", action="store_true")
    firewall.set_defaults(func=cmd_firewall)

    bbr_show = sub.add_parser("bbr-status", help="show BBR status")
    bbr_show.set_defaults(func=cmd_bbr_status)

    bbr_enable = sub.add_parser("enable-bbr", help="enable bbr and fq")
    bbr_enable.set_defaults(func=cmd_enable_bbr)

    backup = sub.add_parser("backup", help="create a tar.gz backup")
    backup.add_argument("--label", required=True)
    backup.add_argument("--paths", required=True)
    backup.add_argument("--backup-root", default=str(BACKUP_ROOT))
    backup.set_defaults(func=cmd_backup)

    restore = sub.add_parser("restore", help="restore a tar.gz backup")
    restore.add_argument("--archive", required=True)
    restore.add_argument("--destination", required=True)
    restore.set_defaults(func=cmd_restore)

    backend_detect = sub.add_parser("backend-detect-region", help=argparse.SUPPRESS)
    backend_detect.set_defaults(func=cmd_backend_detect_region)

    backend_domains = sub.add_parser("backend-recommend-domains", help=argparse.SUPPRESS)
    backend_domains.add_argument("--region", required=True)
    backend_domains.add_argument("--limit", type=int, default=3)
    backend_domains.add_argument("--timeout", type=int, default=6)
    backend_domains.set_defaults(func=cmd_backend_recommend_domains)

    backend_nodes = sub.add_parser("backend-list-nodes", help=argparse.SUPPRESS)
    backend_nodes.set_defaults(func=cmd_backend_list_nodes)

    backend_links = sub.add_parser("backend-show-links", help=argparse.SUPPRESS)
    backend_links.set_defaults(func=cmd_backend_show_links)

    backend_status = sub.add_parser("backend-show-status", help=argparse.SUPPRESS)
    backend_status.set_defaults(func=cmd_backend_show_status)

    backend_logs = sub.add_parser("backend-show-logs", help=argparse.SUPPRESS)
    backend_logs.add_argument("--tag")
    backend_logs.add_argument("--service")
    backend_logs.add_argument("--lines", type=int, default=80)
    backend_logs.set_defaults(func=cmd_backend_show_logs)

    backend_bbr = sub.add_parser("backend-bbr-status", help=argparse.SUPPRESS)
    backend_bbr.set_defaults(func=cmd_backend_bbr_status)

    backend_firewall = sub.add_parser("backend-firewall", help=argparse.SUPPRESS)
    backend_firewall.add_argument("--allow-ports", default="")
    backend_firewall.add_argument("--show-status", action="store_true")
    backend_firewall.set_defaults(func=cmd_backend_firewall)

    backend_remove = sub.add_parser("backend-remove-node", help=argparse.SUPPRESS)
    backend_remove.add_argument("--tag", required=True)
    backend_remove.set_defaults(func=cmd_backend_remove_node)

    backend_update_streaming = sub.add_parser("backend-update-streaming-dns", help=argparse.SUPPRESS)
    backend_update_streaming.add_argument("--tag", required=True)
    backend_update_streaming.add_argument("--streaming-dns")
    backend_update_streaming.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    backend_update_streaming.add_argument("--streaming-domains")
    backend_update_streaming.add_argument("--disable", action="store_true")
    backend_update_streaming.set_defaults(func=cmd_backend_update_streaming_dns)

    backend_deploy = sub.add_parser("backend-deploy-local", help=argparse.SUPPRESS)
    backend_deploy.add_argument("--backend", choices=["sing-box", "xray"], default="sing-box")
    backend_deploy.add_argument("--role", choices=["main", "media"], required=True)
    backend_deploy.add_argument("--region", required=True)
    backend_deploy.add_argument("--server")
    backend_deploy.add_argument("--port", type=int, required=True)
    backend_deploy.add_argument("--domain", required=True)
    backend_deploy.add_argument("--name")
    backend_deploy.add_argument("--enable-streaming-dns", action="store_true")
    backend_deploy.add_argument("--streaming-dns")
    backend_deploy.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    backend_deploy.add_argument("--streaming-domains")
    backend_deploy.add_argument("--provider-label", default="custom-streaming-dns")
    backend_deploy.add_argument("--install-root")
    backend_deploy.add_argument("--binary-name")
    backend_deploy.add_argument("--service-name")
    backend_deploy.add_argument("--backup-root", default=str(BACKUP_ROOT))
    backend_deploy.add_argument("--backend-version", default="latest")
    backend_deploy.add_argument("--skip-install-deps", action="store_true")
    backend_deploy.add_argument("--skip-install-backend", action="store_true")
    backend_deploy.add_argument("--firewall", action=argparse.BooleanOptionalAction, default=True)
    backend_deploy.add_argument("--extra-allow-ports")
    backend_deploy.set_defaults(func=cmd_backend_deploy_local)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except KeyboardInterrupt:
        err("已取消操作")
        return 130
    except CommandError as exc:
        err(str(exc))
        return 1
    except Exception as exc:
        if os.environ.get("SBOXCTL_DEBUG") == "1":
            traceback.print_exc()
        else:
            err(f"脚本运行异常: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
