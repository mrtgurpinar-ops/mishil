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


def test_reactivate_downgrade_rc_t0_dedup_and_trial_will_not_renew_reconcile(client, db_session):
    """
    1) Reactivate with Downgrade yapan iOS abonesinin (started_date=2026-10-30, converted_or_renewed_date=2026-11-15)
       geçici RC_T0_* köprü satırı (started_date=2026-11-15, auto_renew_enabled=False) ile 1-e-1 tekilleştirildiğini,
       auto_renew_enabled=False (will_not_renew) durumunun resmi Apple satırına devredildiğini ve çifte sayımın önlendiğini doğrular.
    2) RevenueCat V2'de will_not_renew olan 7G iOS deneme abonesinin, Apple SUBSCRIPTION (1_3) active_trials_target=1
       bildirse dahi Reconcile Adım 3 tarafından yanlışlıkla tekrar intro_free_trial olarak geri yüklenmediğini doğrular.
    3) Ülke gelir tablosundaki (country_revenue_breakdown) expected_mrr_net_try toplamının, 1 yıl sonraki (Ekim 2027)
       offer_code_trial crossgrade tutarlarını karıştırmadan üstteki projected_total_mrr_net_try ile birebir eşit olduğunu doğrular.
    """
    from app.db.models import SubscriberLedger, SubscriptionLifecycleEvent
    from app.api.v1.endpoints.analytics import (
        _reconcile_ios_ledger_and_cancellations,
        invalidate_analytics_summary_cache,
    )

    db_session.query(SubscriberLedger).delete()
    db_session.query(SubscriptionLifecycleEvent).delete()
    db_session.commit()

    # 1) Resmi Apple satırı: 30 Ekim'de yıllık deneme başlatıp 15 Kasım'da Aylık Esnek VIP'e (149.99 TL) geçen abone
    db_session.add(
        SubscriberLedger(
            subscriber_id="259753775786416",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="paid_active",
            offer_type="standard_paid",
            offer_code_name="7 Günlük Deneme",
            started_date="2026-10-30",
            converted_or_renewed_date="2026-11-15",
            maturity_or_renewal_date="2026-12-15",
            auto_renew_enabled=True,
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        )
    )
    # Aynı işlem için Apple TSV gelmeden önce açılmış ve RC'de will_not_renew yakalamış geçici T-0 köprü satırı
    db_session.add(
        SubscriberLedger(
            subscriber_id="RC_T0_170003989417085",
            rc_app_user_id="$RCAnonymousID:1ea5e400c34c4fff9022733c342cc93d",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="paid_active",
            offer_type="standard_paid",
            offer_code_name="RevenueCat T-0 Canlı Köprü",
            started_date="2026-11-15",
            converted_or_renewed_date="2026-11-21",
            maturity_or_renewal_date="2026-12-15",
            auto_renew_enabled=False,
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=0.0,
            expected_next_proceeds_try=0.0,
            country="TR",
            device_type="iPhone",
        )
    )
    # 2) Oto-yenilemesi açık başka bir ücretli aylık abone
    db_session.add(
        SubscriberLedger(
            subscriber_id="455612656912233",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="paid_active",
            offer_type="standard_paid",
            offer_code_name="7 Günlük Deneme",
            started_date="2026-11-14",
            converted_or_renewed_date="2026-11-21",
            maturity_or_renewal_date="2026-12-21",
            auto_renew_enabled=True,
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        )
    )
    # 3) 17 Kasım'da başlayan ancak RevenueCat V2'de oto-yenilemesini kapatan (will_not_renew) iOS 7G deneme abonesi
    db_session.add(
        SubscriberLedger(
            subscriber_id="700518820757373",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            offer_code_name="7 Günlük Deneme",
            started_date="2026-11-17",
            maturity_or_renewal_date="2026-11-24",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        )
    )
    db_session.add(
        SubscriptionLifecycleEvent(
            event_date="2026-11-17",
            platform="ios",
            event_type="700518820757373:will_not_renew",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            country="TR",
            device_type="iPhone",
            quantity=1,
        )
    )
    # 4) Ekim 2027 vadeli, will_change_product seçmiş DamlaEge2026 kodlu abone
    db_session.add(
        SubscriberLedger(
            subscriber_id="658531636670315",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="offer_code_trial",
            offer_type="offer_code",
            offer_code_name="DamlaEge2026 ➔ Aylık VIP (149.99 ₺)",
            started_date="2026-10-21",
            maturity_or_renewal_date="2027-10-21",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        )
    )
    # Geçmiş bir iptal olayı (merged_cancels boş olmasın ki Adım 3 restorable bloğuna girsin)
    db_session.add(
        SubscriptionLifecycleEvent(
            event_date="2026-10-29",
            platform="ios",
            event_type="EVENT:Cancel:2026-10-22:TR:iPhone",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            country="TR",
            device_type="iPhone",
            quantity=1,
        )
    )
    db_session.commit()

    # Apple SUBSCRIPTION (1_3) hala active_trials_target=1 bildirirken mutabakatı çalıştır
    changed = _reconcile_ios_ledger_and_cancellations(db_session, active_trials_target=1)
    assert changed is True
    db_session.commit()

    # RC_T0_170003989417085 silinmiş ve bilgileri 259753775786416'ya devredilmiş olmalı
    assert db_session.query(SubscriberLedger).filter_by(subscriber_id="RC_T0_170003989417085").first() is None
    reactivated_row = db_session.query(SubscriberLedger).filter_by(subscriber_id="259753775786416").one()
    assert reactivated_row.rc_app_user_id == "$RCAnonymousID:1ea5e400c34c4fff9022733c342cc93d"
    assert reactivated_row.auto_renew_enabled is False
    assert reactivated_row.expected_next_price_try == 0.0
    assert reactivated_row.converted_or_renewed_date == "2026-11-15"

    # 700518820757373 deneme abonesi cancelled olmuş ve Adım 3 tarafından geri yüklenmemiş olmalı
    trial_wnr_row = db_session.query(SubscriberLedger).filter_by(subscriber_id="700518820757373").one()
    assert trial_wnr_row.status == "cancelled"
    assert trial_wnr_row.auto_renew_enabled is False
    assert trial_wnr_row.expected_next_price_try == 0.0

    invalidate_analytics_summary_cache(mark_reconcile=False)
    summary = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    fl = summary["financial_ledger"]

    # 2 gerçek ücretli abone (299.98 TL Brüt / 166.24 TL Net), yalnız 1 tanesinin oto-yenilemesi açık (83.12 TL Net MRR)
    assert fl["paid_subs_count"] == 2
    assert fl["realized_gross_try"] == 299.98
    assert fl["realized_net_proceeds_try"] == 166.24
    assert fl["active_paid_mrr_net_try"] == 83.12
    assert fl["pipeline_7d_trials_count"] == 0
    assert fl["projected_total_mrr_net_try"] == 83.12

    # Ülke tablosundaki Türkiye MRR değeri ile üst karttaki projected_total_mrr_net_try birebir aynı olmalı
    tr_row = next(c for c in fl["country_revenue_breakdown"] if c["code"] == "TR")
    assert tr_row["expected_mrr_net_try"] == fl["projected_total_mrr_net_try"]


