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


def test_historical_bridge_clicks_purged_once_and_meta_app_installs_sdk_state(db_session):
    """
    v4.56.4:
    1) 2026-11-22 07:38 UTC öncesindeki eski /ios ve /download köprü tıklamaları ensure_historical_seed
       tarafından tek seferlik temizlenmeli (StoreSyncState bridge_reset_v4564_done işaretçisiyle).
    2) Sıfırlamadan sonra gelen yeni Instagram Bio (/download) tıklamaları korunmalı ve tek aktif köprü
       olarak raporlanmalı.
    3) Android doğrudan Meta APP_INSTALLS aktif görünmeli; iOS 14+ ATT/SKAdNetwork ise 4.56.0 (Build 72)
       cihaz sinyali gelene kadar 'waiting_for_review', sinyal gelince 'live' durumuna geçmeli.
    """
    import os
    from datetime import datetime, timezone
    from app.db.models import BridgeClick, AppInstallSignal, StoreSyncState
    from app.api.v1.endpoints.analytics import (
        BRIDGE_RESET_V4564_STATE_KEY,
        ensure_historical_seed,
        get_resilient_analytics_summary,
        invalidate_analytics_summary_cache,
    )

    # Eğer önceki ensure_historical_seed çağrısından marker oluşmuşsa silerek ilk göç anını simüle et
    db_session.query(StoreSyncState).filter(StoreSyncState.state_key == BRIDGE_RESET_V4564_STATE_KEY).delete()
    db_session.query(BridgeClick).delete()
    db_session.query(AppInstallSignal).delete()
    db_session.commit()

    # Eski dönemden (Ekim/Kasım başı) kalma /ios, /download ve /android tıklamaları + yeni dönem /download tıklaması
    old_ts = datetime(2026, 11, 10, 12, 0, 0)
    new_ts = datetime(2026, 11, 22, 9, 0, 0)
    db_session.add_all([
        BridgeClick(
            route_path="/ios",
            channel="meta_ads",
            os_family="ios",
            device_detail="iPhone",
            app_webview="Instagram App",
            target_store="app_store",
            is_bot=False,
            is_unique=True,
            country="TR",
            ip_masked="1.2.3.xxx#1111",
            created_at=old_ts,
        ),
        BridgeClick(
            route_path="/download",
            channel="instagram_bio",
            os_family="android",
            device_detail="Android Phone",
            app_webview="Instagram App",
            target_store="google_play",
            is_bot=False,
            is_unique=True,
            has_fbclid=False,
            country="TR",
            ip_masked="1.2.4.xxx#2222",
            created_at=old_ts,
        ),
        BridgeClick(
            route_path="/download",
            channel="meta_ads",
            os_family="android",
            device_detail="Android Phone",
            app_webview="Facebook App",
            target_store="google_play",
            is_bot=False,
            is_unique=True,
            has_fbclid=True,
            fbclid="IwAR_old_ad_click",
            country="TR",
            ip_masked="1.2.9.xxx#9999",
            created_at=old_ts,
        ),
        BridgeClick(
            route_path="/android",
            channel="google_play_direct",
            os_family="desktop",
            device_detail="Windows (Masaüstü)",
            app_webview="Chrome Mobile",
            target_store="app_store",
            is_bot=False,
            is_unique=True,
            country="TR",
            ip_masked="204.52.101.xxx#e82f",
            created_at=old_ts,
        ),
        BridgeClick(
            route_path="/download",
            channel="instagram_bio",
            os_family="ios",
            device_detail="iPhone",
            app_webview="Instagram App",
            target_store="app_store",
            is_bot=False,
            is_unique=True,
            country="TR",
            ip_masked="5.6.7.xxx#3333",
            created_at=new_ts,
        ),
    ])
    db_session.commit()

    # Göç çalıştığında eski reklam/diğer 3 tıklama (/ios, fbclid'li /download, /android) silinmeli;
    # organik /download (has_fbclid=False) tıklamaları korunmalı (1 eski organik + 1 yeni organik = 2)
    os.environ["MISIL_FORCE_BRIDGE_RESET_IN_TEST"] = "1"
    try:
        ensure_historical_seed(db_session)
    finally:
        os.environ.pop("MISIL_FORCE_BRIDGE_RESET_IN_TEST", None)
    remaining_clicks = db_session.query(BridgeClick).all()
    assert len(remaining_clicks) == 2
    assert all(rc.route_path == "/download" and not rc.has_fbclid for rc in remaining_clicks)

    marker = db_session.query(StoreSyncState).filter(StoreSyncState.state_key == BRIDGE_RESET_V4564_STATE_KEY).first()
    assert marker is not None
    assert marker.snapshot_json.get("purged_bridge_clicks") == 3

    invalidate_analytics_summary_cache(mark_reconcile=False)
    summary_before_sdk = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    assert summary_before_sdk["total_unique_human"] == 2
    assert summary_before_sdk["instagram_bio"]["unique_clicks"] == 2
    assert summary_before_sdk["instagram_bio"]["is_sole_active_bridge"] is True
    assert summary_before_sdk["meta_ads"]["unique_clicks"] == 0

    sdk_info = summary_before_sdk["meta_app_installs_sdk"]
    assert sdk_info["android_direct_app_installs_active"] is True
    assert sdk_info["ios_direct_app_installs_active"] is True
    assert "Bekleniyor" not in sdk_info["ios_sdk_status_badge"]
    assert "🟢 iOS Reklamları" in sdk_info["ios_sdk_status_badge"]
    assert sdk_info["ios_sdk_status"] == "waiting_for_review"
    assert sdk_info["ios_sdk_live_devices"] == 0
    assert "🎯 Meta Reklam Aktif" in summary_before_sdk["platform_split"]["ios"]["meta_chips_1"]

    # iOS 4.56.0 (Build 72) cihazından ilk sinyal geldiğinde durum otomatik 'live' olmalı
    db_session.add(
        AppInstallSignal(
            device_uid="ios_build72_dev1",
            event_type="first_open",
            os_family="ios",
            platform="ios_native",
            app_version="4.56.0",
            country="TR",
            matched_channel="organic_or_asa",
            match_confidence="unmatched",
            created_at=new_ts,
        )
    )
    db_session.commit()
    invalidate_analytics_summary_cache(mark_reconcile=False)
    summary_after_sdk = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    sdk_live = summary_after_sdk["meta_app_installs_sdk"]
    assert sdk_live["ios_direct_app_installs_active"] is True
    assert sdk_live["ios_sdk_status"] == "live"
    assert sdk_live["ios_sdk_live_devices"] == 1
    assert "🟢 iOS Reklamları & SDK Aktif (1 Cihaz)" == sdk_live["ios_sdk_status_badge"]


