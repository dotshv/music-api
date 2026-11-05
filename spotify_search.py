from concurrent.futures import ThreadPoolExecutor
import html
import logging
import re
import time
from typing import List, Optional

from cache import cache
from http_client import http
from metadata import fetch_track_meta
from songs import make_song

log = logging.getLogger("toxics.search")

TIMEOUT = 1.5
ONE_HOUR = 3600
_spotify_rate_limited_until = 0.0


def _pick_image(images: list) -> str:
    if not images:
        return ""
    return (images[1] if len(images) > 1 else images[0]).get("url", "")


def _from_spotify(spotify, query: str, limit: int, base_url: Optional[str] = None) -> List[dict]:
    global _spotify_rate_limited_until
    if time.time() < _spotify_rate_limited_until:
        return []

    token = spotify.access_token() if spotify else None
    if not token:
        return []

    try:
        resp = http.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": query, "type": "track", "limit": limit},
            timeout=TIMEOUT,
        )
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", "2"))
            _spotify_rate_limited_until = time.time() + retry_after
            log.warning("Spotify rate limit (429) hit, retrying in %ds, falling back", retry_after)
            return []
        resp.raise_for_status()
    except Exception as exc:
        r = getattr(exc, "response", None)
        if getattr(r, "status_code", None) == 429:
            retry_after = int(getattr(r, "headers", {}).get("retry-after", "2"))
            _spotify_rate_limited_until = time.time() + retry_after
        return []

    songs = []
    for item in resp.json().get("tracks", {}).get("items", []):
        album = item.get("album", {})
        duration_ms = item.get("duration_ms")
        songs.append(
            make_song(
                item["id"],
                title=item.get("name", ""),
                artist=", ".join(a["name"] for a in item.get("artists", [])),
                album=album.get("name", ""),
                thumbnail=_pick_image(album.get("images", [])),
                duration_sec=int(duration_ms / 1000) if duration_ms else None,
                source="spotify",
                base_url=base_url,
            )
        )
    return songs


def _from_saavn(query: str, limit: int, base_url: Optional[str] = None) -> List[dict]:
    resp = http.get(
        "https://www.jiosaavn.com/api.php",
        params={
            "__call": "autocomplete.get",
            "query": query,
            "_format": "json",
            "_marker": "0",
            "ctx": "android",
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    songs = []
    for item in resp.json().get("songs", {}).get("data", [])[:limit]:
        cover = (item.get("image") or "").replace("50x50", "500x500").replace("150x150", "500x500")
        artist = item.get("more_info", {}).get("singers") or item.get("description", "")
        songs.append(
            make_song(
                item["id"],
                title=html.unescape(item.get("title", "")),
                artist=html.unescape(artist),
                album=html.unescape(item.get("album", "")),
                thumbnail=cover,
                source="saavn",
                base_url=base_url,
            )
        )
    return songs


def _from_itunes(query: str, limit: int, base_url: Optional[str] = None) -> List[dict]:
    resp = http.get(
        "https://itunes.apple.com/search",
        params={"term": query, "media": "music", "limit": limit},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()

    songs = []
    for item in resp.json().get("results", []):
        millis = item.get("trackTimeMillis")
        songs.append(
            make_song(
                item["trackId"],
                title=item.get("trackName", ""),
                artist=item.get("artistName", ""),
                album=item.get("collectionName", ""),
                thumbnail=(item.get("artworkUrl100") or "").replace("100x100bb", "600x600bb"),
                duration_sec=int(millis / 1000) if millis else None,
                source="itunes",
                base_url=base_url,
            )
        )
    return songs


def _from_youtube(query: str, limit: int, base_url: Optional[str] = None) -> List[dict]:
    import yt_dlp

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 5,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios"],
            }
        },
        "http_headers": {
            "User-Agent": "com.google.android.youtube/19.29.37 (Linux; U; Android 14; en_US) gzip"
        },
    }
    songs = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = info.get("entries", []) if info else []
        for entry in entries:
            if not entry or not entry.get("id"):
                continue
            vid_id = str(entry.get("id"))
            title = entry.get("title") or "Unknown"
            artist = entry.get("uploader") or entry.get("channel") or ""
            thumb = entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid_id}/hqdefault.jpg"
            duration = entry.get("duration")
            songs.append(
                make_song(
                    vid_id,
                    title=html.unescape(title),
                    artist=html.unescape(artist),
                    thumbnail=thumb,
                    duration_sec=int(duration) if duration else None,
                    source="youtube",
                    base_url=base_url,
                )
            )
    except Exception as exc:
        log.warning("YouTube search fallback failed: %s", exc)
    return songs


def search_tracks(spotify, query: str, limit: int = 10, base_url: Optional[str] = None) -> List[dict]:
    query = query.strip()
    if not query:
        return []

    cache_key = f"search_{query.lower()}_{limit}_{base_url or ''}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    results: List[dict] = []

    global _spotify_rate_limited_until
    spotify_ok = bool(spotify and spotify.is_connected and time.time() >= _spotify_rate_limited_until)
    if spotify_ok:
        try:
            results = _from_spotify(spotify, query, limit, base_url)
        except Exception:
            results = []

    if not results:
        try:
            results = _from_saavn(query, limit, base_url)
        except Exception:
            results = []

    if not results:
        try:
            results = _from_itunes(query, limit, base_url)
        except Exception:
            results = []

    if not results:
        try:
            results = _from_youtube(query, limit, base_url)
        except Exception:
            results = []

    if results:
        cache.set(cache_key, results, ttl=ONE_HOUR)
    return results


search_spotify = search_tracks


def resolve_track(spotify, query: str, prefer_id: Optional[str] = None, base_url: Optional[str] = None) -> Optional[dict]:
    track_id = spotify.clean_track_id(query)
    if track_id:
        return fetch_track_meta(track_id, base_url=base_url)

    yt_match = re.search(r"(?:v=|\/|youtu\.be\/|embed\/)([a-zA-Z0-9_-]{11})", query)
    if yt_match:
        return fetch_track_meta(yt_match.group(1), base_url=base_url)
    clean_q = query.strip()
    if len(clean_q) == 11 and not clean_q.isdigit() and " " not in clean_q:
        return fetch_track_meta(clean_q, base_url=base_url)

    results = search_tracks(spotify, query, limit=5 if prefer_id else 1, base_url=base_url)
    if prefer_id:
        for song in results:
            if song["id"] == prefer_id:
                return song
    return results[0] if results else None
