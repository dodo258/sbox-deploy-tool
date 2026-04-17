from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


CANDIDATES_FILE = Path(__file__).resolve().parents[2] / "templates" / "candidate_domains.json"

REGION_POOL_FALLBACKS: dict[str, list[str]] = {
    "hk": ["hk", "global"],
    "tw": ["tw", "global"],
    "sg": ["sg", "global"],
    "sea": ["sea", "global"],
    "jp": ["jp", "global"],
    "kr": ["kr", "global"],
    "eu": ["eu", "global"],
    "uk": ["uk", "global"],
    "de": ["de", "global"],
    "fr": ["fr", "global"],
    "oceania": ["oceania", "global"],
    "middle-east": ["middle-east", "global"],
    "africa": ["africa", "global"],
    "latam": ["latam", "global"],
    "in": ["in", "global"],
    "us": ["us", "global"],
}


@dataclass(slots=True)
class ProbeResult:
    domain: str
    ok: bool
    tls13: bool
    x25519: bool
    h2: bool
    status_code: int | None
    ttfb: float | None
    note: str = ""

    @property
    def score(self) -> float:
        score = 0.0
        if self.ok:
            score += 60
        if self.tls13:
            score += 12
        if self.x25519:
            score += 12
        if self.h2:
            score += 10
        if self.status_code is not None and 200 <= self.status_code < 300:
            score += 10
        if self.ttfb is not None:
            score += max(0, 10 - self.ttfb * 10)
        lowered = self.domain.lower()
        if any(hint in lowered for hint in ("apple", "github", "google", "youtube")):
            score -= 20
        if any(hint in lowered for hint in ("cdn", "cloudfront", "akamai", "fastly", "edgekey", "azureedge")):
            score -= 15
        return round(score, 2)


def load_candidates() -> dict[str, list[str]]:
    return json.loads(CANDIDATES_FILE.read_text())


def available_regions() -> list[str]:
    return sorted(load_candidates().keys())


def parse_domain_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def candidate_pool_for_region(region: str) -> list[str]:
    pools = load_candidates()
    ordered_regions = REGION_POOL_FALLBACKS.get(region, [region])
    merged: list[str] = []
    seen: set[str] = set()
    for pool_region in ordered_regions:
        for domain in pools.get(pool_region, []):
            if domain not in seen:
                seen.add(domain)
                merged.append(domain)
    return merged


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
        return ProbeResult(domain, False, False, False, False, None, None, "openssl not found")
    except subprocess.TimeoutExpired:
        return ProbeResult(domain, False, False, False, False, None, None, "openssl timeout")

    tls_output = f"{tls_probe.stdout}\n{tls_probe.stderr}"
    tls13 = "TLSv1.3" in tls_output
    x25519 = bool(re.search(r"\bX25519\b", tls_output))
    h2 = "ALPN protocol: h2" in tls_output

    cmd = [
        "curl",
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
        return ProbeResult(domain, False, tls13, x25519, h2, None, None, "curl not found")

    if completed.returncode != 0:
        note = completed.stderr.strip() or completed.stdout.strip() or "probe failed"
        return ProbeResult(domain, False, tls13, x25519, h2, None, None, note)

    output = completed.stdout.strip()
    fields = dict(re.findall(r"(\w+)=([^\s]+)", output))
    code = int(fields["code"]) if fields.get("code", "").isdigit() else None
    ttfb = float(fields["ttfb"]) if fields.get("ttfb") not in (None, "", "0") else 0.0
    h2 = fields.get("alpn") == "2"
    if code is not None and 300 <= code < 400:
        note = "redirect detected"
    else:
        note = ""
    ok = tls13 and x25519 and h2 and code is not None and 200 <= code < 300
    return ProbeResult(domain, ok, tls13, x25519, h2, code, ttfb, note)


def rank_domains(domains: list[str], timeout: int = 6) -> list[ProbeResult]:
    worker_count = min(max(1, len(domains)), 6)
    results: list[ProbeResult] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(probe_domain, domain, timeout): domain for domain in domains}
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda item: item.score, reverse=True)