def test_android_store_metrics_consolidation_no_fake_100_cvr_and_clean_executive_ui(client, db_session):
    """
    1) Android StoreDailyMetric (impressions, page_views, downloads, active_sessions) verilerinin
       kümülatif KPI'lara (impressions_total, store_page_views, visits_and_clicks_total, active_sessions)
       ve platform_split['android'] içerisine konsolide edildiğini doğrular.
    2) Android gösterim veya sayfa ziyareti 0 olduğunda:
       - Büyük sayı (big-num) alanında asla 'Meta APP_INSTALLS' veya 'Doğrudan Play' metni çıkmadığını ('0' sayısal),
       - Android kurulumlarının kendisine bölünerek sahte %100.0 CVR üretilmediğini (%0.0),
       - Kümülatif (Tümü) sekmesinde iOS+Android toplam indirmelerinin yalnızca iOS sayfa ziyaretine bölünerek
         Simpson paradoksu (%37.8) üretmediğini doğrular.
    3) Sekme 1 Ülke Kurulumları tablosunun ve Donut grafiğinin yalnızca iOS değil, iOS + Android toplam kurulumlarını
       konsolide gösterdiğini ve arayüzde 'App ID: 1093539003520092', 'META APP_INSTALLS', 'Opt-in r8' gibi
       kaba mühendislik kodlarının yer almadığını doğrular.
    """
    from app.db.models import BridgeClick, CampaignConfig, StoreDailyMetric
    from app.api.v1.endpoints.analytics import (
        get_resilient_analytics_summary,
        invalidate_analytics_summary_cache,
    )

    db_session.query(BridgeClick).delete()
    db_session.query(CampaignConfig).delete()
    db_session.query(StoreDailyMetric).delete()
    db_session.commit()

    # Senaryo A: Android mağaza gösterimi/sayfa ziyareti henüz 0 iken (181 iOS + 222 Android = 403 Kurulum)
    db_session.add_all([
        StoreDailyMetric(
            metric_date="2026-11-20",
            platform="ios",
            impressions=6448,
            impressions_unique=5211,
            page_views=1062,
            page_views_unique=839,
            downloads_total=181,
            active_sessions=420,
        ),
        StoreDailyMetric(
            metric_date="2026-11-20",
            platform="android",
            impressions=0,
            impressions_unique=0,
            page_views=0,
            page_views_unique=0,
            downloads_total=222,
            active_sessions=0,
        ),
    ])
    db_session.commit()

    invalidate_analytics_summary_cache(mark_reconcile=False)
    s_zero_and = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    ps_all_a = s_zero_and["platform_split"]["all"]
    ps_and_a = s_zero_and["platform_split"]["android"]

    # Büyük sayı alanları metin değil temiz rakam olmalı ve sahte %100 CVR veya %37.8 Simpson paradoksu olmamalı
    assert ps_and_a["impressions_display"] == "0"
    assert ps_and_a["touchpoints_display"] == "0"
    assert ps_and_a["cvr_pct"] == 0.0
    assert ps_all_a["store_cvr_pct"] == 17.0
    assert ps_all_a["cvr_pct"] == 17.0

    # Senaryo B: Android StoreDailyMetric gösterim (3,552) ve sayfa ziyareti (938) + oturum (180) geldiğinde tam konsolidasyon
    and_row = db_session.query(StoreDailyMetric).filter_by(platform="android", metric_date="2026-11-20").one()
    and_row.impressions = 3552
    and_row.impressions_unique = 2800
    and_row.page_views = 938
    and_row.page_views_unique = 760
    and_row.active_sessions = 180
    db_session.commit()

    invalidate_analytics_summary_cache(mark_reconcile=False)
    s_cons = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    kpis_b = s_cons["cumulative_kpis"]
    ps_all_b = s_cons["platform_split"]["all"]
    ps_and_b = s_cons["platform_split"]["android"]

    assert kpis_b["impressions_total"] == 6448 + 3552
    assert kpis_b["store_page_views"] == 1062 + 938
    assert kpis_b["visits_and_clicks_total"] == 2000
    assert kpis_b["downloads_total"] == 403
    assert kpis_b["active_sessions"] == 420 + 180
    assert ps_and_b["impressions_display"] == "3,552"
    assert ps_and_b["touchpoints_display"] == "938"
    assert ps_and_b["cvr_pct"] == round((222 / 938) * 100, 1)
    assert ps_all_b["store_cvr_pct"] == round((403 / 2000) * 100, 1)

    dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
    assert dash_res.status_code == 200
    html_txt = dash_res.text

    # Ülke kurulumları konsolide toplam kurulumu (403 Kurulum) göstermeli, teknik kodlar görünür UI'dan kalkmış olmalı
    assert "403 Kurulum" in html_txt
    assert "🍏 iOS + 🤖 Android Reklamları Aktif" in html_txt
    assert "⏳ iOS v4.56.0 Mağaza Onayı Bekleniyor" not in html_txt
    assert "⏳ v4.56.0 Onayda" not in html_txt
    assert "App ID: 1093539003520092" not in html_txt
    assert "🤖 APP_INSTALLS Aktif" not in html_txt
    assert "Opt-in r8" not in html_txt


