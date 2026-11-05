import logging
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import BASE_URL, RATE_LIMIT_PER_MIN, TRUST_PROXY
from metadata import fetch_track_meta
from ratelimit import RateLimiter
from spotify_search import resolve_track, search_tracks
from spotify_session import SpotifyManager

log = logging.getLogger("toxics.api")

spotify = SpotifyManager.get_instance()
limiter = RateLimiter(RATE_LIMIT_PER_MIN)

VALID_SOURCES = {"spotify", "saavn", "itunes", "youtube", "auto"}

TAGS = [
    {"name": "Songs", "description": "Search the catalog, get a song and stream its audio."},
    {"name": "Resolve", "description": "Turn a song title or Spotify link into one song."},
    {"name": "Meta", "description": "API index."},
]


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request, response: Response) -> None:
    if RATE_LIMIT_PER_MIN <= 0:
        return
    allowed, remaining, retry_after = limiter.check(client_ip(request))
    response.headers["X-RateLimit-Limit"] = str(limiter.limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {retry_after}s.",
            headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(limiter.limit), "X-RateLimit-Remaining": "0"},
        )


def get_base_url(request: Request) -> str:
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    if not host or host in {"localhost", "127.0.0.1", "testserver"} or "localhost" in host or "127.0.0.1" in host:
        return BASE_URL
    proto = request.headers.get("x-forwarded-proto", "https" if "toxics.me" in host else request.url.scheme)
    return f"{proto}://{host}"


router = APIRouter(prefix="/api/v1", dependencies=[Depends(rate_limit)])


class Song(BaseModel):
    id: str
    title: str
    artist: str = ""
    album: str = ""
    thumbnail: str = ""
    duration_sec: Optional[int] = None
    source: str
    stream_url: str
    preview_url: Optional[str] = None
    video_url: Optional[str] = None
    video_stream_url: Optional[str] = None
    spotify_url: str


class SongList(BaseModel):
    status: str = "success"
    query: str
    count: int
    results: List[Song]


class SongResult(BaseModel):
    status: str = "success"
    song: Song
    data: Optional[Song] = None
    result: Optional[Song] = None
    stream_url: Optional[str] = None
    video_url: Optional[str] = None
    video_stream_url: Optional[str] = None
    vstream_url: Optional[str] = None
    direct_video_url: Optional[str] = None
    url: Optional[str] = None
    link: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    thumbnail: Optional[str] = None
    duration: Optional[int] = None


class SongData(BaseModel):
    status: str = "success"
    data: Song


class ErrorBody(BaseModel):
    status: str = "error"
    code: int
    message: str


ERRORS = {
    404: {"model": ErrorBody, "description": "Nothing matched"},
    422: {"model": ErrorBody, "description": "Invalid or missing parameter"},
    429: {"model": ErrorBody, "description": "Rate limit exceeded"},
}


def _chunks(stream, size: int = 32768):
    try:
        while True:
            chunk = stream.read(size)
            if not chunk:
                break
            yield chunk
    except Exception:
        log.warning("Stream interrupted", exc_info=True)
    finally:
        if hasattr(stream, "close"):
            stream.close()


@router.api_route("", methods=["GET", "HEAD"], tags=["Meta"], summary="API index", include_in_schema=True)
def index(request: Request):
    base = get_base_url(request)
    return {
        "name": "Toxics Music API",
        "version": "v1",
        "base_url": f"{base}/api/v1",
        "endpoints": {
            "search": "GET /api/v1/songs?query= or GET /search?query=",
            "song": "GET /api/v1/songs/{id} or GET /info/{id}",
            "stream": "GET /api/v1/songs/{id}/stream or GET /stream/{id}",
            "play": "GET /api/v1/play?query= or GET /play?query=",
            "resolve": "GET /api/v1/resolve?query=",
        },
    }


@router.api_route("/songs", methods=["GET", "HEAD"], response_model=SongList, responses=ERRORS, tags=["Songs"], summary="Search songs")
@router.api_route("/search", methods=["GET", "HEAD"], response_model=SongList, include_in_schema=False)
def search_songs(
    request: Request,
    query: Optional[str] = Query(None, description="Song title or artist"),
    q: Optional[str] = Query(None, description="Short query alias"),
    name: Optional[str] = Query(None, description="Name alias"),
    limit: int = Query(10, ge=1, le=25, description="Number of results"),
):
    search_term = (query or q or name or "").strip()
    if not search_term:
        raise HTTPException(status_code=422, detail="Query parameter is required")
    base = get_base_url(request)
    results = search_tracks(spotify, search_term, limit=limit, base_url=base)
    return {"status": "success", "query": search_term, "count": len(results), "results": results}


