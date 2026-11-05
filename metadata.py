import html
import logging
import re
from typing import Optional

from cache import cache
from http_client import http
from songs import make_song

log = logging.getLogger("toxics.metadata")

OEMBED_URL = "https://open.spotify.com/oembed"
YT_OEMBED_URL = "https://www.youtube.com/oembed"
ONE_DAY = 86400
_YT_RE = re.compile(r"(?:v=|\/|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})")


def fetch_track_meta(track_id: str, base_url: Optional[str] = None) -> dict:
    clean_id = str(track_id).strip()
    cache_key = f"meta_{clean_id}_{base_url or ''}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if len(clean_id) == 22 and clean_id.isalnum():
        try:
            resp = http.get(
                OEMBED_URL,
                params={"url": f"https://open.spotify.com/track/{clean_id}"},
                timeout=2.5,
            )
            if resp.status_code == 200:
                payload = resp.json()
                title = payload.get("title")
                if title:
                    song = make_song(
                        clean_id,
                        title=title,
                        thumbnail=payload.get("thumbnail_url", ""),
                        source="spotify",
                        base_url=base_url,
                    )
                    cache.set(cache_key, song, ttl=ONE_DAY)
                    return song
        except Exception:
            pass

    yt_match = _YT_RE.search(clean_id)
    yt_id = yt_match.group(1) if yt_match else (clean_id if (len(clean_id) == 11 and not clean_id.isdigit()) else None)
    if yt_id:
        try:
            resp = http.get(
                YT_OEMBED_URL,
                params={"url": f"https://www.youtube.com/watch?v={yt_id}", "format": "json"},
                timeout=2.5,
            )
            if resp.status_code == 200:
                payload = resp.json()
                title = payload.get("title")
                if title:
                    song = make_song(
                        yt_id,
                        title=html.unescape(title),
                        artist=html.unescape(payload.get("author_name", "")),
                        thumbnail=payload.get("thumbnail_url") or f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg",
                        source="youtube",
                        base_url=base_url,
                    )
                    cache.set(cache_key, song, ttl=ONE_DAY)
                    return song
        except Exception:
            pass

    try:
        resp = http.get(
            "https://www.jiosaavn.com/api.php",
            params={
                "__call": "song.getDetails",
                "pids": clean_id,
                "_format": "json",
                "_marker": "0",
                "ctx": "android",
            },
            timeout=2.0,
        )
        if resp.status_code == 200:
            data = resp.json().get(clean_id, {})
            title = data.get("song")
            if title:
                singer = data.get("primary_artists") or data.get("singers") or ""
                cover = (data.get("image") or "").replace("150x150", "500x500")
                song = make_song(
                    clean_id,
                    title=html.unescape(title),
                    artist=html.unescape(singer),
                    album=html.unescape(data.get("album", "")),
                    thumbnail=cover,
                    source="saavn",
                    base_url=base_url,
                )
                cache.set(cache_key, song, ttl=ONE_DAY)
                return song
    except Exception:
        pass

    return make_song(clean_id, title=clean_id, base_url=base_url)