def test_churn_chips_promo_code_reconcile_and_android_telemetry_derived_impressions(client, db_session):
    """
    1) 4. Aktif VIP kartındaki meta_chips_4 rozetlerinde '2 Paket' yerine tüm platformlarda (all, ios, android)
       iptal sayısı ve churn yüzdesinin ('✖ X İptal (%Y Churn)') yer aldığını doğrular.
    2) DamlaEge2026 kodlu (2027-10-20 vadeli) olup intro_free_trial kalmış iOS #595636574492241 kaydının
       _reconcile_ios_ledger_and_cancellations ile 'offer_code_trial' olarak onarıldığını doğrular.
    3) Doğrulanmış Android telemetrisi (first_open + instagram_bio eşleşmesi + paywall_viewed) mevcutken
       StoreDailyMetric(android) gösterimi 0 olsa dahi Android mağaza gösterimi, mağaza ziyareti ve Bio
       profil trafiğinin 0 kalmadığını doğrular.
    """
    from datetime import datetime, timezone
    from app.db.models import AppInstallSignal, BridgeClick, StoreDailyMetric, SubscriberLedger
    from app.api.v1.endpoints.analytics import (
        get_resilient_analytics_summary,
        invalidate_analytics_summary_cache,
    )

    db_session.query(BridgeClick).delete()
    db_session.query(AppInstallSignal).delete()
    db_session.query(StoreDailyMetric).delete()
    db_session.query(SubscriberLedger).delete()
    db_session.commit()

    db_session.add_all([
        StoreDailyMetric(
            metric_date="2026-11-20",
            platform="ios",
            impressions=10928,
            impressions_unique=7685,
            page_views=1062,
            page_views_unique=829,
            downloads_total=181,
            active_sessions=90,
        ),
        StoreDailyMetric(
            metric_date="2026-11-20",
            platform="android",
            impressions=0,
            impressions_unique=0,
            page_views=0,
            page_views_unique=0,
            downloads_total=225,
            active_sessions=0,
        ),
    ])

    now_ts = datetime(2026, 11, 22, 10, 0, 0, tzinfo=timezone.utc)
    db_session.add_all([
        AppInstallSignal(
            device_uid="and_bio_1",
            event_type="first_open",
            os_family="android",
            platform="android_native",
            app_version="4.55.0",
            country="TR",
            matched_channel="instagram_bio",
            match_confidence="high",
            created_at=now_ts,
        ),
        AppInstallSignal(
            device_uid="and_pw_1",
            event_type="paywall_viewed",
            os_family="android",
            platform="android_native",
            app_version="4.55.0",
            country="TR",
            matched_channel="organic_or_asa",
            match_confidence="unmatched",
            created_at=now_ts,
        ),
        SubscriberLedger(
            subscriber_id="595636574492241",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            offer_code_name="DamlaEge2026",
            started_date="2026-10-20",
            maturity_or_renewal_date="2027-10-20",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.50,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="GPA.3393-7847-2790-81158",
            platform="android",
            product_id="misilaylik",
            plan_label="Mışıl Baby Aylık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            offer_code_name="Deneme / Promosyon (Google Play)",
            started_date="2026-11-19",
            maturity_or_renewal_date="2026-11-26",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=109.04,
            country="TR",
            device_type="Android",
        ),
        SubscriberLedger(
            subscriber_id="GPA.3300-4310-2609-37553",
            platform="android",
            product_id="misilaylik",
            plan_label="Mışıl Baby Aylık VIP",
            status="cancelled",
            offer_type="intro_7d_trial",
            offer_code_name="İptal / 72s Onaysız (Google Play)",
            started_date="2026-11-18",
            maturity_or_renewal_date="2026-11-25",
            auto_renew_enabled=False,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=0.0,
            expected_next_proceeds_try=0.0,
            country="TR",
            device_type="Android",
        ),
    ])
    db_session.commit()

    invalidate_analytics_summary_cache(mark_reconcile=True)
    summary = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    fl = summary["financial_ledger"]
    ps_all = summary["platform_split"]["all"]
    ps_ios = summary["platform_split"]["ios"]
    ps_and = summary["platform_split"]["android"]

    # 1) DamlaEge2026 kaydı offer_code_trial'a onarılmış olmalı; yalnız 1 aktif deneme (Android) kalmalı
    assert fl["offer_code_subs_count"] == 1
    assert fl["pipeline_7d_trials_count"] == 1
    assert fl["cancelled_subs_count"] == 1
    assert fl["churn_rate_pct"] == round((1 / 3) * 100, 1)

    # 2) 6 Aşamalı Dönüşüm Hunisi: 4. Başlayan VIP (meta_chips_4), 5. İptaller/Churn (meta_chips_5), 6. Net Abone (meta_chips_6)
    assert ps_all["total_vip_count"] == 3
    assert ps_all["cancelled_vip_count"] == 1
    assert ps_all["vip_count"] == 2
    assert ps_all["retention_rate_pct"] == round(100.0 - ps_all["churn_rate_pct"], 1)
    assert ps_all["started_vip_of_dl_pct"] == round((3 / (181 + 225)) * 100, 1)

    assert any("Churn" in ch or "İptal" in ch for ch in ps_all["meta_chips_5"])
    assert any("Churn" in ch or "İptal" in ch for ch in ps_ios["meta_chips_5"])
    assert any("Churn" in ch or "İptal" in ch for ch in ps_and["meta_chips_5"])
    assert not any("Paket" in ch for ch in ps_and["meta_chips_4"] + ps_and["meta_chips_5"] + ps_and["meta_chips_6"])

    dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
    assert dash_res.status_code == 200
    assert "4. Başlayan VIP" in dash_res.text
    assert "5. İptaller (Churn)" in dash_res.text
    assert "6. Net Abone" in dash_res.text

    # 3) Canlı Android telemetrisi varken Android mağaza gösterimi ve sayfa ziyareti > 0 türetilmeli
    assert ps_and["impressions"] > 0
    assert ps_and["touchpoints"] > 0
    assert summary["instagram_bio"]["android_clicks"] >= 1


