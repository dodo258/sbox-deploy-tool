from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sbox_tool.config_gen import build_config, build_service, write_json
from sbox_tool.cli import _build_streaming_dns
from sbox_tool.crypto import generate_reality_keys, reality_keys_from_existing
from sbox_tool.exports import export_mihomo_proxy, export_vless_url
from sbox_tool.models import DeployPlan, NodeSpec, StreamingDnsSpec
from sbox_tool.profiles import get_profile
from sbox_tool.remote_ops import build_scp_base, render_prepare_remote_dir_command, render_remote_deploy_command
from sbox_tool.system_ops import _render_iptables_rules, install_singbox, load_firewall_ports, summarize_bbr_status
from sbox_tool.xray_import import load_xray_reality_node


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
            backend="sing-box",
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
            backend="sing-box",
            install_root=Path("/etc/sing-box"),
            binary_name="sing-box",
            service_name="sing-box-media",
            node=self.make_node("media", 2443),
            streaming_dns=StreamingDnsSpec(
                provider_label="nf",
                dns_server="192.0.2.53",
            ),
        )
        config = build_config(plan)
        self.assertEqual(config["dns"]["servers"][1]["tag"], "streaming-dns")
        suffix_rule = config["route"]["rules"][1]
        self.assertIn("netflix.com", suffix_rule["domain_suffix"])
        self.assertEqual(suffix_rule["server"], "streaming-dns")
        self.assertEqual(config["dns"]["servers"][1]["type"], "udp")

    def test_xray_media_config(self) -> None:
        plan = DeployPlan(
            backend="xray",
            install_root=Path("/etc/xray"),
            binary_name="xray",
            service_name="xray-media",
            node=self.make_node("media", 2443),
            streaming_dns=StreamingDnsSpec(
                provider_label="nf",
                dns_server="192.0.2.53",
            ),
        )
        config = build_config(plan)
        self.assertEqual(config["inbounds"][0]["protocol"], "vless")
        self.assertEqual(config["dns"]["servers"][1]["address"], "192.0.2.53")
        self.assertIn("domain:netflix.com", config["dns"]["servers"][1]["domains"])

    def test_profiles(self) -> None:
        self.assertIn("disneyplus.com", get_profile("common-media"))
        self.assertIn("hbomax.com", get_profile("max"))

    def test_dns_server_port_parsing(self) -> None:
        plan = DeployPlan(
            backend="sing-box",
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

    def test_xray_rejects_tls_streaming_dns(self) -> None:
        with self.assertRaisesRegex(Exception, "does not accept tls://"):
            _build_streaming_dns("xray", True, "tls://dns.example.com", "netflix", None, "custom")

    def test_exports(self) -> None:
        node = self.make_node("main", 443)
        url = export_vless_url("203.0.113.10", node)
        self.assertIn("vless://11111111-1111-1111-1111-111111111111@203.0.113.10:443", url)
        payload = export_mihomo_proxy("203.0.113.10", node)
        self.assertEqual(payload["server"], "203.0.113.10")
        self.assertEqual(payload["reality-opts"]["short-id"], node.reality.short_id)

    def test_service_render(self) -> None:
        service = build_service("sing-box-main", "sing-box", "/etc/sing-box/main.json", "sing-box")
        self.assertIn("ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/main.json", service)

    def test_xray_service_render(self) -> None:
        service = build_service("xray-main", "xray", "/etc/xray/main.json", "xray")
        self.assertIn("ExecStart=/usr/local/bin/xray run -config /etc/xray/main.json", service)

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

    def test_summarize_bbr_status(self) -> None:
        status = summarize_bbr_status("bbr", "reno cubic bbr", "fq")
        self.assertTrue(status["has_bbr"])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["fq_ready"])

    def test_render_iptables_rules(self) -> None:
        rules = _render_iptables_rules([22, 443], ipv6=False)
        self.assertIn("-A INPUT -p tcp --dport 22 -j ACCEPT", rules)
        self.assertIn("-A INPUT -p tcp --dport 443 -j ACCEPT", rules)
        self.assertIn("-A INPUT -p icmp -j ACCEPT", rules)

    def test_load_firewall_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "iptables.v4"
            path.write_text(_render_iptables_rules([22, 8443], ipv6=False))
            self.assertEqual(load_firewall_ports(path), [22, 8443])

    def test_reality_keys_from_existing(self) -> None:
        original = generate_reality_keys()
        recovered = reality_keys_from_existing(original.private_key, original.short_id)
        self.assertEqual(recovered.private_key, original.private_key)
        self.assertEqual(recovered.public_key, original.public_key)
        self.assertEqual(recovered.short_id, original.short_id)

    def test_load_xray_reality_node(self) -> None:
        keys = generate_reality_keys()
        payload = {
            "inbounds": [
                {
                    "protocol": "vless",
                    "port": 2443,
                    "settings": {
                        "clients": [
                            {
                                "id": "22222222-2222-2222-2222-222222222222",
                                "flow": "xtls-rprx-vision",
                                "email": "media-user",
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "serverNames": ["media.example.net"],
                            "privateKey": keys.private_key,
                            "shortIds": [keys.short_id],
                        },
                    },
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "xray.json"
            path.write_text(json.dumps(payload))
            node = load_xray_reality_node(
                path,
                name="US-media",
                tag="us-media",
                role="media",
            )
        self.assertEqual(node.listen_port, 2443)
        self.assertEqual(node.uuid, "22222222-2222-2222-2222-222222222222")
        self.assertEqual(node.server_name, "media.example.net")
        self.assertEqual(node.reality.private_key, keys.private_key)
        self.assertEqual(node.reality.public_key, keys.public_key)
        self.assertEqual(node.reality.short_id, keys.short_id)


if __name__ == "__main__":
    unittest.main()
