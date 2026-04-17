from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .models import BackendType


MANIFEST_ROOT = Path("/etc/sboxctl/nodes")
FIREWALL_ROOT = Path("/etc/sboxctl/firewall")
FIREWALL_SERVICE_NAME = "sboxctl-firewall"
FIREWALL_EXTRA_PORTS_FILE = FIREWALL_ROOT / "extra_ports.json"


class CommandError(RuntimeError):
    pass


def run(cmd: list[str], check: bool = True, capture: bool = True, text: bool = True) -> subprocess.CompletedProcess:
    completed = subprocess.run(cmd, check=False, capture_output=capture, text=text)
    if check and completed.returncode != 0:
        raise CommandError((completed.stderr or completed.stdout or "").strip())
    return completed


def require_root() -> None:
    if os.geteuid() != 0:
        raise CommandError("this command must be run as root")


def detect_os() -> dict[str, str]:
    os_release = Path("/etc/os-release")
    data: dict[str, str] = {}
    if os_release.exists():
        for line in os_release.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v.strip('"')
    return data


def kernel_release() -> str:
    return platform.release()


def ensure_apt_dependencies(packages: list[str]) -> None:
    require_root()
    if shutil.which("apt-get") is None:
        raise CommandError("apt-get not found; first version supports Debian/Ubuntu only")
    missing = []
    for package in packages:
        completed = run(
            ["dpkg-query", "-W", "-f=${Status}", package],
            check=False,
        )
        if "install ok installed" not in (completed.stdout or ""):
            missing.append(package)
    if not missing:
        return
    run(["apt-get", "update", "-o", "Acquire::Retries=3", "-o", "Acquire::ForceIPv4=true"])
    run(["apt-get", "install", "-y", *missing])


def read_sysctl_value(key: str) -> str:
    if shutil.which("sysctl") is None:
        return ""
    completed = run(["sysctl", "-n", key], check=False)
    return (completed.stdout or "").strip()


def arch_slug_singbox() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    try:
        return mapping[machine]
    except KeyError as exc:
        raise CommandError(f"unsupported architecture: {machine}") from exc


def arch_slug_xray() -> str:
    machine = platform.machine().lower()
    mapping = {
        "x86_64": "64",
        "amd64": "64",
        "aarch64": "arm64-v8a",
        "arm64": "arm64-v8a",
    }
    try:
        return mapping[machine]
    except KeyError as exc:
        raise CommandError(f"unsupported architecture: {machine}") from exc