@router.api_route("/resolve", methods=["GET", "HEAD"], response_model=SongResult, responses=ERRORS, tags=["Resolve"], summary="Resolve a title or link to one song")
@router.api_route("/play", methods=["GET", "HEAD"], response_model=SongResult, include_in_schema=False)
def resolve_song(
    request: Request,
    query: Optional[str] = Query(None, description="Song title, or a Spotify track link / URI"),
    q: Optional[str] = Query(None, description="Short query alias"),
    song: Optional[str] = Query(None, description="Song alias"),
    name: Optional[str] = Query(None, description="Name alias"),
    stream: Optional[bool] = Query(False, description="Set true to stream audio directly"),
):
    search_term = (query or q or song or name or "").strip()
    if not search_term:
        raise HTTPException(status_code=422, detail="Query parameter is required")
    base = get_base_url(request)
    song_item = resolve_track(spotify, search_term, base_url=base)
    if not song_item:
        raise HTTPException(status_code=404, detail="Track not found")

    if stream:
        clean_id = spotify.clean_track_id(song_item["id"]) or song_item["id"]
        raw_stream, content_type = spotify.stream_track(clean_id, source=song_item.get("source", "auto").lower(), query=search_term)
        return StreamingResponse(
            _chunks(raw_stream),
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Accel-Buffering": "no",
            },
        )

    return {
        "status": "success",
        "song": song_item,
        "data": song_item,
        "result": song_item,
        "stream_url": song_item["stream_url"],
        "video_url": song_item.get("video_url"),
        "video_stream_url": song_item.get("video_stream_url"),
        "url": song_item["stream_url"],
        "link": song_item["stream_url"],
        "title": song_item["title"],
        "artist": song_item.get("artist", ""),
        "thumbnail": song_item.get("thumbnail", ""),
        "duration": song_item.get("duration_sec"),
    }


@router.api_route("/songs/{track_id}", methods=["GET", "HEAD"], response_model=SongData, responses=ERRORS, tags=["Songs"], summary="Get one song")
@router.api_route("/info/{track_id}", methods=["GET", "HEAD"], response_model=SongData, include_in_schema=False)
def get_song(request: Request, track_id: str):
    clean_id = spotify.clean_track_id(track_id) or track_id
    base = get_base_url(request)
    return {"status": "success", "data": fetch_track_meta(clean_id, base_url=base)}


