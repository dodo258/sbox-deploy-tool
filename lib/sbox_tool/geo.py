from __future__ import annotations

import json
import urllib.request


COUNTRY_REGION_OVERRIDES = {
    "US": "us",
    "CA": "us",
    "GB": "uk",
    "DE": "de",
    "FR": "fr",
    "JP": "jp",
    "KR": "kr",
    "HK": "hk",
    "TW": "tw",
    "SG": "sg",
    "IN": "in",
    "MX": "latam",
    "BR": "latam",
    "AR": "latam",
    "CL": "latam",
    "CO": "latam",
    "PE": "latam",
    "MY": "sea",
    "ID": "sea",
    "TH": "sea",
    "VN": "sea",
    "PH": "sea",
    "AE": "middle-east",
    "SA": "middle-east",
    "QA": "middle-east",
    "KW": "middle-east",
    "OM": "middle-east",
    "BH": "middle-east",
    "IL": "middle-east",
    "JO": "middle-east",
    "NZ": "oceania",
    "AU": "oceania",
    "ZA": "africa",
    "NG": "africa",
    "EG": "africa",
    "KE": "africa",
    "MA": "africa",
}

CONTINENT_REGION_DEFAULTS = {
    "EU": "eu",
    "AS": "sea",
    "OC": "oceania",
    "SA": "latam",
    "AF": "africa",
    "NA": "us",
}


def map_country_to_probe_region(country_code: str | None, continent_code: str | None) -> str:
    if country_code:
        token = country_code.strip().upper()
        if token in COUNTRY_REGION_OVERRIDES:
            return COUNTRY_REGION_OVERRIDES[token]
    if continent_code:
        token = continent_code.strip().upper()
        if token in CONTINENT_REGION_DEFAULTS:
            return CONTINENT_REGION_DEFAULTS[token]
    return "us"


def lookup_ip_metadata(server_ip: str, timeout: int = 8) -> dict[str, str]:
    providers = [
        f"https://ipwho.is/{server_ip}",
        f"https://ipapi.co/{server_ip}/json/",
    ]
    for url in providers:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
        except Exception:
            continue
        country_code = str(payload.get("country_code") or payload.get("countryCode") or "").upper()
        continent_code = str(payload.get("continent_code") or payload.get("continentCode") or "").upper()
        country = str(payload.get("country") or payload.get("country_name") or "").strip()
        region = map_country_to_probe_region(country_code or None, continent_code or None)
        return {
            "server_ip": server_ip,
            "country_code": country_code,
            "continent_code": continent_code,
            "country": country,
            "probe_region": region,
        }
    return {
        "server_ip": server_ip,
        "country_code": "",
        "continent_code": "",
        "country": "",
        "probe_region": "us",
    }
