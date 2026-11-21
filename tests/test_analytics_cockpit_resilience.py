import time
from unittest.mock import patch

from app.api.v1.endpoints.analytics import (
    _PIN_BLOCK_UNTIL,
    _PIN_FAILED_ATTEMPTS,
    _PIN_RATE_LIMIT_LOCK,
    _SUMMARY_CACHE_TTL_SEC,
    get_resilient_analytics_summary,
)


def _clear_pin_rate_limit_state():
    with _PIN_RATE_LIMIT_LOCK:
        _PIN_FAILED_ATTEMPTS.clear()
        _PIN_BLOCK_UNTIL.clear()


def test_unauthenticated_login_screen_loads_do_not_trigger_429_lockout(client):
    """
    PIN girmeden yalnızca /admin/analytics veya /api/v1/analytics/dashboard giriş sayfasını
    5+ kez açmak brute-force sayacını artırmamalı ve 429 kilidine düşürmemelidir.
    """
    _clear_pin_rate_limit_state()
    client.cookies.clear()

    for _ in range(8):
        res = client.get("/api/v1/analytics/dashboard")
        assert res.status_code == 200
        assert "Mışıl Kurucu Kokpiti" in res.text

    # Hemen ardından doğru PIN ile giriş yapıldığında 429 almadan 200 OK açılmalıdır
    auth_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
    assert auth_res.status_code == 200
    assert "Dönüşüm Hunisi" in auth_res.text


def test_wrong_pin_brute_force_renders_html_on_dashboard_and_blocks_after_5_attempts(client):
    """Gerçekten hatalı PIN 5 kez gönderildiğinde brute-force koruması devreye girmeli ve dashboard HTML hata ekranı dönmelidir."""
    _clear_pin_rate_limit_state()
    client.cookies.clear()

    for _ in range(5):
        bad_res = client.get("/api/v1/analytics/dashboard", params={"pin": "WRONG-PIN-000"})
        assert bad_res.status_code == 401

    blocked_res = client.get("/api/v1/analytics/dashboard", params={"pin": "WRONG-PIN-000"})
    assert blocked_res.status_code == 429
    assert "Çok fazla hatalı PIN denemesi" in blocked_res.text
    assert "<html" in blocked_res.text.lower()

    _clear_pin_rate_limit_state()


def test_swr_fallback_prevents_500_when_db_raises_and_cache_ttl_exceeds_poll_interval(client, db_session):
    """
    1) _SUMMARY_CACHE_TTL_SEC (25s) >= 15s polling aralığı olmalı.
    2) _LAST_GOOD_SUMMARY_CACHE dolduktan sonra veritabanı hatası oluşursa 500 yerine SWR fallback dönmelidir.
    """
    _clear_pin_rate_limit_state()
    assert _SUMMARY_CACHE_TTL_SEC >= 20.0

    # Önce sağlam bir özet üreterek _LAST_GOOD_SUMMARY_CACHE'i ısıt
    initial_summary = get_resilient_analytics_summary(db_session, period="all", use_cache=True)
    assert "cumulative_kpis" in initial_summary

    # Şimdi _build_analytics_summary içinde geçici DB hatası simüle et
    with patch(
        "app.api.v1.endpoints.analytics._build_analytics_summary",
        side_effect=RuntimeError("Simulated Railway DB lock timeout"),
    ):
        swr_summary = get_resilient_analytics_summary(db_session, period="all", use_cache=True)
        assert swr_summary.get("stale_fallback") is True
        assert "cumulative_kpis" in swr_summary

        dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
        assert dash_res.status_code == 200
        assert "Hızlı Önbellek Koruma Modu (SWR)" in dash_res.text


def test_mobile_first_responsive_css_and_fast_cache_hit(client, db_session):
    """Mobil-öncelikli CSS kırılımları (@media (max-width: 768px), 480px, 2x2 grid), önbellek izolasyonu ve <50ms önbellek yanıtı doğrulanır."""
    _clear_pin_rate_limit_state()

    # İlk ısınma
    first = get_resilient_analytics_summary(db_session, period="all", use_cache=True)
    first["cumulative_kpis"]["impressions_total"] = 999999  # Dış mutasyon önbelleği kirletmemeli

    t0 = time.perf_counter()
    cached = get_resilient_analytics_summary(db_session, period="all", use_cache=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 50.0
    assert "cumulative_kpis" in cached
    assert cached["cumulative_kpis"]["impressions_total"] != 999999

    dash_res = client.get(
        "/api/v1/analytics/dashboard",
        params={"pin": "MISIL-REV-9842"},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert dash_res.status_code == 200
    assert "Secure" in dash_res.headers.get("set-cookie", "")
    html_text = dash_res.text
    assert "@media (max-width: 768px)" in html_text
    assert "@media (max-width: 480px)" in html_text
    assert "grid-template-columns: repeat(2, minmax(0, 1fr)) !important;" in html_text
    assert "AbortController" in html_text