def resolve_singbox_version(version: str) -> str:
    if version != "latest":
        return version.removeprefix("v")
    with urllib.request.urlopen("https://api.github.com/repos/SagerNet/sing-box/releases/latest", timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    return payload["tag_name"].removeprefix("v")


def resolve_xray_version(version: str) -> str:
    if version != "latest":
        return version.removeprefix("v")
    with urllib.request.urlopen("https://api.github.com/repos/XTLS/Xray-core/releases/latest", timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    return payload["tag_name"].removeprefix("v")


def _installed_binary_version(binary: str, pattern: str) -> str | None:
    path = Path(f"/usr/local/bin/{binary}")
    if not path.exists():
        return None
    completed = run([str(path), "version"], check=False)
    output = (completed.stdout or completed.stderr or "").strip()
    match = re.search(pattern, output)
    if match:
        return match.group(1)
    return None


def installed_singbox_version() -> str | None:
    return _installed_binary_version("sing-box", r"sing-box version (\d+\.\d+\.\d+)")


def installed_xray_version() -> str | None:
    return _installed_binary_version("xray", r"\b(\d+\.\d+\.\d+)\b")


def install_singbox(version: str = "latest") -> str:
    require_root()
    resolved = resolve_singbox_version(version)
    current = installed_singbox_version()
    if current == resolved:
        return resolved
    arch = arch_slug_singbox()
    url = f"https://github.com/SagerNet/sing-box/releases/download/v{resolved}/sing-box-{resolved}-linux-{arch}.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        tarball = Path(tmp) / "sing-box.tar.gz"
        extracted = Path(tmp) / "extract"
        extracted.mkdir()
        urllib.request.urlretrieve(url, tarball)
        with tarfile.open(tarball, "r:gz") as tf:
            tf.extractall(extracted)
        binary = next(extracted.rglob("sing-box"))
        shutil.copy2(binary, "/usr/local/bin/sing-box")
        os.chmod("/usr/local/bin/sing-box", 0o755)
    return resolved


def install_xray(version: str = "latest") -> str:
    require_root()
    resolved = resolve_xray_version(version)
    current = installed_xray_version()
    if current == resolved:
        return resolved
    arch = arch_slug_xray()
    url = f"https://github.com/XTLS/Xray-core/releases/download/v{resolved}/Xray-linux-{arch}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "xray.zip"
        extracted = Path(tmp) / "extract"
        extracted.mkdir()
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extracted)
        binary = extracted / "xray"
        if not binary.exists():
            raise CommandError("downloaded xray archive did not contain xray binary")
        shutil.copy2(binary, "/usr/local/bin/xray")
        os.chmod("/usr/local/bin/xray", 0o755)
    return resolved


def install_backend(backend: BackendType, version: str = "latest") -> str:
    if backend == "sing-box":
        return install_singbox(version)
    return install_xray(version)


def installed_backend_version(backend: BackendType) -> str | None:
    if backend == "sing-box":
        return installed_singbox_version()
    return installed_xray_version()


def default_install_root(backend: BackendType) -> Path:
    return Path("/etc/sing-box" if backend == "sing-box" else "/etc/xray")


def default_binary_name(backend: BackendType) -> str:
    return "sing-box" if backend == "sing-box" else "xray"


def default_service_prefix(backend: BackendType) -> str:
    return "sing-box" if backend == "sing-box" else "xray"


def detect_primary_ipv4() -> str:
    out = run(["bash", "-lc", "ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if ($i==\"src\") print $(i+1)}'"], capture=True).stdout.strip()
    if out:
        return out
    raise CommandError("unable to detect primary IPv4")


def detect_ssh_ports() -> list[int]:
    ports: set[int] = {22}
    sshd = shutil.which("sshd")
    if sshd:
        completed = subprocess.run([sshd, "-T"], check=False, capture_output=True, text=True)
        for line in completed.stdout.splitlines():
            if line.startswith("port "):
                try:
                    ports.add(int(line.split()[1]))
                except ValueError:
                    pass
    config = Path("/etc/ssh/sshd_config")
    if config.exists():
        for line in config.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("port "):
                try:
                    ports.add(int(line.split()[1]))
                except ValueError:
                    pass
    return sorted(ports)


def parse_port_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    ports: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            continue
        try:
            port = int(token)
        except ValueError as exc:
            raise CommandError(f"invalid port value: {token}") from exc
        validate_port(port)
        ports.append(port)
    return sorted(set(ports))


def validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise CommandError(f"port out of range: {port}")


def validate_domain(domain: str) -> None:
    pattern = r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
    if not re.fullmatch(pattern, domain):
        raise CommandError(f"invalid domain: {domain}")


def summarize_bbr_status(current: str, available: str, qdisc: str) -> dict[str, str | bool]:
    available_set = {item.strip() for item in available.split() if item.strip()}
    return {
        "current": current or "unknown",
        "available": available or "unknown",
        "qdisc": qdisc or "unknown",
        "has_bbr": "bbr" in available_set,
        "enabled": current == "bbr" and "bbr" in available_set,
        "fq_ready": qdisc == "fq",
    }


def bbr_status() -> dict[str, str | bool]:
    current = read_sysctl_value("net.ipv4.tcp_congestion_control")
    available = read_sysctl_value("net.ipv4.tcp_available_congestion_control")
    qdisc = read_sysctl_value("net.core.default_qdisc")
    return summarize_bbr_status(current, available, qdisc)


def enable_bbr(sysctl_conf: Path = Path("/etc/sysctl.d/99-sboxctl-bbr.conf")) -> dict[str, str | bool]:
    require_root()
    if shutil.which("modprobe") is not None:
        run(["modprobe", "tcp_bbr"], check=False)
    sysctl_conf.write_text(
        "\n".join(
            [
                "net.core.default_qdisc=fq",
                "net.ipv4.tcp_congestion_control=bbr",
                "",
            ]
        )
    )
    run(["sysctl", "--system"])
    status = bbr_status()
    if not status["has_bbr"]:
        raise CommandError("kernel does not report bbr support after applying sysctl")
    return status


def ensure_bbr_enabled() -> dict[str, str | bool]:
    status = bbr_status()
    if not status["enabled"] or not status["fq_ready"]:
        return enable_bbr()
    return status


def save_firewall_extra_ports(ports: list[int]) -> None:
    require_root()
    FIREWALL_ROOT.mkdir(parents=True, exist_ok=True)
    FIREWALL_EXTRA_PORTS_FILE.write_text(json.dumps(sorted(set(ports)), ensure_ascii=False) + "\n")


def load_firewall_extra_ports() -> list[int]:
    if not FIREWALL_EXTRA_PORTS_FILE.exists():
        return []
    try:
        payload = json.loads(FIREWALL_EXTRA_PORTS_FILE.read_text())
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    ports: list[int] = []
    for item in payload:
        try:
            ports.append(int(item))
        except Exception:
            continue
    return sorted(set(ports))


def _parse_ufw_allowed_ports(status_output: str) -> list[int]:
    ports: list[int] = []
    for line in status_output.splitlines():
        match = re.search(r"(\d+)/tcp\b", line)
        if match:
            ports.append(int(match.group(1)))
    return sorted(set(ports))


def enforce_firewall_tcp_allowlist(ports: list[int], extra_ports: list[int] | None = None) -> None:
    require_root()
    ensure_apt_dependencies(["ufw"])
    FIREWALL_ROOT.mkdir(parents=True, exist_ok=True)
    if extra_ports is not None:
        save_firewall_extra_ports(extra_ports)
    elif not FIREWALL_EXTRA_PORTS_FILE.exists():
        save_firewall_extra_ports([])

    if (Path("/etc/systemd/system") / f"{FIREWALL_SERVICE_NAME}.service").exists():
        stop_and_disable_service(FIREWALL_SERVICE_NAME)

    run(["ufw", "--force", "reset"])
    run(["ufw", "default", "deny", "incoming"])
    run(["ufw", "default", "allow", "outgoing"])
    for port in sorted(set(ports)):
        run(["ufw", "allow", f"{port}/tcp"])
    run(["ufw", "--force", "enable"])


def backup_paths(label: str, paths: list[Path], backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    target = backup_root / f"{label}-{stamp}.tar.gz"
    with tarfile.open(target, "w:gz") as tf:
        for path in paths:
            if path.exists():
                tf.add(path, arcname=path.name)
    return target


def restore_backup(archive: Path, destination: Path) -> None:
    require_root()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(destination)


def systemd_apply(service_name: str, service_content: str, service_path: Path) -> None:
    require_root()
    service_path.write_text(service_content)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", service_name])
    run(["systemctl", "restart", service_name])


def systemd_status(service_name: str) -> tuple[str, str]:
    if shutil.which("systemctl") is None:
        return "unavailable", "unavailable"
    active = run(["systemctl", "is-active", service_name], check=False).stdout.strip()
    enabled = run(["systemctl", "is-enabled", service_name], check=False).stdout.strip()
    return active, enabled


def stop_and_disable_service(service_name: str) -> None:
    if shutil.which("systemctl") is None:
        raise CommandError("systemctl not found")
    run(["systemctl", "disable", "--now", service_name], check=False)
    service_path = Path("/etc/systemd/system") / f"{service_name}.service"
    if service_path.exists():
        service_path.unlink()
    run(["systemctl", "daemon-reload"], check=False)


def read_service_logs(service_name: str, lines: int = 80) -> str:
    if shutil.which("journalctl") is None:
        raise CommandError("journalctl not found")
    completed = run(
        ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager"],
        check=False,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    if not output or output == "-- No entries --":
        return "当前节点暂无日志"
    if "No entries" in output:
        return "当前节点暂无日志"
    return output


def port_is_listening(port: int) -> bool:
    if shutil.which("ss") is None:
        return False
    completed = run(["bash", "-lc", f"ss -ltn '( sport = :{port} )' | tail -n +2"], check=False)
    return bool(completed.stdout.strip())


def firewall_status() -> str:
    if shutil.which("ufw") is None:
        return "ufw=未安装"
    completed = run(["ufw", "status"], check=False)
    output = (completed.stdout or completed.stderr or "").strip()
    ports = _parse_ufw_allowed_ports(output)
    if not output:
        return "ufw=状态未知"
    first = output.splitlines()[0].strip().lower()
    if "active" in first:
        state = "已开启"
    elif "inactive" in first:
        state = "未开启"
    else:
        state = output.splitlines()[0].strip()
    return f"ufw={state} | tcp放行={ports}"


def load_firewall_ports() -> list[int]:
    if shutil.which("ufw") is None:
        return []
    completed = run(["ufw", "status"], check=False)
    output = (completed.stdout or completed.stderr or "").strip()
    return _parse_ufw_allowed_ports(output)


def wait_for_service(service_name: str, port: int, timeout: int = 12) -> tuple[str, bool]:
    end = dt.datetime.utcnow().timestamp() + timeout
    last_active = "unknown"
    while dt.datetime.utcnow().timestamp() < end:
        active, _ = systemd_status(service_name)
        last_active = active
        if active == "active" and port_is_listening(port):
            return active, True
        subprocess.run(["sleep", "1"], check=False)
    return last_active, port_is_listening(port)


def write_node_manifest(tag: str, payload: dict, manifest_root: Path = MANIFEST_ROOT) -> Path:
    require_root()
    manifest_root.mkdir(parents=True, exist_ok=True)
    target = manifest_root / f"{tag}.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return target


def remove_node_manifest(tag: str, manifest_root: Path = MANIFEST_ROOT) -> bool:
    require_root()
    target = manifest_root / f"{tag}.json"
    if not target.exists():
        return False
    target.unlink()
    return True


def load_node_manifests(manifest_root: Path = MANIFEST_ROOT) -> list[dict]:
    if not manifest_root.exists():
        return []
    payloads: list[dict] = []
    for path in sorted(manifest_root.glob("*.json")):
        try:
            payloads.append(json.loads(path.read_text()))
        except Exception:
            continue
    return payloads


def collect_manifest_ports(manifests: list[dict]) -> list[int]:
    ports: list[int] = []
    for item in manifests:
        try:
            ports.append(int(item["node"]["listen_port"]))
        except Exception:
            continue
    return sorted(set(ports))


def collect_manifest_services(manifests: list[dict]) -> list[str]:
    services: list[str] = []
    for item in manifests:
        name = str(item.get("service_name") or "").strip()
        if name:
            services.append(name)
    return sorted(set(services))
