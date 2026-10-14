"""A fake Minh Ngoc built from seed/mega645.csv that mimics the real site's behaviour:
10 draws per page (the requested draw + 9 before it, newest first), and a redirect to the
LATEST page for any date it has no draw for (observed on the real site, 2026-10-13)."""

from __future__ import annotations

import csv
import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.collectors.fetcher import Fetcher

SEED = Path(__file__).resolve().parents[2] / "seed" / "mega645.csv"
FIRST_DRAW_NO = 1453
UA = "RoyalYellowAnalyzer/0.1 (+https://codencode.my; test)"

BLOCK = (
    '<div class="box-result-detail"> <p class="time-result"> </p><table><tbody><tr>'
    '<td class="thu_mega"><a href="/x.html">Chủ nhật</a></td>'
    '<td align="center">Kỳ vé: <span id="DT6X45_KY_VE">#{ky:05d}</span> | Ngày quay thưởng {d:%d/%m/%Y}</td>'
    "</tr></tbody></table> <ul class=\"result-number\">{balls}</ul> </div>"
)
BALL = '<li> <div class="finnish{i} bool">{n:02d}</div></li>'


@dataclass(frozen=True)
class SeedDraw:
    draw_no: int
    date: dt.date
    numbers: list[int]


def load_seed() -> list[SeedDraw]:
    rows = list(csv.reader(SEED.read_text(encoding="utf-8").splitlines()))[1:]
    return [
        SeedDraw(FIRST_DRAW_NO + i, dt.date.fromisoformat(r[0]), [int(x) for x in r[1:]])
        for i, r in enumerate(rows)
    ]


def render_block(d: SeedDraw, balls: list[int] | None = None) -> str:
    nums = d.numbers if balls is None else balls
    return BLOCK.format(
        ky=d.draw_no, d=d.date,
        balls="".join(BALL.format(i=i, n=n) for i, n in enumerate(nums, start=1)),
    )


def render_page(draws: list[SeedDraw], title: str = "Kết quả xổ số Mega 6/45") -> str:
    return f"<html><head><title>{title}</title></head><body>{''.join(render_block(d) for d in draws)}</body></html>"


class FakeSite:
    def __init__(self, draws: list[SeedDraw], *, tamper: dict[int, list[int]] | None = None,
                 fail_after: int | None = None, garbage: bool = False, down: bool = False):
        self.draws = draws
        self.index = {d.date: i for i, d in enumerate(draws)}
        self.tamper = tamper or {}
        self.fail_after = fail_after
        self.garbage = garbage
        self.down = down
        self.requests: list[str] = []
        self.user_agents: list[str] = []

    def page_for_index(self, i: int) -> str:
        window = self.draws[max(0, i - 9): i + 1][::-1]
        return "".join(
            render_block(d, self.tamper.get(d.draw_no)) for d in window
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        self.user_agents.append(request.headers.get("user-agent", ""))
        if self.down:
            raise httpx.ConnectError("site is down", request=request)
        if self.fail_after is not None and len(self.requests) > self.fail_after:
            return httpx.Response(503, text="unavailable")
        if self.garbage:
            return httpx.Response(200, text="<html><title>Bảo trì</title><body>maintenance</body></html>")
        path = urlsplit(str(request.url)).path
        m = re.search(r"/(\d{2})-(\d{2})-(\d{4})\.html$", path)
        if not m:
            return httpx.Response(404, text="not found")
        date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        latest = self.draws[-1]
        if date not in self.index:  # the real site redirects to the latest page
            target = request.url.copy_with(path=re.sub(r"[^/]+$", f"{latest.date:%d-%m-%Y}.html", path))
            return httpx.Response(302, headers={"location": str(target)})
        title = f"Kết quả xổ số Mega 6/45 {date:%d/%m/%Y}"
        body = self.page_for_index(self.index[date])
        return httpx.Response(200, text=f"<html><head><title>{title}</title></head><body>{body}</body></html>")

    def fetcher(self, **kw) -> Fetcher:
        client = httpx.Client(
            transport=httpx.MockTransport(self.handler),
            headers={"User-Agent": UA}, follow_redirects=True,
        )
        kw.setdefault("min_interval", 0)
        kw.setdefault("sleep", lambda s: None)
        return Fetcher(user_agent=UA, client=client, **kw)
