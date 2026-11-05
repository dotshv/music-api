"""Shared HTTP session with connection pooling and light retries."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

http = requests.Session()
_adapter = HTTPAdapter(
    pool_connections=50,
    pool_maxsize=100,
    max_retries=Retry(
        total=1,
        backoff_factor=0.1,
        respect_retry_after_header=False,
    ),
)
http.mount("https://", _adapter)
http.mount("http://", _adapter)
http.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
