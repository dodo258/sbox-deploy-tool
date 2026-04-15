from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from .config_gen import build_config, build_service, write_json
from .crypto import generate_reality_keys
from .domain_probe import load_candidates, rank_domains
from .exports import export_mihomo_proxy, export_vless_url
from .models import DeployPlan, NodeSpec, StreamingDnsSpec
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
    backup_paths,
    detect_os,
    detect_primary_ipv4,
    detect_ssh_ports,
    ensure_apt_dependencies,
    ensure_ufw_ports,
    install_singbox,
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
)
from .ui import info, ok, print_logo, section, warn


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "output"
BACKUP_ROOT = Path("/var/backups/sboxctl")


def _default_name(role: str, region: str) -> str:
    if role == "main":
        return f"{region.upper()}-main"
    return f"{region.upper()}-media"


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


def _make_node(role: str, region: str, port: int, domain: str, name: str | None) -> NodeSpec:
    keys = generate_reality_keys()
    node_name = name or _default_name(role, region)
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
    server = args.server or detect_primary_ipv4()
    node = _make_node(args.role, args.region, args.port, args.domain, args.name)
    dns = None
    if args.role == "media":
        if args.streaming_dns:
            suffixes = get_profile(args.streaming_profile)
            if args.streaming_domains:
                suffixes = [part.strip() for part in args.streaming_domains.split(",") if part.strip()]
            dns = StreamingDnsSpec(
                provider_label=args.provider_label,
                dns_server=args.streaming_dns,
                profile_name=args.streaming_profile,
                match_suffixes=suffixes,
            )
        else:
            warn("media role selected without --streaming-dns; node will behave like a normal node")
    plan = DeployPlan(
        install_root=Path(args.install_root),
        binary_name=args.binary_name,
        service_name=args.service_name or f"sing-box-{node.tag}",
        node=node,
        streaming_dns=dns,
    )
    return plan, server


