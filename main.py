import logging
import uuid

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import BASE_DIR, ENABLE_DOCS, HOST, PORT, SITE_NAME
from routes import api, pages
from templating import templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("toxics")

app = FastAPI(
    title=SITE_NAME,
    summary="Search songs, resolve links and stream audio over HTTP.",
    description="No API key needed. JSON responses, CORS enabled. Guide and live playground: /developers and /playground.",
    version="5.0.0",
    openapi_tags=api.TAGS,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After", "X-Request-ID"],
)


@app.middleware("http")
async def request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(api.router)
app.include_router(pages.router)

app.add_api_route("/play", api.resolve_song, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/search", api.search_songs, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/songs", api.search_songs, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/stream/{track_id}", api.stream_song, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/stream", api.stream_by_query, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/info/{track_id}", api.get_song, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/vplay", api.resolve_vplay, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/video", api.resolve_vplay, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/vstream/{track_id}", api.stream_video_route, methods=["GET", "HEAD"], include_in_schema=False)
app.add_api_route("/vstream", api.stream_video_by_query, methods=["GET", "HEAD"], include_in_schema=False)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


def _error(request: Request, code: int, message: str, headers: dict = None):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"status": "error", "code": code, "message": message}, status_code=code, headers=headers)
    return templates.TemplateResponse(
        request, "error.html", {"page": "error", "code": code, "message": message}, status_code=code, headers=headers
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    message = "Page not found" if exc.status_code == 404 and not request.url.path.startswith("/api/") else str(exc.detail)
    return _error(request, exc.status_code, message, getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p not in ("query", "path"))
    return _error(request, 422, f"{field}: {first['msg']}" if field else first["msg"])


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.error("Unhandled error on %s", request.url.path, exc_info=exc)
    return _error(request, 500, "Something went wrong on our side")


if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=False)
