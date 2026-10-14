import datetime as dt

import httpx
import pytest

from app.collectors import PageLayoutError, SourceUnreachable
from app.collectors.fetcher import Fetcher
from app.collectors.minhngoc import MinhNgocMega645
from tests.conftest import FIXTURES
from tests.fakesite import UA, FakeSite, SeedDraw, load_seed, render_block, render_page

C = MinhNgocMega645()
D = dt.date


# ---------- parsing ----------


def test_real_page_fixture_parses_and_matches_seed():
    html = (FIXTURES / "minhngoc_11-10-2026.html").read_text(encoding="utf-8")
    draws = C.parse_page(html)
    assert [d.draw_no for d in draws] == list(range(1574, 1564, -1))  # newest first
    assert draws[0].draw_date == D(2026, 10, 11) and draws[0].numbers == [3, 9, 16, 29, 30, 44]
    assert draws[3].draw_no == 1571 and draws[3].numbers == [15, 20, 29, 37, 40, 45]
    seed = {d.draw_no: d for d in load_seed()}
    for d in draws:  # the live page agrees with the seed for these ten draws
        assert (seed[d.draw_no].date, seed[d.draw_no].numbers) == (d.draw_date, d.numbers)


def test_page_url_and_schedule():
    assert C.page_url(D(2026, 10, 11)).endswith("/mega-6x45/11-10-2026.html")
    assert C.latest_scheduled_on_or_before(D(2026, 10, 13)) == D(2026, 10, 11)  # Tue -> Sun
    assert C.latest_scheduled_on_or_before(D(2026, 10, 14)) == D(2026, 10, 14)  # Wed
    assert C.previous_scheduled(D(2026, 10, 11)) == D(2026, 10, 9)  # Sun -> Fri
    assert C.previous_scheduled(D(2026, 10, 9)) == D(2026, 10, 7)  # Fri -> Wed
    assert C.previous_scheduled(D(2026, 10, 7)) == D(2026, 10, 4)  # Wed -> Sun


def _sd(no, date, nums):
    return SeedDraw(no, date, nums)


def test_layout_drift_is_an_error_not_a_guess():
    ok = [_sd(11, D(2026, 1, 9), [1, 2, 3, 4, 5, 6]), _sd(10, D(2026, 1, 7), [7, 8, 9, 10, 11, 12])]
    assert len(C.parse_page(render_page(ok))) == 2

    with pytest.raises(PageLayoutError, match="no div.box-result-detail"):
        C.parse_page("<html><title>URL không tồn tại</title><body></body></html>")

    five = render_block(ok[0], [1, 2, 3, 4, 5]) + render_block(ok[1])
    with pytest.raises(PageLayoutError, match="expected 6 numeric balls"):
        C.parse_page(f"<html><body>{five}</body></html>")

    no_ky = render_block(ok[0]).replace("Kỳ vé", "Ky")
    with pytest.raises(PageLayoutError, match="expected 'Kỳ vé"):
        C.parse_page(f"<html><body>{no_ky}</body></html>")

    out_of_order = render_block(ok[1]) + render_block(ok[0])  # oldest first
    with pytest.raises(PageLayoutError, match="not consecutive"):
        C.parse_page(f"<html><body>{out_of_order}</body></html>")

    skipped = render_block(_sd(12, D(2026, 1, 11), [1, 2, 3, 4, 5, 6])) + render_block(
        _sd(10, D(2026, 1, 7), [7, 8, 9, 10, 11, 12])
    )
    with pytest.raises(PageLayoutError, match="not consecutive"):
        C.parse_page(f"<html><body>{skipped}</body></html>")


def test_placeholder_block_without_numbers_is_skipped():
    drawn = _sd(11, D(2026, 1, 9), [1, 2, 3, 4, 5, 6])
    pending = render_block(_sd(12, D(2026, 1, 11), []), balls=[])
    html = f"<html><body>{pending}{render_block(drawn)}</body></html>"
    assert [d.draw_no for d in C.parse_page(html)] == [11]


# ---------- fetcher ----------


def test_fetcher_sends_user_agent_and_rate_limits_per_host():
    site = FakeSite(load_seed())
    now = [100.0]
    slept: list[float] = []

    def sleep(s):
        slept.append(s)
        now[0] += s

    f = site.fetcher(min_interval=5.0, clock=lambda: now[0], sleep=sleep)
    for d in ("11-10-2026", "09-10-2026", "07-10-2026"):
        f.get(f"https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/{d}.html")
    assert site.user_agents == [UA] * 3
    assert slept == [5.0, 5.0]  # nothing before the first request, then a full interval each time
    assert f.requests_made == 3


def test_fetcher_cache_ttl_and_cache_if(tmp_path):
    site = FakeSite(load_seed())
    f = site.fetcher(cache_dir=tmp_path)
    url = "https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/11-10-2026.html"
    a = f.get(url)
    b = f.get(url)
    assert (a.from_cache, b.from_cache, len(site.requests)) == (False, True, 1)
    c = f.get(url, ttl=0)  # fresh request bypasses the cache
    assert (c.from_cache, len(site.requests)) == (False, 2)

    url2 = url.replace("11-10-2026", "09-10-2026")
    f.get(url2, cache_if=lambda r: False)  # e.g. a "not published" answer must not be remembered
    f.get(url2)
    assert len(site.requests) == 4


def test_fetcher_retries_server_errors_then_gives_up():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503)

    f = Fetcher(UA, min_interval=0, retries=2, sleep=lambda s: None,
                client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(SourceUnreachable, match="HTTP 503"):
        f.get("https://example.test/x")
    assert len(calls) == 3  # 1 + 2 retries


def test_fetcher_does_not_retry_client_errors():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(404)

    f = Fetcher(UA, min_interval=0, retries=2, sleep=lambda s: None,
                client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(SourceUnreachable, match="HTTP 404"):
        f.get("https://example.test/x")
    assert len(calls) == 1


def test_fetcher_recovers_after_transient_failure():
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectTimeout("slow", request=req)
        return httpx.Response(200, text="ok")

    f = Fetcher(UA, min_interval=0, retries=2, sleep=lambda s: None,
                client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert f.get("https://example.test/x").text == "ok"


def test_fake_site_redirects_unknown_dates_to_latest_like_the_real_one():
    site = FakeSite(load_seed())
    f = site.fetcher()
    res = f.get("https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/14-10-2026.html")
    assert res.final_url.endswith("/11-10-2026.html")
    assert C.parse_page(res.text)[0].draw_no == 1574
