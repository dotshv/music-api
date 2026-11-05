from typing import Optional
from urllib.parse import quote, urlencode

from config import BASE_URL


def make_song(
    track_id,
    title: str,
    artist: str = "",
    album: str = "",
    thumbnail: str = "",
    duration_sec: Optional[int] = None,
    source: str = "spotify",
    base_url: Optional[str] = None,
) -> dict:
    track_id = str(track_id)
    title = title or "Unknown track"
    query = f"{title} {artist}".strip()
    root_url = base_url or BASE_URL

    stream_qs = urlencode({"source": source, "q": query})

    if source == "spotify":
        spotify_url = f"https://open.spotify.com/track/{track_id}"
    elif source == "youtube":
        spotify_url = f"https://www.youtube.com/watch?v={track_id}"
    else:
        spotify_url = f"https://open.spotify.com/search/{quote(query)}"

    stream_url = f"{root_url}/stream/{quote(track_id, safe='')}?{stream_qs}"
    video_url = f"{root_url}/vstream/{quote(track_id, safe='')}?{stream_qs}"

    return {
        "id": track_id,
        "title": title,
        "artist": artist or "",
        "album": album or "",
        "thumbnail": thumbnail or "",
        "duration_sec": duration_sec,
        "source": "Spotify" if source == "spotify" else ("YouTube" if source == "youtube" else "Catalog"),
        "stream_url": stream_url,
        "preview_url": stream_url,
        "video_url": video_url,
        "video_stream_url": video_url,
        "spotify_url": spotify_url,
    }
