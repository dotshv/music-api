import logging
from pathlib import Path
import re
import threading
import time
from typing import Optional, Tuple

import requests
from librespot.audio.decoders import AudioQuality
from librespot.core import Session
from librespot.metadata import TrackId

from config import BASE_DIR, SPOTIFY_CREDENTIALS_FILE, SPOTIFY_PASSWORD, SPOTIFY_USERNAME

log = logging.getLogger("toxics.spotify")

_TRACK_ID_RE = re.compile(r"track[/:]([a-zA-Z0-9]{22})")
_MIME_BY_EXT = {"webm": "audio/webm", "m4a": "audio/mp4", "mp4": "audio/mp4"}
_MOBILE_UA = "com.google.android.youtube/19.29.37 (Linux; U; Android 14; en_US) gzip"


def get_direct_cdn_url(track_id: str) -> Optional[str]:
    try:
        from cache import cache
        from http_client import http
        import base64
        from Cryptodome.Cipher import DES

        clean_id = str(track_id).strip()
        cache_key = f"saavn_cdn_{clean_id}"
        cdn_url = cache.get(cache_key)
        if not cdn_url:
            resp = http.get(
                "https://www.jiosaavn.com/api.php",
                params={
                    "__call": "song.getDetails",
                    "pids": clean_id,
                    "_format": "json",
                    "_marker": "0",
                    "ctx": "android",
                },
                timeout=2.5,
            )
            if resp.status_code != 200:
                return None
            data = resp.json().get(clean_id, {})
            enc = data.get("encrypted_media_url")
            if not enc:
                return None
            cipher = DES.new(b"38346591", DES.MODE_ECB)
            dec = cipher.decrypt(base64.b64decode(enc))
            pad = dec[-1]
            raw_url = dec[:-pad].decode("utf-8")
            cdn_url = raw_url.replace("_96.mp4", "_320.mp4")
            cache.set(cache_key, cdn_url, ttl=86400)
        return cdn_url
    except Exception:
        return None


def _stream_from_saavn(track_id: str) -> Optional[Tuple[object, str]]:
    try:
        from http_client import http
        cdn_url = get_direct_cdn_url(track_id)
        if not cdn_url:
            return None
        stream_resp = http.get(cdn_url, stream=True, timeout=5)
        if stream_resp.status_code != 200:
            fallback_url = cdn_url.replace("_320.mp4", "_96.mp4")
            stream_resp = http.get(fallback_url, stream=True, timeout=5)
        stream_resp.raise_for_status()
        stream_resp.raw.decode_content = True
        return stream_resp.raw, "audio/mp4"
    except Exception:
        log.warning("Saavn direct CDN stream failed for %s", track_id, exc_info=True)
        return None


def get_direct_audio_url(track_id: str, query: Optional[str] = None) -> Optional[str]:
    clean_id = str(track_id).strip()
    cdn_url = get_direct_cdn_url(clean_id)
    if cdn_url:
        return cdn_url

    target = query or clean_id
    try:
        import yt_dlp

        options = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 10,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios"],
                }
            },
            "http_headers": {
                "User-Agent": _MOBILE_UA
            },
        }
        if "youtube.com" in target or "youtu.be" in target:
            search_target = target
        elif len(target) == 11 and not target.isdigit() and " " not in target:
            search_target = f"https://www.youtube.com/watch?v={target}"
        else:
            search_target = f"ytsearch1:{target}"

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(search_target, download=False)
        entry = info["entries"][0] if info.get("entries") else info
        return entry.get("url")
    except Exception:
        return None


def _stream_from_search(query: str) -> Tuple[object, str]:
    import yt_dlp

    options = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 10,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios"],
            }
        },
        "http_headers": {
            "User-Agent": _MOBILE_UA
        },
    }
    if "youtube.com" in query or "youtu.be" in query:
        target = query
    elif len(query) == 11 and not query.isdigit() and " " not in query:
        target = f"https://www.youtube.com/watch?v={query}"
    else:
        target = f"ytsearch1:{query}"

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(target, download=False)

    entry = info["entries"][0] if info.get("entries") else info
    direct_url = entry["url"]
    headers = entry.get("http_headers") or {"User-Agent": _MOBILE_UA}
    resp = requests.get(direct_url, stream=True, timeout=12, headers=headers)
    resp.raise_for_status()
    resp.raw.decode_content = True
    return resp.raw, _MIME_BY_EXT.get(entry.get("ext"), "audio/mpeg")


class SpotifyManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.session = None
        self.is_connected = False
        threading.Thread(target=self.connect, daemon=True).start()

    @classmethod
    def get_instance(cls) -> "SpotifyManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def connect(self) -> bool:
        creds_candidates = [
            BASE_DIR / SPOTIFY_CREDENTIALS_FILE,
            Path(SPOTIFY_CREDENTIALS_FILE),
            Path("/home/ubuntu/api/credentials.json"),
            Path("/root/api/credentials.json"),
            Path("/root/credentials.json"),
            Path("/opt/toxics-music/credentials.json"),
        ]
        for creds_path in creds_candidates:
            if creds_path.is_file():
                for attempt in range(1, 3):
                    try:
                        self.session = Session.Builder().stored_file(str(creds_path)).create()
                        self.is_connected = True
                        log.info("Spotify connected successfully via stored credentials (%s)!", creds_path)
                        return True
                    except Exception as exc:
                        log.warning("Attempt %d connecting via stored file %s failed: %s", attempt, creds_path, exc)
                        time.sleep(1)

        if not SPOTIFY_USERNAME or not SPOTIFY_PASSWORD:
            log.warning("Spotify credentials missing - running in catalog-only mode")
            self.is_connected = False
            return False

        for attempt in range(1, 3):
            try:
                self.session = Session.Builder().user_pass(SPOTIFY_USERNAME, SPOTIFY_PASSWORD).create()
                self.is_connected = True
                log.info("Spotify connected successfully via username/password!")
                return True
            except Exception as exc:
                log.warning("Attempt %d connecting via user/pass failed: %s", attempt, exc)
                time.sleep(1)

        self.session = None
        self.is_connected = False
        return False

    def access_token(self) -> Optional[str]:
        from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
        if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
            from cache import cache
            cached_token = cache.get("spotify_cc_token")
            if cached_token:
                return cached_token
            try:
                import base64
                auth_header = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
                resp = requests.post(
                    "https://accounts.spotify.com/api/token",
                    data={"grant_type": "client_credentials"},
                    headers={"Authorization": f"Basic {auth_header}"},
                    timeout=3,
                )
                if resp.status_code == 200:
                    token_data = resp.json()
                    tok = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                    if tok:
                        cache.set("spotify_cc_token", tok, ttl=expires_in - 60)
                        return tok
            except Exception:
                log.warning("Spotify client credentials token failed", exc_info=True)

        if not (self.session and self.is_connected):
            return None
        try:
            token = self.session.tokens().get_token("user-read-private")
            return getattr(token, "access_token", None)
        except Exception:
            log.warning("Could not get Spotify access token", exc_info=True)
            return None

    @staticmethod
    def clean_track_id(value: str) -> Optional[str]:
        if not value:
            return None
        match = _TRACK_ID_RE.search(value)
        if match:
            return match.group(1)
        if len(value) == 22 and value.isalnum():
            return value
        return None

    def stream_track(self, track_id: str, source: str = "auto", query: Optional[str] = None):
        track_str = str(track_id).strip()
        is_spotify_id = len(track_str) == 22 and track_str.isalnum()

        if is_spotify_id and self.is_connected:
            try:
                stream = self.session.content_feeder().load(
                    TrackId.from_base62(track_str), AudioQuality.VERY_HIGH, False, None
                )
                return stream.input_stream, "audio/ogg"
            except Exception:
                log.warning("Direct Spotify stream failed for %s, trying Saavn CDN fallback", track_str)

        if not is_spotify_id:
            saavn_res = _stream_from_saavn(track_str)
            if saavn_res:
                return saavn_res

        is_yt = source == "youtube" or "youtube.com" in track_str or "youtu.be" in track_str or (len(track_str) == 11 and not track_str.isdigit())
        if is_yt:
            try:
                return _stream_from_search(track_str)
            except Exception:
                log.warning("Direct YouTube stream failed for %s, trying query fallback", track_str)

        search_query = query
        from metadata import fetch_track_meta
        if not search_query:
            meta = fetch_track_meta(track_str)
            if meta and meta.get("title") and meta["title"] != track_str:
                search_query = f"{meta['title']} {meta.get('artist', '')}".strip()
            else:
                search_query = track_str

        if search_query:
            try:
                from spotify_search import _from_saavn
                fast_matches = _from_saavn(search_query, 1)
                if fast_matches:
                    saavn_res = _stream_from_saavn(fast_matches[0]["id"])
                    if saavn_res:
                        return saavn_res
            except Exception:
                pass

        if not search_query:
            raise RuntimeError("Could not resolve audio for track")

        try:
            return _stream_from_search(search_query)
        except Exception as exc:
            log.error("Playback stream error for %r", search_query, exc_info=True)
            raise RuntimeError("Playback stream error") from exc

    get_audio_stream = stream_track
    get_direct_audio_url = staticmethod(get_direct_audio_url)

    @staticmethod
    def _fallback_query(track_id: str, source: str) -> Optional[str]:
        if source != "spotify":
            return None
        from metadata import fetch_track_meta
        meta = fetch_track_meta(track_id)
        return meta.get("title") if meta else None
