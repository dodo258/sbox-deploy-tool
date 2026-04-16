from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from .config_gen import build_config, build_manifest, build_service, write_json
from .crypto import generate_reality_keys
from .domain_probe import load_candidates, rank_domains
from .exports import export_mihomo_proxy, export_vless_url
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
    enforce_ufw_tcp_allowlist,
    ensure_apt_dependencies,
    ensure_bbr_enabled,
    install_backend,
    installed_backend_version,
    kernel_release,
    load_node_manifests,
    parse_port_list,
    port_is_listening,
    require_root,
    restore_backup,
    systemd_apply,
    systemd_status,
    ufw_status,
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


def _default_name(role: str, region: str, backend: BackendType) -> str:
    suffix = "main" if role == "main" else "media"
    return f"{region.upper()}-{backend}-{suffix}"


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
            "curl",
            "tar",
            "gzip",
            "unzip",
            "zip",
            "openssl",
            "jq",
            "ufw",
            "python3",
            "python3-cryptography",
        ]
    )


def _build_streaming_dns(
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
    node = _make_node(args.role, args.region, args.port, args.domain, args.name, backend)
    streaming_dns = _build_streaming_dns(
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
    node_name = args.name or _default_name(args.role, args.region, backend)
    node = load_xray_reality_node(
        Path(args.input),
        name=node_name,
        tag=node_name.lower().replace(" ", "-"),
        role=args.role,
    )
    streaming_dns = _build_streaming_dns(
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


def _apply_plan(plan: DeployPlan, server: str, args: argparse.Namespace) -> int:
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
    info(f"backup: {backup}")

    try:
        config_payload = build_config(plan)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    write_json(final_config, config_payload)
    systemd_apply(plan.service_name, service_content, final_service)
    write_node_manifest(plan.node.tag, build_manifest(plan, server))

    if args.firewall:
        manifests = load_node_manifests()
        allow_ports = {
            22,
            plan.node.listen_port,
            *detect_ssh_ports(),
            *collect_manifest_ports(manifests),
            *parse_port_list(args.extra_allow_ports),
        }
        enforce_ufw_tcp_allowlist(sorted(allow_ports))
        ok(f"firewall active allowlist: {sorted(allow_ports)}")

    active, listening = wait_for_service(plan.service_name, plan.node.listen_port)
    _, enabled = systemd_status(plan.service_name)
    exports = json.loads((bundle_dir / "exports.json").read_text())
    info(f"backend={plan.backend} version={installed_backend_version(plan.backend) or 'unknown'}")
    info(f"service active={active} enabled={enabled} listening={listening}")
    info(f"config path: {final_config}")
    info(f"service path: {final_service}")
    info(f"manifest path: {final_manifest}")
    info(f"vless: {exports['shadowrocket_vless']}")
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


def _print_bbr_summary(status: dict[str, str | bool]) -> None:
    print(f"bbr_current={status['current']}")
    print(f"bbr_available={status['available']}")
    print(f"default_qdisc={status['qdisc']}")
    print(f"bbr_has_support={status['has_bbr']}")
    print(f"bbr_enabled={status['enabled']}")
    print(f"bbr_fq_ready={status['fq_ready']}")


def _print_probe_help() -> None:
    section("Reality Local Probe")
    print("macOS / Linux:")
    print("  bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.sh) us")
    print("")
    print("Windows PowerShell:")
    print("  irm https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/scripts/probe-reality.ps1 | iex")
    print("")
    print("先在本地电脑优选，再把域名填回服务器端向导。")


def cmd_probe(args: argparse.Namespace) -> int:
    section("Reality Domain Probe")
    pools = load_candidates()
    domains = pools.get(args.region, [])
    if not domains:
        print(f"No candidates for region={args.region}")
        return 1
    results = rank_domains(domains, timeout=args.timeout)
    for item in results[: args.limit]:
        status = item.status_code if item.status_code is not None else "-"
        ttfb = f"{item.ttfb:.3f}" if item.ttfb is not None else "-"
        line = (
            f"{item.domain:28} score={item.score:6} tls13={item.tls13!s:5} "
            f"h2={item.h2!s:5} code={status:>3} ttfb={ttfb}"
        )
        if item.note:
            line += f" note={item.note}"
        print(line)
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    section("Generate Bundle")
    plan, server = _build_plan_from_args(args)
    bundle_dir = _write_bundle(plan, server)
    ok(f"bundle written: {bundle_dir}")
    return 0


def cmd_deploy_local(args: argparse.Namespace) -> int:
    section("Deploy Local Node")
    require_root()
    info(f"os: {detect_os().get('PRETTY_NAME', 'unknown')}")
    if not args.skip_install_deps:
        _ensure_dependencies()
        ok("dependencies ready")
    try:
        status = ensure_bbr_enabled()
        ok("bbr ready")
        _print_bbr_summary(status)
    except Exception as exc:
        warn(f"bbr auto-enable skipped: {exc}")
    if not args.skip_install_backend:
        version = install_backend(args.backend, args.backend_version)
        ok(f"{args.backend} ready: v{version}")
    plan, server = _build_plan_from_args(args)
    return _apply_plan(plan, server, args)


def cmd_import_xray(args: argparse.Namespace) -> int:
    section("Import Xray Reality")
    plan, server = _build_plan_from_xray(args)
    info(f"imported xray file: {args.input}")
    if args.deploy_local:
        require_root()
        if not args.skip_install_deps:
            _ensure_dependencies()
            ok("dependencies ready")
        try:
            status = ensure_bbr_enabled()
            ok("bbr ready")
            _print_bbr_summary(status)
        except Exception as exc:
            warn(f"bbr auto-enable skipped: {exc}")
        if not args.skip_install_backend:
            version = install_backend(args.backend, args.backend_version)
            ok(f"{args.backend} ready: v{version}")
        return _apply_plan(plan, server, args)
    bundle_dir = _write_bundle(plan, server)
    ok(f"bundle written: {bundle_dir}")
    return 0


def cmd_firewall(args: argparse.Namespace) -> int:
    section("Firewall")
    require_root()
    manifests = load_node_manifests()
    allow_ports = {
        22,
        *detect_ssh_ports(),
        *collect_manifest_ports(manifests),
        *parse_port_list(args.allow_ports),
    }
    enforce_ufw_tcp_allowlist(sorted(allow_ports))
    ok(f"firewall active allowlist: {sorted(allow_ports)}")
    if args.show_status:
        print(ufw_status())
    return 0


def cmd_bbr_status(_: argparse.Namespace) -> int:
    section("BBR Status")
    print(f"kernel={kernel_release()}")
    _print_bbr_summary(bbr_status())
    return 0


def cmd_enable_bbr(_: argparse.Namespace) -> int:
    section("Enable BBR")
    require_root()
    status = enable_bbr()
    ok("bbr settings applied")
    _print_bbr_summary(status)
    return 0


def cmd_show_links(_: argparse.Namespace) -> int:
    section("VLESS Links")
    manifests = load_node_manifests()
    if not manifests:
        warn("no deployed node manifests found")
        return 0
    for payload in manifests:
        node = _node_from_manifest(payload)
        server = payload.get("server") or _resolve_server_address(None)
        print(f"[{payload.get('backend', 'unknown')}] {node.name}")
        print(export_vless_url(server, node))
        print("")
    return 0


def cmd_show_status(_: argparse.Namespace) -> int:
    section("Node Status")
    manifests = load_node_manifests()
    if not manifests:
        warn("no deployed node manifests found")
        return 0
    _print_bbr_summary(bbr_status())
    for payload in manifests:
        node = payload["node"]
        backend = payload.get("backend", "unknown")
        service_name = payload.get("service_name", "")
        active, enabled = systemd_status(service_name)
        listening = port_is_listening(int(node["listen_port"]))
        print(
            f"{node['name']} | backend={backend} | service={service_name} | "
            f"port={node['listen_port']} | active={active} | enabled={enabled} | listening={listening}"
        )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    section("Doctor")
    info(f"os: {detect_os().get('PRETTY_NAME', 'unknown')}")
    print(f"kernel={kernel_release()}")
    try:
        print(f"primary_ipv4={detect_primary_ipv4()}")
    except Exception:
        print("primary_ipv4=unavailable")
    print(f"ssh_ports={detect_ssh_ports()}")
    print(f"ufw_status={ufw_status().splitlines()[0] if ufw_status() else 'unknown'}")
    _print_bbr_summary(bbr_status())
    manifests = load_node_manifests()
    service_names = [part.strip() for part in args.services.split(",") if part.strip()] or collect_manifest_services(manifests)
    ports = [int(part) for part in args.ports.split(",") if part.strip()] or collect_manifest_ports(manifests)
    for service in service_names:
        active, enabled = systemd_status(service)
        print(f"{service}: active={active} enabled={enabled}")
    for port in ports:
        print(f"port {port}: listening={port_is_listening(port)}")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    section("Backup")
    require_root()
    paths = [Path(part.strip()) for part in args.paths.split(",") if part.strip()]
    archive = backup_paths(args.label, paths, Path(args.backup_root))
    ok(f"backup created: {archive}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    section("Restore")
    require_root()
    restore_backup(Path(args.archive), Path(args.destination))
    ok(f"restored: {args.archive} -> {args.destination}")
    return 0


def _prompt_choice(prompt: str, valid: set[str], default: str) -> str:
    raw = input(prompt).strip()
    if not raw:
        return default
    if raw not in valid:
        raise CommandError(f"invalid choice: {raw}")
    return raw


def _prompt_region() -> str:
    return _prompt_choice("region [us/jp/sg] (default us): ", {"us", "jp", "sg"}, "us")


def _prompt_streaming_profile() -> tuple[str, str | None]:
    print("streaming profile:")
    print("  1) common-media (全部常见流媒体)")
    index_to_profile = {str(index): name for index, name in enumerate(sorted(STREAMING_PROFILES), start=1)}
    for index, profile in index_to_profile.items():
        print(f"  {index}) {profile}")
    print("  c) custom")
    choice = input("select profile (default 1): ").strip() or "1"
    if choice == "c":
        custom = input("custom domains (comma separated): ").strip()
        return "common-media", custom
    profile = index_to_profile.get(choice)
    if not profile:
        raise CommandError(f"invalid streaming profile selection: {choice}")
    return profile, None


def _interactive_deploy(backend: BackendType) -> int:
    section(f"Deploy {backend}")
    print("node mode:")
    print("  1) 主节点")
    print("  2) 流媒体专用节点")
    print("  3) 主节点 + 流媒体 DNS")
    mode = _prompt_choice("select mode (default 1): ", {"1", "2", "3"}, "1")
    role = "media" if mode == "2" else "main"
    enable_streaming_dns = mode in {"2", "3"}
    region = _prompt_region()
    default_port = "2443" if role == "media" else "443"
    port = int(input(f"listen port (default {default_port}): ").strip() or default_port)
    validate_port(port)
    domain = input("reality domain: ").strip()
    validate_domain(domain)
    default_name = _default_name(role, region, backend)
    name = input(f"node name (default {default_name}): ").strip() or default_name
    service_name = input("systemd service name [optional]: ").strip() or None
    extra_allow_ports = input("extra allow ports [optional, comma separated]: ").strip() or None
    streaming_dns = None
    streaming_profile = "common-media"
    streaming_domains = None
    if enable_streaming_dns:
        streaming_dns = input("streaming DNS address: ").strip()
        if not streaming_dns:
            raise CommandError("streaming DNS is required in media-enabled mode")
        streaming_profile, streaming_domains = _prompt_streaming_profile()
    print("")
    print("summary:")
    print(f"  backend: {backend}")
    print(f"  role: {role}")
    print(f"  region: {region}")
    print(f"  port: {port}")
    print(f"  reality domain: {domain}")
    print(f"  node name: {name}")
    if enable_streaming_dns:
        print(f"  streaming dns: {streaming_dns}")
        print(f"  streaming profile: {streaming_profile}")
        if streaming_domains:
            print(f"  custom domains: {streaming_domains}")
    confirm = input("deploy now? [Y/n]: ").strip().lower()
    if confirm == "n":
        warn("deployment canceled")
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
    while True:
        print_logo()
        print("1) 部署 sing-box 节点 (推荐)")
        print("2) 部署 xray 节点")
        print("3) 查看节点状态")
        print("4) 查看 VLESS 地址")
        print("5) 查看 BBR 状态")
        print("6) 调整防火墙")
        print("7) Reality 本地域名优选说明")
        print("0) 退出")
        choice = input("select: ").strip() or "1"
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
                cmd_bbr_status(argparse.Namespace())
            elif choice == "6":
                raw = input("extra allow ports [optional, comma separated]: ").strip() or ""
                cmd_firewall(argparse.Namespace(allow_ports=raw, show_status=True))
            elif choice == "7":
                _print_probe_help()
            elif choice == "0":
                return 0
            else:
                warn("unknown choice")
        except CommandError as exc:
            err(str(exc))
        print("")
        input("press Enter to continue...")


def cmd_init(_: argparse.Namespace) -> int:
    print_logo()
    section("Overview")
    info("server-side one-click deploy tool for VLESS + Reality + Vision")
    info("default backend: sing-box")
    info("also supports xray with the same node workflow")
    print("")
    print("Start on server:")
    print("  sudo bash <(curl -fsSL https://raw.githubusercontent.com/dodo258/sbox-deploy-tool/main/bootstrap.sh)")
    print("")
    print("Useful commands:")
    print("  ./bin/sboxctl menu")
    print("  ./bin/sboxctl show-status")
    print("  ./bin/sboxctl show-links")
    print("  ./bin/sboxctl bbr-status")
    print("  sudo ./bin/sboxctl firewall --show-status")
    print("  ./bin/sboxctl import-xray --input <XRAY_JSON> --role main --region us --backend sing-box")
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
    section("Deploy Remote Node")
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
        info(f"packaged: {archive}")
        run_remote(host, args.ssh_port, render_prepare_remote_dir_command(args.remote_dir), args.identity_file, args.ssh_password)
        upload_archive(archive, host, remote_archive, args.ssh_port, args.identity_file, args.ssh_password)
        ok(f"uploaded to {host}:{remote_archive}")
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

    probe = sub.add_parser("probe", help="probe candidate reality domains")
    probe.add_argument("--region", choices=["us", "jp", "sg"], required=True)
    probe.add_argument("--timeout", type=int, default=6)
    probe.add_argument("--limit", type=int, default=8)
    probe.set_defaults(func=cmd_probe)

    generate = sub.add_parser("generate", help="generate config, service and exports")
    generate.add_argument("--backend", choices=["sing-box", "xray"], default="sing-box")
    generate.add_argument("--role", choices=["main", "media"], required=True)
    generate.add_argument("--region", choices=["us", "jp", "sg"], required=True)
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
    deploy.add_argument("--region", choices=["us", "jp", "sg"], required=True)
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
    import_xray.add_argument("--region", choices=["us", "jp", "sg"], required=True)
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
    deploy_remote.add_argument("--region", choices=["us", "jp", "sg"], required=True)
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

    doctor = sub.add_parser("doctor", help="inspect system and deployed nodes")
    doctor.add_argument("--services", default="")
    doctor.add_argument("--ports", default="")
    doctor.set_defaults(func=cmd_doctor)

    firewall = sub.add_parser("firewall", help="enforce tcp allowlist with ufw")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
