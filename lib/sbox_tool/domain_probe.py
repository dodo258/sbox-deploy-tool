from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


CANDIDATES_FILE = Path(__file__).resolve().parents[2] / "templates" / "candidate_domains.json"


@dataclass(slots=True)
class ProbeResult:
    domain: str
    ok: bool
    tls13: bool
    h2: bool
    status_code: int | None
    ttfb: float | None
    note: str = ""

    @property
    def score(self) -> float:
        score = 0.0
        if self.ok:
            score += 50
        if self.tls13:
            score += 25
        if self.h2:
            score += 20
        if self.status_code == 200:
            score += 10
        elif self.status_code and 200 <= self.status_code < 400:
            score += 5
        if self.ttfb is not None:
            score += max(0, 10 - self.ttfb * 10)
        return round(score, 2)


def load_candidates() -> dict[str, list[str]]:
    return json.loads(CANDIDATES_FILE.read_text())


def available_regions() -> list[str]:
    return sorted(load_candidates().keys())


def parse_domain_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def probe_domain(domain: str, timeout: int = 6) -> ProbeResult:
    openssl_cmd = [
        "openssl",
        "s_client",
        "-connect",
        f"{domain}:443",
        "-servername",
        domain,
        "-tls1_3",
        "-alpn",
        "h2",
    ]
    try:
        tls_probe = subprocess.run(
            openssl_cmd,
            check=False,
            capture_output=True,
            text=True,
            input="",
            timeout=timeout,
        )
    except FileNotFoundError:
        return ProbeResult(domain, False, False, False, None, None, "openssl not found")
    except subprocess.TimeoutExpired:
        return ProbeResult(domain, False, False, False, None, None, "openssl timeout")

    tls_output = f"{tls_probe.stdout}\n{tls_probe.stderr}"
    tls13 = "TLSv1.3" in tls_output
    h2 = "ALPN protocol: h2" in tls_output

    cmd = [
        "curl",
        "-I",
        "-sS",
        "--max-time",
        str(timeout),
        "--http2",
        "-o",
        "/dev/null",
        "-w",
        "code=%{http_code} alpn=%{http_version} ttfb=%{time_starttransfer}",
        f"https://{domain}",
    ]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return ProbeResult(domain, False, False, False, None, None, "curl not found")

    if completed.returncode != 0:
        note = completed.stderr.strip() or completed.stdout.strip() or "probe failed"
        return ProbeResult(domain, False, tls13, h2, None, None, note)

    output = completed.stdout.strip()
    fields = dict(re.findall(r"(\w+)=([^\s]+)", output))
    code = int(fields["code"]) if fields.get("code", "").isdigit() else None
    ttfb = float(fields["ttfb"]) if fields.get("ttfb") not in (None, "", "0") else 0.0
    h2 = fields.get("alpn") == "2"
    ok = tls13 and h2 and code is not None and 200 <= code < 400
    return ProbeResult(domain, ok, tls13, h2, code, ttfb)


def rank_domains(domains: list[str], timeout: int = 6) -> list[ProbeResult]:
    results = [probe_domain(domain, timeout=timeout) for domain in domains]
    return sorted(results, key=lambda item: item.score, reverse=True)
