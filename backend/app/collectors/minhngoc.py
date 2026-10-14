"""Minh Ngoc (minhngoc.net.vn) - Vietlott Mega 6/45.

Observed layout (checked 2026-10-13):
  URL   https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/DD-MM-YYYY.html
  page  lists the draw of that date plus the 9 draws before it, newest first, each as

        <div class="box-result-detail">
          ... Kỳ vé: <span id="DT6X45_KY_VE">#01574</span> | Ngày quay thưởng 11/10/2026 ...
          <ul class="result-number"><li><div class="finnish1 bool">03</div></li> ... x6</ul>
        </div>

  A date with no published draw (future date, or a day nothing is drawn) does NOT give a
  404: the site redirects to the latest page. The caller must therefore compare the page's
  newest draw date with the date it asked for.
"""

from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from app.collectors.base import Collector, PageLayoutError
from app.importers.common import ParsedDraw

_KY = re.compile(r"Kỳ vé:\s*#?\s*(\d+)")
_DATE = re.compile(r"Ngày quay thưởng\s*(\d{2})/(\d{2})/(\d{4})")


class MinhNgocMega645(Collector):
    game_code = "vn_mega_645"
    source_name = "minhngoc.net.vn"
    draws_per_page = 10
    draw_weekdays = (2, 4, 6)  # Wednesday, Friday, Sunday

    BASE = "https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/{:02d}-{:02d}-{:04d}.html"

    def page_url(self, date: dt.date) -> str:
        return self.BASE.format(date.day, date.month, date.year)

    def parse_page(self, html: str) -> list[ParsedDraw]:
        soup = BeautifulSoup(html, "lxml")
        blocks = soup.select("div.box-result-detail")
        if not blocks:
            title = soup.title.get_text(strip=True) if soup.title else "no <title>"
            raise PageLayoutError(f"no div.box-result-detail result blocks found (page title: {title!r})")

        draws: list[ParsedDraw] = []
        for i, b in enumerate(blocks, start=1):
            text = re.sub(r"\s+", " ", b.get_text(" ", strip=True))
            ky, dm = _KY.search(text), _DATE.search(text)
            if not ky or not dm:
                raise PageLayoutError(
                    f"result block {i}: expected 'Kỳ vé: #nnnnn | Ngày quay thưởng dd/mm/yyyy', got {text[:120]!r}"
                )
            try:
                date = dt.date(int(dm.group(3)), int(dm.group(2)), int(dm.group(1)))
            except ValueError as exc:
                raise PageLayoutError(f"result block {i}: impossible date {dm.group(0)!r}") from exc
            balls = [e.get_text(strip=True) for e in b.select("ul.result-number div.bool")]
            if not balls:
                continue  # drawn-but-not-yet-published placeholder: no result to take
            if len(balls) != 6 or not all(re.fullmatch(r"\d{1,2}", x) for x in balls):
                raise PageLayoutError(
                    f"result block {i} (draw {int(ky.group(1))}): expected 6 numeric balls, got {balls!r}"
                )
            draws.append(
                ParsedDraw(
                    numbers=[int(x) for x in balls],  # validated against the game by the caller
                    draw_date=date,
                    draw_no=int(ky.group(1)),
                    line_no=i,
                )
            )

        if not draws:
            raise PageLayoutError("result blocks present but none has numbers")
        for a, b in zip(draws, draws[1:]):
            if not (a.draw_no == b.draw_no + 1 and a.draw_date > b.draw_date):
                raise PageLayoutError(
                    f"blocks are not consecutive newest-first: draw {a.draw_no} ({a.draw_date}) "
                    f"followed by {b.draw_no} ({b.draw_date})"
                )
        return draws
