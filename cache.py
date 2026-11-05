"""Tiny thread-safe in-memory TTL cache with a size cap."""
import threading
import time


class MemoryCache:
    def __init__(self, default_ttl: int = 3600, max_items: int = 2000):
        self._store = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl
        self.max_items = max_items

    def get(self, key):
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.time() < expiry:
                return value
            del self._store[key]
            return None

    def set(self, key, value, ttl=None):
        expiry = time.time() + (ttl or self.default_ttl)
        with self._lock:
            self._store[key] = (value, expiry)
            if len(self._store) > self.max_items:
                self._evict()

    def _evict(self):
        now = time.time()
        for key in [k for k, (_, exp) in self._store.items() if exp <= now]:
            del self._store[key]
        while len(self._store) > self.max_items:
            self._store.pop(next(iter(self._store)))


cache = MemoryCache()
