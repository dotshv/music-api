import logging
from typing import Optional, Tuple
import requests

from cache import cache
from metadata import fetch_track_meta

log = logging.getLogger("toxics.video")

_VIDEO_CACHE_TTL = 7200
_MOBILE_UA = "com.google.android.youtube/19.29.37 (Linux; U; Android 14; en_US) gzip"


def extract_video_info(query_or_id: str) -> Optional[dict]:
    clean = str(query_or_id).strip()
    if not clean:
        return None

    cache_key = f"vinfo_{clean.lower()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    search_term = clean
    if "youtube.com" in clean or "youtu.be" in clean:
        search_term = clean
    elif len(clean) == 11 and not clean.isdigit() and " " not in clean:
        search_term = f"https://www.youtube.com/watch?v={clean}"
    else:
        is_id = len(clean) in (8, 22) and clean.isalnum()
        if is_id:
            meta = fetch_track_meta(clean)
            if meta and meta.get("title") and meta["title"] != clean:
                artist = meta.get("artist", "")
                search_term = f"{meta['title']} {artist} official video".strip()
            else:
                search_term = f"{clean} official video"
        else:
            search_term = f"{clean} official video" if "video" not in clean.lower() else clean

    import yt_dlp

    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios"],
            }
        },
        "http_headers": {
            "User-Agent": _MOBILE_UA,
        },
        "socket_timeout": 6,
    }

    target = search_term if ("youtube.com" in search_term or "youtu.be" in search_term) else f"ytsearch1:{search_term}"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(target, download=False)
        entry = info["entries"][0] if info.get("entries") else info
        direct_url = entry.get("url")
        if not direct_url:
            return None
        res = {
            "id": entry.get("id", ""),
            "title": entry.get("title", ""),
            "url": direct_url,
            "duration": entry.get("duration"),
            "thumbnail": entry.get("thumbnail", ""),
            "headers": entry.get("http_headers") or {"User-Agent": _MOBILE_UA},
        }
        cache.set(cache_key, res, ttl=_VIDEO_CACHE_TTL)
        return res
    except Exception as exc:
        log.error("Failed extracting video for %r: %s", search_term, exc)
        return None


def get_video_stream(query_or_id: str) -> Tuple[object, str]:
    info = extract_video_info(query_or_id)
    if not info or not info.get("url"):
        raise RuntimeError("Could not resolve video stream")

    resp = requests.get(
        info["url"],
        stream=True,
        timeout=15,
        headers=info.get("headers") or {"User-Agent": _MOBILE_UA},
    )
    resp.raise_for_status()
    resp.raw.decode_content = True
    return resp.raw, "video/mp4"