def _write_bundle(plan: DeployPlan, server: str) -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    node = plan.node
    bundle_dir = OUTPUT_ROOT / node.tag
    bundle_dir.mkdir(parents=True, exist_ok=True)

    config = build_config(plan)
    config_path = bundle_dir / f"{node.tag}.json"
    service_path = bundle_dir / f"{plan.service_name}.service"
    exports_path = bundle_dir / "exports.json"

    write_json(config_path, config)
    service_path.write_text(
        build_service(
            plan.service_name,
            plan.binary_name,
            str(plan.install_root / f"{node.tag}.json"),
        )
    )
    exports_path.write_text(
        json.dumps(
            {
                "shadowrocket_vless": export_vless_url(server, node),
                "mihomo_proxy": export_mihomo_proxy(server, node),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    return bundle_dir


def cmd_generate(args: argparse.Namespace) -> int:
    section("Generate Deployment Bundle")
    plan, server = _build_plan_from_args(args)
    bundle_dir = _write_bundle(plan, server)
    ok(f"bundle written: {bundle_dir}")
    info(f"config:  {bundle_dir / (plan.node.tag + '.json')}")
    info(f"service: {bundle_dir / (plan.service_name + '.service')}")
    info(f"exports: {bundle_dir / 'exports.json'}")
    return 0


def cmd_install_deps(_: argparse.Namespace) -> int:
    section("Install Dependencies")
    require_root()
    ensure_apt_dependencies(
        [
            "ca-certificates",
            "curl",
            "tar",
            "gzip",
            "unzip",
            "openssl",
            "jq",
            "ufw",
            "python3",
            "python3-cryptography",
        ]
    )
    ok("dependencies installed")
    return 0


def cmd_install_singbox(args: argparse.Namespace) -> int:
    section("Install sing-box")
    require_root()
    version = install_singbox(args.version)
    ok(f"sing-box installed: v{version}")
    return 0


def cmd_deploy_local(args: argparse.Namespace) -> int:
    section("Deploy Local Node")
    require_root()
    os_info = detect_os()
    info(f"os: {os_info.get('PRETTY_NAME', 'unknown')}")
    if not args.skip_install_deps:
        ensure_apt_dependencies(
            [
                "ca-certificates",
                "curl",
                "tar",
                "gzip",
                "unzip",
                "openssl",
                "jq",
                "ufw",
                "python3",
                "python3-cryptography",
            ]
        )
        ok("dependencies ready")
    if not args.skip_install_singbox:
        version = install_singbox(args.singbox_version)
        ok(f"sing-box ready: v{version}")

    plan, server = _build_plan_from_args(args)
    bundle_dir = _write_bundle(plan, server)
    config_path = bundle_dir / f"{plan.node.tag}.json"
    service_content = build_service(plan.service_name, plan.binary_name, str(plan.install_root / f"{plan.node.tag}.json"))

    install_config_dir = plan.install_root
    install_config_dir.mkdir(parents=True, exist_ok=True)
    final_config = install_config_dir / f"{plan.node.tag}.json"
    final_service = Path("/etc/systemd/system") / f"{plan.service_name}.service"

    backup = backup_paths(
        plan.node.tag,
        [final_config, final_service],
        Path(args.backup_root),
    )
    info(f"backup: {backup}")

    write_json(final_config, build_config(plan))
    systemd_apply(plan.service_name, service_content, final_service)

    if args.firewall:
        allow_ports = {22, plan.node.listen_port, *detect_ssh_ports()}
        allow_ports.update(parse_port_list(args.extra_allow_ports))
        ensure_ufw_ports(sorted(allow_ports))
        ok(f"firewall allowed tcp ports: {sorted(allow_ports)}")

    active, listening = wait_for_service(plan.service_name, plan.node.listen_port)
    _, enabled = systemd_status(plan.service_name)
    exports = json.loads((bundle_dir / "exports.json").read_text())
    info(f"service active={active} enabled={enabled} listening={listening}")
    info(f"config path: {final_config}")
    info(f"service path: {final_service}")
    info(f"shadowrocket: {exports['shadowrocket_vless']}")
    return 0


def cmd_firewall(args: argparse.Namespace) -> int:
    section("Firewall")
    require_root()
    allow_ports = {22, *detect_ssh_ports()}
    allow_ports.update(parse_port_list(args.allow_ports))
    ensure_ufw_ports(sorted(allow_ports))
    ok(f"firewall allowed tcp ports: {sorted(allow_ports)}")
    if args.show_status:
        print(ufw_status())
    return 0


def _remote_deploy_args(args: argparse.Namespace) -> list[str]:
    deploy_args = [
        "--role",
        args.role,
        "--region",
        args.region,
        "--port",
        str(args.port),
        "--domain",
        args.domain,
        "--install-root",
        args.install_root,
        "--binary-name",
        args.binary_name,
        "--backup-root",
        args.backup_root,
        "--singbox-version",
        args.singbox_version,
    ]
    if args.name:
        deploy_args.extend(["--name", args.name])
    if args.service_name:
        deploy_args.extend(["--service-name", args.service_name])
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
    if args.skip_install_singbox:
        deploy_args.append("--skip-install-singbox")
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
        run_remote(
            host,
            args.ssh_port,
            render_prepare_remote_dir_command(args.remote_dir),
            args.identity_file,
            args.ssh_password,
        )
        upload_archive(archive, host, remote_archive, args.ssh_port, args.identity_file, args.ssh_password)
        ok(f"uploaded to {host}:{remote_archive}")
        result = run_remote(host, args.ssh_port, remote_cmd, args.identity_file, args.ssh_password)
        sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
    finally:
        cleanup_local_archive(archive)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    section("Doctor")
    os_info = detect_os()
    info(f"os: {os_info.get('PRETTY_NAME', 'unknown')}")
    print(f"ssh_ports={detect_ssh_ports()}")
    print(f"ufw_status={ufw_status().splitlines()[0] if ufw_status() else 'unknown'}")
    service_names = [part.strip() for part in args.services.split(",") if part.strip()]
    for service in service_names:
        active, enabled = systemd_status(service)
        print(f"{service}: active={active} enabled={enabled}")
    for port in [int(part) for part in args.ports.split(",") if part.strip()]:
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


def cmd_wizard(_: argparse.Namespace) -> int:
    print_logo()
    section("Interactive Wizard")
    role = input("role [main/media]: ").strip() or "main"
    region = input("region [us/jp/sg]: ").strip() or "us"
    domain = input("reality domain: ").strip()
    port = int((input("listen port: ").strip() or ("2443" if role == "media" else "443")))
    name = input("node name: ").strip() or _default_name(role, region)
    service_name = input("systemd service name [optional]: ").strip() or ""
    streaming_dns = ""
    streaming_profile = "common-media"
    streaming_domains = ""
    if role == "media":
        streaming_dns = input("streaming dns server: ").strip()
        if streaming_dns:
            profile_hint = "/".join(STREAMING_PROFILES.keys())
            streaming_profile = input(f"streaming profile [{profile_hint}] (default common-media): ").strip() or "common-media"
            streaming_domains = input("custom streaming domains (comma separated, optional): ").strip()
    firewall_answer = input("enable firewall auto-allow (22 + ssh ports + node port)? [Y/n]: ").strip().lower()
    args = argparse.Namespace(
        role=role,
        region=region,
        domain=domain,
        port=port,
        name=name,
        service_name=service_name or None,
        streaming_dns=streaming_dns or None,
        streaming_profile=streaming_profile,
        streaming_domains=streaming_domains or None,
        provider_label="custom-streaming-dns",
        install_root="/etc/sing-box",
        binary_name="sing-box",
        server=None,
        skip_install_deps=False,
        skip_install_singbox=False,
        singbox_version="latest",
        firewall=firewall_answer != "n",
        extra_allow_ports=None,
        backup_root=str(BACKUP_ROOT),
    )
    return cmd_deploy_local(args)


def cmd_init(_: argparse.Namespace) -> int:
    print_logo()
    section("First Version Scope")
    info("supported: Ubuntu/Debian + VLESS Reality Vision + sing-box")
    info("modes: wizard / deploy-local / media-dns node / domain probe / backup / restore / doctor")
    warn("online probe still depends on local network reachability")
    print("")
    print("Examples:")
    print("  sboxctl probe --region us")
    print("  sboxctl wizard")
    print("  sboxctl deploy-local --role main --region jp --port 443 --domain www.example.com")
    print("  sboxctl deploy-remote --host 203.0.113.10 --ssh-port 22 --ssh-user root --role main --region us --port 443 --domain www.example.com")
    print("  sboxctl deploy-local --role media --region us --port 2443 --domain www.example.com --streaming-dns 138.2.89.178 --streaming-profile common-media")
    print("  sboxctl firewall --allow-ports 443,2443")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sboxctl")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="show project scope and examples")
    init.set_defaults(func=cmd_init)

    wizard = sub.add_parser("wizard", help="interactive local deployment")
    wizard.set_defaults(func=cmd_wizard)

    probe = sub.add_parser("probe", help="probe candidate reality domains")
    probe.add_argument("--region", choices=["us", "jp", "sg"], required=True)
    probe.add_argument("--timeout", type=int, default=6)
    probe.add_argument("--limit", type=int, default=8)
    probe.set_defaults(func=cmd_probe)

    gen = sub.add_parser("generate", help="generate config, systemd unit and exports")
    gen.add_argument("--role", choices=["main", "media"], required=True)
    gen.add_argument("--region", choices=["us", "jp", "sg"], required=True)
    gen.add_argument("--server")
    gen.add_argument("--port", type=int, required=True)
    gen.add_argument("--domain", required=True)
    gen.add_argument("--name")
    gen.add_argument("--streaming-dns")
    gen.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    gen.add_argument("--streaming-domains")
    gen.add_argument("--provider-label", default="custom-streaming-dns")
    gen.add_argument("--install-root", default="/etc/sing-box")
    gen.add_argument("--binary-name", default="sing-box")
    gen.add_argument("--service-name")
    gen.set_defaults(func=cmd_generate)

    deps = sub.add_parser("install-deps", help="install required system dependencies")
    deps.set_defaults(func=cmd_install_deps)

    install_sb = sub.add_parser("install-singbox", help="install sing-box binary")
    install_sb.add_argument("--version", default="latest")
    install_sb.set_defaults(func=cmd_install_singbox)

    deploy = sub.add_parser("deploy-local", help="generate and install a local node on the current server")
    deploy.add_argument("--role", choices=["main", "media"], required=True)
    deploy.add_argument("--region", choices=["us", "jp", "sg"], required=True)
    deploy.add_argument("--server")
    deploy.add_argument("--port", type=int, required=True)
    deploy.add_argument("--domain", required=True)
    deploy.add_argument("--name")
    deploy.add_argument("--streaming-dns")
    deploy.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    deploy.add_argument("--streaming-domains")
    deploy.add_argument("--provider-label", default="custom-streaming-dns")
    deploy.add_argument("--install-root", default="/etc/sing-box")
    deploy.add_argument("--binary-name", default="sing-box")
    deploy.add_argument("--service-name")
    deploy.add_argument("--backup-root", default=str(BACKUP_ROOT))
    deploy.add_argument("--singbox-version", default="latest")
    deploy.add_argument("--skip-install-deps", action="store_true")
    deploy.add_argument("--skip-install-singbox", action="store_true")
    deploy.add_argument("--firewall", action=argparse.BooleanOptionalAction, default=True)
    deploy.add_argument("--extra-allow-ports")
    deploy.set_defaults(func=cmd_deploy_local)

    deploy_remote = sub.add_parser("deploy-remote", help="package the project and deploy to a remote host through ssh/scp")
    deploy_remote.add_argument("--host", required=True)
    deploy_remote.add_argument("--ssh-user", default="root")
    deploy_remote.add_argument("--ssh-port", type=int, default=22)
    deploy_remote.add_argument("--identity-file")
    deploy_remote.add_argument("--ssh-password")
    deploy_remote.add_argument("--remote-dir", default="/root/sboxctl-release")
    deploy_remote.add_argument("--role", choices=["main", "media"], required=True)
    deploy_remote.add_argument("--region", choices=["us", "jp", "sg"], required=True)
    deploy_remote.add_argument("--port", type=int, required=True)
    deploy_remote.add_argument("--domain", required=True)
    deploy_remote.add_argument("--name")
    deploy_remote.add_argument("--streaming-dns")
    deploy_remote.add_argument("--streaming-profile", choices=sorted(STREAMING_PROFILES), default="common-media")
    deploy_remote.add_argument("--streaming-domains")
    deploy_remote.add_argument("--provider-label", default="custom-streaming-dns")
    deploy_remote.add_argument("--install-root", default="/etc/sing-box")
    deploy_remote.add_argument("--binary-name", default="sing-box")
    deploy_remote.add_argument("--service-name")
    deploy_remote.add_argument("--backup-root", default=str(BACKUP_ROOT))
    deploy_remote.add_argument("--singbox-version", default="latest")
    deploy_remote.add_argument("--skip-install-deps", action="store_true")
    deploy_remote.add_argument("--skip-install-singbox", action="store_true")
    deploy_remote.add_argument("--firewall", action=argparse.BooleanOptionalAction, default=True)
    deploy_remote.add_argument("--extra-allow-ports")
    deploy_remote.set_defaults(func=cmd_deploy_remote)

    doctor = sub.add_parser("doctor", help="inspect service and port state")
    doctor.add_argument("--services", default="")
    doctor.add_argument("--ports", default="")
    doctor.set_defaults(func=cmd_doctor)

    firewall = sub.add_parser("firewall", help="apply SSH-safe UFW rules")
    firewall.add_argument("--allow-ports", default="")
    firewall.add_argument("--show-status", action="store_true")
    firewall.set_defaults(func=cmd_firewall)

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
