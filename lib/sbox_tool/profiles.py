from __future__ import annotations

STREAMING_PROFILES: dict[str, list[str]] = {
    "common-media": [
        "netflix.com",
        "netflix.net",
        "nflxvideo.net",
        "nflximg.net",
        "nflximg.com",
        "nflxext.com",
        "nflxso.net",
        "nflxsearch.net",
        "fast.com",
        "disneyplus.com",
        "disney-plus.net",
        "dssott.com",
        "bamgrid.com",
        "max.com",
        "hbomax.com",
        "hbo.com",
        "hulu.com",
        "huluim.com",
        "hulustream.com",
        "primevideo.com",
        "amazonvideo.com",
        "aiv-cdn.net",
        "crunchyroll.com",
        "crunchyrollsvc.com",
        "peacocktv.com",
        "paramountplus.com",
    ],
    "netflix": [
        "netflix.com",
        "netflix.net",
        "nflxvideo.net",
        "nflximg.net",
        "nflximg.com",
        "nflxext.com",
        "nflxso.net",
        "nflxsearch.net",
        "fast.com",
    ],
    "disney": [
        "disneyplus.com",
        "disney-plus.net",
        "dssott.com",
        "bamgrid.com",
    ],
    "max": [
        "max.com",
        "hbomax.com",
        "hbo.com",
    ],
    "primevideo": [
        "primevideo.com",
        "amazonvideo.com",
        "aiv-cdn.net",
    ],
    "hulu": [
        "hulu.com",
        "huluim.com",
        "hulustream.com",
    ],
}


def get_profile(name: str) -> list[str]:
    try:
        return STREAMING_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown streaming profile: {name}") from exc
