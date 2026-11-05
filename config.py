import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).resolve().parent

SITE_NAME = "Toxics Music API"
DOMAIN = os.getenv("DOMAIN", "toxics.me")
SCHEME = os.getenv("SCHEME", "https")
BASE_URL = f"{SCHEME}://{DOMAIN}"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

SUPPORT_URL = os.getenv("SUPPORT_URL", "https://t.me/dotshv")

SPOTIFY_USERNAME = os.getenv("SPOTIFY_USERNAME", "")
SPOTIFY_PASSWORD = os.getenv("SPOTIFY_PASSWORD", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_CREDENTIALS_FILE = os.getenv("SPOTIFY_CREDENTIALS_FILE", "credentials.json")

ENABLE_DOCS = _flag("ENABLE_DOCS", True)
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "120"))
TRUST_PROXY = _flag("TRUST_PROXY", True)
