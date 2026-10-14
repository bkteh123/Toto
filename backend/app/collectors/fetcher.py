"""HTTP fetching that is polite to the source: one request per N seconds, a descriptive
User-Agent, a small on-disk cache and a bounded number of retries."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.collectors.base import SourceUnreachable


@dataclass
class FetchResult:
    text: str
    final_url: str  # differs from the requested URL when the site redirected
    from_cache: bool


class Fetcher:
    def __init__(
        self,
        user_agent: str,
        min_interval: float = 5.0,
        cache_dir: Path | None = None,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
        retries: int = 2,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.cache_dir = cache_dir
        self.retries = retries
        self._clock, self._sleep, self._wall = clock, sleep, wall_clock
        self._last_request: dict[str, float] = {}  # host -> monotonic time of last request
        self.requests_made = 0
        self._client = client or httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Language": "vi,en;q=0.8"},
            follow_redirects=True,
            timeout=timeout,
        )

    # ---- cache ----
    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:40] + ".json")

    def _cache_read(self, url: str, ttl: float | None) -> FetchResult | None:
        p = self._cache_path(url)
        if p is None or ttl == 0 or not p.exists():
            return None
        try:
            if ttl is not None and self._wall() - p.stat().st_mtime > ttl:
                return None
            data = json.loads(p.read_text(encoding="utf-8"))
            return FetchResult(data["text"], data["final_url"], from_cache=True)
        except (OSError, ValueError, KeyError):
            return None

    def _cache_write(self, url: str, res: FetchResult) -> None:
        p = self._cache_path(url)
        if p is None:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"text": res.text, "final_url": res.final_url}), encoding="utf-8")
        except OSError:
            pass  # a cache that cannot be written must never break a run

    # ---- network ----
    def _wait_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.min_interval - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def get(
        self,
        url: str,
        ttl: float | None = None,
        cache_if: Callable[[FetchResult], bool] | None = None,
    ) -> FetchResult:
        """GET `url`.

        ttl: seconds a cached copy stays valid; None = valid forever, 0 = never read the cache.
        cache_if: called with the fresh result; the body is cached only if it returns True
        (so a "not published yet" answer is never remembered as if it were a result).
        """
        cached = self._cache_read(url, ttl)
        if cached is not None:
            return cached

        host = urlsplit(url).netloc
        last_error = "unknown error"
        for attempt in range(self.retries + 1):
            self._wait_turn(host)
            self.requests_made += 1
            try:
                r = self._client.get(url)
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if r.status_code == 200:
                res = FetchResult(r.content.decode("utf-8", "replace"), str(r.url), from_cache=False)
                if cache_if is None or cache_if(res):
                    self._cache_write(url, res)
                return res
            last_error = f"HTTP {r.status_code}"
            if 400 <= r.status_code < 500:
                break  # a client error will not fix itself on retry
        raise SourceUnreachable(f"{url}: {last_error}")
