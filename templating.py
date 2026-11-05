"""Shared Jinja2 environment so pages and error handlers render the same way."""
from datetime import datetime

from fastapi.templating import Jinja2Templates

from config import BASE_DIR, BASE_URL, ENABLE_DOCS, RATE_LIMIT_PER_MIN, SITE_NAME, SUPPORT_URL

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals.update(
    site_name=SITE_NAME,
    base_url=BASE_URL,
    support_url=SUPPORT_URL,
    docs_enabled=ENABLE_DOCS,
    rate_limit=RATE_LIMIT_PER_MIN,
    year=datetime.now().year,
)
