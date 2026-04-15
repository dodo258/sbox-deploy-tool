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
from pathlib import Path


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
    run(["apt-get", "update"])
    run(["apt-get", "install", "-y", *packages])


def read_sysctl_value(key: str) -> str:
    if shutil.which("sysctl") is None:
        return ""
    completed = run(["sysctl", "-n", key], check=False)
    return (completed.stdout or "").strip()


def arch_slug() -> str:
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


def resolve_singbox_version(version: str) -> str:
    if version != "latest":
        return version.removeprefix("v")
    with urllib.request.urlopen("https://api.github.com/repos/SagerNet/sing-box/releases/latest", timeout=15) as resp:
        payload = json.loads(resp.read().decode())
    tag = payload["tag_name"]
    return tag.removeprefix("v")


def installed_singbox_version() -> str | None:
    binary = Path("/usr/local/bin/sing-box")
    if not binary.exists():
        return None
    completed = run([str(binary), "version"], check=False)
    output = (completed.stdout or completed.stderr or "").strip()
    match = re.search(r"sing-box version (\d+\.\d+\.\d+)", output)
    if match:
        return match.group(1)
    return None


def install_singbox(version: str = "latest") -> str:
    require_root()
    resolved = resolve_singbox_version(version)
    current = installed_singbox_version()
    if current == resolved:
        return resolved
    arch = arch_slug()
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


def ensure_ufw_ports(ports: list[int]) -> None:
    require_root()
    if shutil.which("ufw") is None:
        raise CommandError("ufw not found")
    for port in sorted(set(ports)):
        run(["ufw", "allow", f"{port}/tcp"])
    run(["ufw", "default", "deny", "incoming"])
    run(["ufw", "default", "allow", "outgoing"])
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


def port_is_listening(port: int) -> bool:
    if shutil.which("ss") is None:
        return False
    completed = run(["bash", "-lc", f"ss -ltn '( sport = :{port} )' | tail -n +2"], check=False)
    return bool(completed.stdout.strip())


def ufw_status() -> str:
    if shutil.which("ufw") is None:
        return "unavailable"
    return run(["ufw", "status"], check=False).stdout.strip()


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