@router.api_route(
    "/songs/{track_id}/stream",
    methods=["GET", "HEAD"],
    tags=["Songs"],
    summary="Stream audio",
    responses={200: {"content": {"audio/*": {}}, "description": "Audio stream"}, 400: {"model": ErrorBody}, 500: {"model": ErrorBody}},
)
@router.api_route("/stream/{track_id}", methods=["GET", "HEAD"], include_in_schema=False)
def stream_song(
    request: Request,
    track_id: str,
    source: str = Query("auto", description="spotify, saavn, itunes or auto"),
    q: Optional[str] = Query(None, max_length=200, description="Title and artist, used to find audio if no direct source exists."),
    redirect: bool = Query(False, description="Redirect directly to CDN url if available"),
):
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type="audio/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    clean_id = spotify.clean_track_id(track_id) or track_id
    if redirect:
        from spotify_session import get_direct_audio_url
        direct_url = get_direct_audio_url(clean_id, query=q)
        if direct_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(direct_url, status_code=307)
    try:
        stream, content_type = spotify.stream_track(clean_id, source=source, query=q)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not start the audio stream")

    return StreamingResponse(
        _chunks(stream),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


@router.api_route("/stream", methods=["GET", "HEAD"], include_in_schema=False)
def stream_by_query(
    request: Request,
    query: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    song: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    source: str = Query("auto"),
    redirect: bool = Query(False),
):
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type="audio/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    search_term = (query or q or song or name or "").strip()
    if not search_term:
        raise HTTPException(status_code=422, detail="Query parameter is required")
    base = get_base_url(request)
    song_item = resolve_track(spotify, search_term, base_url=base)
    if not song_item:
        raise HTTPException(status_code=404, detail="Track not found")
    if redirect:
        from spotify_session import get_direct_audio_url
        direct_url = get_direct_audio_url(song_item["id"], query=song_item["title"])
        if direct_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(direct_url, status_code=307)
    stream, content_type = spotify.stream_track(song_item["id"], source=source, query=song_item["title"])
    return StreamingResponse(
        _chunks(stream),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.api_route("/vplay", methods=["GET", "HEAD"], response_model=SongResult, include_in_schema=False)
@router.api_route("/video", methods=["GET", "HEAD"], response_model=SongResult, include_in_schema=False)
def resolve_vplay(
    request: Request,
    query: Optional[str] = Query(None, description="Song title or video query"),
    q: Optional[str] = Query(None, description="Short query alias"),
    song: Optional[str] = Query(None, description="Song alias"),
    name: Optional[str] = Query(None, description="Name alias"),
    stream: Optional[bool] = Query(False, description="Set true to stream video directly"),
    redirect: Optional[bool] = Query(True, description="Redirect to direct video CDN if true"),
):
    search_term = (query or q or song or name or "").strip()
    if not search_term:
        raise HTTPException(status_code=422, detail="Query parameter is required")

    base = get_base_url(request)
    song_item = resolve_track(spotify, search_term, base_url=base)

    if not song_item:
        song_item = {
            "id": search_term,
            "title": search_term,
            "artist": "",
            "album": "",
            "thumbnail": "",
            "duration_sec": None,
            "source": "Catalog",
            "stream_url": f"{base}/vstream/{quote(search_term, safe='')}?q={quote(search_term, safe='')}",
            "video_url": f"{base}/vstream/{quote(search_term, safe='')}?q={quote(search_term, safe='')}",
            "video_stream_url": f"{base}/vstream/{quote(search_term, safe='')}?q={quote(search_term, safe='')}",
            "spotify_url": "",
        }

    target_query = f"{song_item['title']} {song_item.get('artist', '')}".strip()
    video_stream_url = f"{base}/vstream/{quote(str(song_item['id']), safe='')}?q={quote(target_query, safe='')}"

    if stream:
        from fastapi.responses import RedirectResponse
        from video import extract_video_info, get_video_stream

        vinfo = extract_video_info(target_query)
        if not vinfo or not vinfo.get("url"):
            raise HTTPException(status_code=404, detail="Video stream not found")
        if redirect:
            return RedirectResponse(vinfo["url"], status_code=302)
        raw_stream, content_type = get_video_stream(target_query)
        return StreamingResponse(
            _chunks(raw_stream),
            media_type=content_type,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Accel-Buffering": "no",
            },
        )

    return {
        "status": "success",
        "song": song_item,
        "data": song_item,
        "result": song_item,
        "stream_url": video_stream_url,
        "video_url": video_stream_url,
        "video_stream_url": video_stream_url,
        "vstream_url": video_stream_url,
        "direct_video_url": None,
        "url": video_stream_url,
        "link": video_stream_url,
        "title": song_item["title"],
        "artist": song_item.get("artist", ""),
        "thumbnail": song_item.get("thumbnail", ""),
        "duration": song_item.get("duration_sec"),
    }


@router.api_route("/vstream/{track_id}", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/video/{track_id}/stream", methods=["GET", "HEAD"], include_in_schema=False)
def stream_video_route(
    request: Request,
    track_id: str,
    q: Optional[str] = Query(None),
    proxy: bool = Query(False, description="Set true to proxy stream instead of redirecting"),
):
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    from fastapi.responses import RedirectResponse
    from video import extract_video_info, get_video_stream

    target = q or track_id
    vinfo = extract_video_info(target)
    if not vinfo or not vinfo.get("url"):
        raise HTTPException(status_code=404, detail="Video stream not found")

    if not proxy:
        return RedirectResponse(vinfo["url"], status_code=302)

    raw_stream, content_type = get_video_stream(target)
    return StreamingResponse(
        _chunks(raw_stream),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )


@router.api_route("/vstream", methods=["GET", "HEAD"], include_in_schema=False)
def stream_video_by_query(
    request: Request,
    query: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    song: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    proxy: bool = Query(False),
):
    if request.method == "HEAD":
        return Response(
            status_code=200,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )
    search_term = (query or q or song or name or "").strip()
    if not search_term:
        raise HTTPException(status_code=422, detail="Query parameter is required")

    from fastapi.responses import RedirectResponse
    from video import extract_video_info, get_video_stream

    vinfo = extract_video_info(search_term)
    if not vinfo or not vinfo.get("url"):
        raise HTTPException(status_code=404, detail="Video stream not found")

    if not proxy:
        return RedirectResponse(vinfo["url"], status_code=302)

    raw_stream, content_type = get_video_stream(search_term)
    return StreamingResponse(
        _chunks(raw_stream),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Accel-Buffering": "no",
        },
    )
