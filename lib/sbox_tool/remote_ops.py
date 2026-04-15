from __future__ import annotations

import shlex
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .system_ops import CommandError, run


EXCLUDE_NAMES = {".git", "__pycache__", ".DS_Store", "output"}


def package_project(project_root: Path) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix="sboxctl-", suffix=".tgz")
    Path(raw_path).unlink(missing_ok=True)
    archive = Path(raw_path)
    with tarfile.open(archive, "w:gz") as tf:
        for path in project_root.iterdir():
            if path.name in EXCLUDE_NAMES:
                continue
            tf.add(path, arcname=path.name)
    return archive


def _sshpass_prefix(ssh_password: str | None) -> list[str]:
    if not ssh_password:
        return []
    if shutil.which("sshpass") is None:
        raise CommandError("sshpass not found; install it locally or use key-based ssh")
    return ["sshpass", "-p", ssh_password]


def build_ssh_base(host: str, port: int, identity_file: str | None = None, ssh_password: str | None = None) -> list[str]:
    cmd = _sshpass_prefix(ssh_password) + [
        "ssh",
        "-p",
        str(port),
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if identity_file:
        cmd.extend(["-i", identity_file])
    cmd.append(host)
    return cmd


def build_scp_base(port: int, identity_file: str | None = None, ssh_password: str | None = None) -> list[str]:
    cmd = _sshpass_prefix(ssh_password) + [
        "scp",
        "-P",
        str(port),
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if identity_file:
        cmd.extend(["-i", identity_file])
    return cmd


def upload_archive(local_archive: Path, host: str, remote_archive: str, port: int, identity_file: str | None = None, ssh_password: str | None = None) -> None:
    cmd = build_scp_base(port, identity_file, ssh_password)
    cmd.extend([str(local_archive), f"{host}:{remote_archive}"])
    run(cmd, capture=True)


def run_remote(host: str, port: int, remote_command: str, identity_file: str | None = None, ssh_password: str | None = None) -> subprocess.CompletedProcess:
    cmd = build_ssh_base(host, port, identity_file, ssh_password)
    cmd.append(remote_command)
    return run(cmd, capture=True)


def render_remote_deploy_command(remote_dir: str, remote_archive: str, deploy_args: list[str]) -> str:
    quoted_dir = shlex.quote(remote_dir)
    quoted_archive = shlex.quote(remote_archive)
    deploy = " ".join(shlex.quote(part) for part in deploy_args)
    return "set -e; mkdir -p {dir}; tar -xzf {archive} -C {dir}; cd {dir}; ./bin/sboxctl deploy-local {deploy}".format(
        dir=quoted_dir,
        archive=quoted_archive,
        deploy=deploy,
    )


def render_prepare_remote_dir_command(remote_dir: str) -> str:
    quoted_dir = shlex.quote(remote_dir)
    return f"mkdir -p {quoted_dir}"


def cleanup_local_archive(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise CommandError(f"failed to remove temp archive: {path}") from exc
