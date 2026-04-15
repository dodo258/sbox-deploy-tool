from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sbox_tool.config_gen import build_config, build_service, write_json
from sbox_tool.crypto import generate_reality_keys
from sbox_tool.exports import export_mihomo_proxy, export_vless_url
from sbox_tool.models import DeployPlan, NodeSpec, StreamingDnsSpec
from sbox_tool.profiles import get_profile
from sbox_tool.remote_ops import build_scp_base, render_prepare_remote_dir_command, render_remote_deploy_command
from sbox_tool.system_ops import install_singbox


class GenerationTests(unittest.TestCase):
    def make_node(self, role: str = "main", port: int = 443) -> NodeSpec:
        return NodeSpec(
            tag=f"{role}-node",
            name=f"{role}-node",
            role=role,  # type: ignore[arg-type]
            listen_port=port,
            uuid="11111111-1111-1111-1111-111111111111",
            server_name="www.example.com",
            reality=generate_reality_keys(),
            user_label=role,
        )

    def test_main_config(self) -> None:
        plan = DeployPlan(
            install_root=Path("/etc/sing-box"),
            binary_name="sing-box",
            service_name="sing-box-main",
            node=self.make_node("main", 443),
        )
        config = build_config(plan)
        self.assertEqual(config["inbounds"][0]["listen_port"], 443)
        self.assertEqual(config["route"]["rules"][0]["action"], "sniff")
        self.assertEqual(config["dns"]["final"], "local")

    def test_media_config(self) -> None:
        plan = DeployPlan(
            install_root=Path("/etc/sing-box"),
            binary_name="sing-box",
            service_name="sing-box-media",
            node=self.make_node("media", 2443),
            streaming_dns=StreamingDnsSpec(
                provider_label="nf",
                dns_server="138.2.89.178",
            ),
        )
        config = build_config(plan)
        self.assertEqual(config["dns"]["servers"][1]["tag"], "streaming-dns")
        suffix_rule = config["route"]["rules"][1]
        self.assertIn("netflix.com", suffix_rule["domain_suffix"])
        self.assertEqual(suffix_rule["server"], "streaming-dns")
        self.assertEqual(config["dns"]["servers"][1]["type"], "udp")

    def test_profiles(self) -> None:
        self.assertIn("disneyplus.com", get_profile("common-media"))
        self.assertIn("hbomax.com", get_profile("max"))

    def test_dns_server_port_parsing(self) -> None:
        plan = DeployPlan(
            install_root=Path("/etc/sing-box"),
            binary_name="sing-box",
            service_name="sing-box-media",
            node=self.make_node("media", 2443),
            streaming_dns=StreamingDnsSpec(
                provider_label="custom",
                dns_server="dns.example.com:5353",
            ),
        )
        config = build_config(plan)
        self.assertEqual(config["dns"]["servers"][1]["server"], "dns.example.com")
        self.assertEqual(config["dns"]["servers"][1]["server_port"], 5353)

    def test_exports(self) -> None:
        node = self.make_node("main", 443)
        url = export_vless_url("154.31.116.61", node)
        self.assertIn("vless://11111111-1111-1111-1111-111111111111@154.31.116.61:443", url)
        payload = export_mihomo_proxy("154.31.116.61", node)
        self.assertEqual(payload["server"], "154.31.116.61")
        self.assertEqual(payload["reality-opts"]["short-id"], node.reality.short_id)

    def test_service_render(self) -> None:
        service = build_service("sing-box-main", "sing-box", "/etc/sing-box/main.json")
        self.assertIn("ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/main.json", service)

    def test_write_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            write_json(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text())["a"], 1)

    @mock.patch("sbox_tool.system_ops.installed_singbox_version", return_value="1.13.8")
    @mock.patch("sbox_tool.system_ops.resolve_singbox_version", return_value="1.13.8")
    def test_install_singbox_skips_same_version(self, *_: object) -> None:
        with mock.patch("sbox_tool.system_ops.require_root"), mock.patch("sbox_tool.system_ops.urllib.request.urlretrieve") as urlretrieve:
            self.assertEqual(install_singbox("latest"), "1.13.8")
            urlretrieve.assert_not_called()

    def test_render_remote_deploy_command(self) -> None:
        command = render_remote_deploy_command(
            "/root/sboxctl-release",
            "/root/sboxctl-release/sboxctl.tgz",
            ["--role", "main", "--port", "443", "--domain", "www.example.com"],
        )
        self.assertIn("./bin/sboxctl deploy-local", command)
        self.assertIn("tar -xzf", command)
        self.assertIn("/root/sboxctl-release", command)

    @mock.patch("sbox_tool.remote_ops.shutil.which", return_value="/usr/bin/sshpass")
    def test_build_scp_base_with_password(self, _: object) -> None:
        cmd = build_scp_base(22, None, "secret")
        self.assertEqual(cmd[:3], ["sshpass", "-p", "secret"])

    def test_render_prepare_remote_dir_command(self) -> None:
        command = render_prepare_remote_dir_command("/root/sboxctl-release")
        self.assertEqual(command, "mkdir -p /root/sboxctl-release")


if __name__ == "__main__":
    unittest.main()