def test_period_filter_updates_funnel_ledger_and_tabs(client, db_session):
    """
    v4.56.14:
    Üst bardaki dönem seçici ('all', '7d', 'yesterday', 'today') değiştirildiğinde:
    1) 6 aşamalı Dönüşüm Hunisi (platform_split['all'/'ios'/'android']: impressions, touchpoints, downloads,
       total_vip_count, cancelled_vip_count, vip_count),
    2) Sekme 1 timeline_days ve edinim kanalları (aso_attribution_matrix),
    3) Sekme 2 Abone Defteri (subscriber_ledger) ve Ülke Gelirleri (country_revenue_breakdown),
    4) Sekme 3 Ürün Kullanımı & Paywall Hunisi (product_funnel)
    seçilen zaman penceresine göre dinamik olarak süzülmeli; 'all' ile 'today'/'yesterday'/'7d' aynı kalmamalıdır.
    """
    from datetime import datetime, timedelta, timezone
    from app.db.models import AppInstallSignal, BridgeClick, StoreDailyMetric, SubscriberLedger
    from app.api.v1.endpoints.analytics import (
        get_resilient_analytics_summary,
        invalidate_analytics_summary_cache,
    )

    db_session.query(BridgeClick).delete()
    db_session.query(AppInstallSignal).delete()
    db_session.query(StoreDailyMetric).delete()
    db_session.query(SubscriberLedger).delete()
    db_session.commit()

    tz_tr = timezone(timedelta(hours=3))
    now_tr = datetime.now(tz_tr)
    today_str = now_tr.strftime("%Y-%m-%d")
    yesterday_str = (now_tr - timedelta(days=1)).strftime("%Y-%m-%d")
    old_20d_str = (now_tr - timedelta(days=20)).strftime("%Y-%m-%d")
    old_20d_utc = (now_tr - timedelta(days=20)).astimezone(timezone.utc).replace(tzinfo=None)
    today_utc = now_tr.astimezone(timezone.utc).replace(tzinfo=None)

    # 20 gün önce yüksek gösterim/indirme vs dün ve bugün daha düşük günlük metrikler
    db_session.add_all([
        StoreDailyMetric(
            metric_date=old_20d_str,
            platform="ios",
            impressions=5000,
            impressions_unique=4000,
            page_views=800,
            page_views_unique=650,
            downloads_total=120,
            downloads_search=90,
            downloads_referrer=20,
            downloads_browse=10,
            active_sessions=300,
        ),
        StoreDailyMetric(
            metric_date=yesterday_str,
            platform="ios",
            impressions=400,
            impressions_unique=320,
            page_views=60,
            page_views_unique=50,
            downloads_total=12,
            downloads_search=8,
            downloads_referrer=3,
            downloads_browse=1,
            active_sessions=40,
        ),
        StoreDailyMetric(
            metric_date=old_20d_str,
            platform="android",
            impressions=2000,
            impressions_unique=1500,
            page_views=350,
            page_views_unique=280,
            downloads_total=80,
            active_sessions=110,
        ),
        StoreDailyMetric(
            metric_date=yesterday_str,
            platform="android",
            impressions=150,
            impressions_unique=120,
            page_views=30,
            page_views_unique=25,
            downloads_total=8,
            active_sessions=15,
        ),
    ])

    # 20 gün önce başlayan eski abone vs bugün başlayan yeni abone
    db_session.add_all([
        SubscriberLedger(
            subscriber_id="OLD_SUB_20D_111111",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="paid_active",
            offer_type="standard_paid",
            offer_code_name="7 Günlük Deneme",
            started_date=old_20d_str,
            converted_or_renewed_date=old_20d_str,
            maturity_or_renewal_date=(now_tr + timedelta(days=10)).strftime("%Y-%m-%d"),
            auto_renew_enabled=True,
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="TODAY_SUB_222222",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="paid_active",
            offer_type="standard_paid",
            offer_code_name="Doğrudan Yıllık",
            started_date=today_str,
            converted_or_renewed_date=today_str,
            maturity_or_renewal_date=(now_tr + timedelta(days=365)).strftime("%Y-%m-%d"),
            auto_renew_enabled=True,
            customer_price_try=599.99,
            developer_proceeds_try=332.50,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.50,
            country="DE",
            device_type="iPhone",
        ),
    ])

    # Sinyaller: 20 gün önce 2 paywall_viewed, bugün 1 paywall_viewed
    db_session.add_all([
        AppInstallSignal(
            device_uid="old_dev_1",
            event_type="paywall_viewed",
            os_family="ios",
            platform="ios_native",
            app_version="4.55.0",
            country="TR",
            created_at=old_20d_utc,
        ),
        AppInstallSignal(
            device_uid="old_dev_2",
            event_type="paywall_viewed",
            os_family="android",
            platform="android_native",
            app_version="4.55.0",
            country="TR",
            created_at=old_20d_utc,
        ),
        AppInstallSignal(
            device_uid="today_dev_1",
            event_type="paywall_viewed",
            os_family="ios",
            platform="ios_native",
            app_version="4.56.0",
            country="DE",
            created_at=today_utc,
        ),
    ])
    db_session.commit()

    invalidate_analytics_summary_cache(mark_reconcile=False)
    s_all = get_resilient_analytics_summary(db_session, period="all", use_cache=False)
    s_7d = get_resilient_analytics_summary(db_session, period="7d", use_cache=False)
    s_yest = get_resilient_analytics_summary(db_session, period="yesterday", use_cache=False)
    s_today = get_resilient_analytics_summary(db_session, period="today", use_cache=False)

    # 1) Tüm Zamanlar vs Son 7 Gün vs Dün vs Bugün: Mağaza gösterimi ve kurulumlar döneme göre değişmeli
    assert s_all["platform_split"]["all"]["impressions"] == 5000 + 400 + 2000 + 150
    assert s_all["platform_split"]["all"]["downloads"] == 120 + 12 + 80 + 8
    assert s_7d["platform_split"]["all"]["impressions"] == 400 + 150
    assert s_7d["platform_split"]["all"]["downloads"] == 12 + 8
    assert s_yest["platform_split"]["all"]["impressions"] == 400 + 150
    assert s_yest["platform_split"]["all"]["downloads"] == 12 + 8
    assert s_today["platform_split"]["all"]["impressions"] == 0

    # 2) Abone Defteri ve Dönüşüm Hunisi VIP sayısı seçilen döneme göre filtrelenmeli
    assert len(s_all["subscriber_ledger"]) == 2
    assert s_all["platform_split"]["all"]["total_vip_count"] == 2
    assert len(s_today["subscriber_ledger"]) == 1
    assert s_today["subscriber_ledger"][0]["subscriber_id"] == "TODAY_SUB_222222"
    assert s_today["platform_split"]["all"]["total_vip_count"] == 1
    assert s_today["platform_split"]["all"]["vip_count"] == 1

    # 3) Ürün Hunisi (Paywall) sinyalleri seçilen döneme göre filtrelenmeli
    assert s_all["product_funnel"]["paywall_funnel"]["paywall_viewed"] == 3
    assert s_today["product_funnel"]["paywall_funnel"]["paywall_viewed"] == 1

    # 4) Dashboard HTML çıktısı da period parametresine göre güncellenmeli ve Mışıl Baby kurumsal marka tokenlarını barındırmalı
    res_all = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842", "period": "all"})
    res_today = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842", "period": "today"})
    assert res_all.status_code == 200
    assert res_today.status_code == 200
    assert "#111111" in res_all.text
    assert "#222222" in res_all.text
    assert "#111111" not in res_today.text
    assert "#222222" in res_today.text
    assert "Bugün (TSİ)" in res_today.text
    # Mışıl Baby kurumsal renk ve tasarım tokenları (Sıcak Kaşmir #13101C, Kehribar #F4A261, Pişmiş Toprak #C86446, Adaçayı #74C69D)
    assert "#13101C" in res_all.text
    assert "#F4A261" in res_all.text
    assert "#C86446" in res_all.text
    assert "#74C69D" in res_all.text
    assert "#2C201A" in res_all.text
    # .card-desc ve .step-sub açıklamaları .sr-only ile gizlenmemiş olmalı, jenerik Tailwind rgba kalıntıları temizlenmiş olmalı ve --stage-N-rgb dinamik tema değişkenleri kullanılmalı
    assert ".sr-only,\n        .card-desc" not in res_all.text
    assert "rgba(79, 70, 229" not in res_all.text
    assert "rgba(220,38,38" not in res_all.text
    assert "rgba(13,148,136" not in res_all.text
    assert "--stage-1-rgb:" in res_all.text
    assert "rgba(var(--stage-1-rgb)," in res_all.text
    assert "rgba(var(--stage-6-rgb)," in res_all.text






