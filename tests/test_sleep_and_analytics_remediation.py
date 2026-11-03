from datetime import datetime, timezone

from app.db.models import Baby, FamilyGroup, SleepLog, User
from app.api.v1.endpoints.sleep import create_or_update_sleep_log, SleepLogCreateRequest


def _seed_family(db, code, baby_name):
    user = User(email=f"{code.lower()}@example.com", hashed_password="x", full_name=code)
    db.add(user)
    db.flush()
    family = FamilyGroup(invite_code=code, created_by_user_id=user.id)
    db.add(family)
    db.flush()
    baby = Baby(
        user_id=user.id, family_id=family.id, name=baby_name,
        birth_date=datetime(2026, 4, 11, tzinfo=timezone.utc),
    )
    db.add(baby)
    db.commit()
    return baby


def test_unknown_client_id_update_does_not_overwrite_latest_sleep(db_session):
    baby = _seed_family(db_session, "FAM001", "A")
    original = SleepLog(
        baby_id=baby.id,
        start_time=datetime(2026, 10, 29, 8, tzinfo=timezone.utc),
        notes="existing",
    )
    db_session.add(original)
    db_session.commit()

    response = create_or_update_sleep_log(
        SleepLogCreateRequest(
            baby_id=baby.id, client_id="unknown", is_update=True,
            start_time=datetime(2026, 10, 29, 12, tzinfo=timezone.utc), duration_minutes=30,
        ),
        db_session,
    )

    db_session.refresh(original)
    assert original.start_time.isoformat().startswith("2026-10-29T08:00:00")
    assert db_session.query(SleepLog).filter(SleepLog.baby_id == baby.id).count() == 2
    assert response.id != original.id


def test_family_code_cannot_be_combined_with_another_babys_id(client, db_session):
    _seed_family(db_session, "FAM001", "A")
    baby_b = _seed_family(db_session, "FAM002", "B")
    result = client.post(
        "/api/v1/sleep/log",
        json={"family_code": "FAM001", "baby_id": baby_b.id, "duration_minutes": 20},
    )
    assert result.status_code in (403, 404)


def test_sleep_update_like_characters_do_not_match_a_different_client_token(db_session):
    baby = _seed_family(db_session, "FAM003", "C")
    unrelated = SleepLog(
        baby_id=baby.id,
        start_time=datetime(2026, 10, 29, 8, tzinfo=timezone.utc),
        notes="[cid:abcXdef]",
    )
    db_session.add(unrelated)
    db_session.commit()

    response = create_or_update_sleep_log(
        SleepLogCreateRequest(
            baby_id=baby.id, client_id="abc_def", is_update=True, duration_minutes=15,
        ),
        db_session,
    )

    db_session.refresh(unrelated)
    assert unrelated.duration_minutes is None
    assert response.id != unrelated.id


def test_first_open_is_idempotent_and_invalid_admin_pin_is_rejected(client, db_session):
    from app.db.models import AppInstallSignal

    AppInstallSignal.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    payload = {"event_type": "first_open", "device_uid": "remediation-device", "os_family": "android"}
    first = client.post("/api/v1/analytics/app-open-signal", json=payload)
    second = client.post("/api/v1/analytics/app-open-signal", json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json().get("status") == "already_recorded"

    response = client.get("/admin/analytics", params={"pin": "invalid-test-pin"})
    assert response.status_code in (401, 403)


def test_google_play_reviewer_pin_rejected_on_admin_analytics(client):
    """P0-2: Google Play Reviewer PIN (MISILREV2026) yönetici kokpitine erişememelidir."""
    res_dash = client.get("/admin/analytics", params={"pin": "MISILREV2026"})
    assert res_dash.status_code == 401

    res_sum = client.get("/api/v1/analytics/summary", params={"pin": "MISILREV2026"})
    assert res_sum.status_code == 401


def test_expired_admin_session_token_is_rejected():
    """P1-3: Süresi dolmuş (exp < now) oturum token'ı sunucu tarafında reddedilmelidir."""
    import time
    from app.api.v1.endpoints.analytics import (
        _make_admin_session_token,
        _admin_session_token_is_valid,
    )

    valid_tok = _make_admin_session_token("MISIL-REV-9842", exp_ts=int(time.time()) + 3600)
    expired_tok = _make_admin_session_token("MISIL-REV-9842", exp_ts=int(time.time()) - 10)

    assert _admin_session_token_is_valid(valid_tok) is True
    assert _admin_session_token_is_valid(expired_tok) is False
    assert _admin_session_token_is_valid("tampered.token") is False


def test_zero_static_data_on_fresh_database(db_session):
    """P0-3: Taze veritabanında hiçbir statik/tohum (seed) veri bulunmamalı, tüm metrikler 0 dönmelidir."""
    from app.api.v1.endpoints.analytics import (
        _build_analytics_summary,
        OFFICIAL_STORE_BASELINE,
        _empty_store_state,
        _BASELINE_LOCK,
    )

    with _BASELINE_LOCK:
        OFFICIAL_STORE_BASELINE.clear()
        OFFICIAL_STORE_BASELINE.update(_empty_store_state())

    summary = _build_analytics_summary(db_session, period="all")
    kpis = summary["cumulative_kpis"]
    fl = summary["financial_ledger"]

    assert kpis["impressions_total"] == 0
    assert kpis["downloads_total"] == 0
    assert kpis["vip_activations"] == 0
    assert summary["total_raw"] == 0
    assert summary["total_all_spend_usd"] == 0.0
    assert summary["subscriber_ledger"] == []
    assert fl["realized_gross_try"] == 0.0
    assert fl["active_paid_mrr_net_try"] == 0.0
    assert fl["matured_trial_to_paid_cvr_str"] == "Veri Yok"


def test_mrr_separates_cumulative_ltv_from_recurring_and_period_filter_has_no_silent_fallback(db_session):
    """P1-1 & P1-2: Kümülatif LTV MRR'ı şişirmemeli ve boş 'today' filtresi tüm zamanlara sessizce dönmemelidir."""
    from datetime import timedelta
    from app.db.models import SubscriberLedger, BridgeClick
    from app.api.v1.endpoints.analytics import _build_analytics_summary

    SubscriberLedger.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    BridgeClick.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    # 3 kez yenilenmiş (toplam 449.97 TL ödenmiş) ancak aylık yinelenen fiyatı 149.99 TL olan abone
    sub = SubscriberLedger(
        subscriber_id="SUB_TEST_MRR_01",
        platform="ios",
        product_id="misil_monthly",
        plan_label="Aylık VIP",
        status="paid_active",
        offer_type="standard_paid",
        started_date="2026-08-01",
        converted_or_renewed_date="2026-10-01",
        maturity_or_renewal_date="2026-11-01",
        auto_renew_enabled=True,
        customer_price_try=449.97,
        developer_proceeds_try=249.36,
        expected_next_price_try=149.99,
        expected_next_proceeds_try=83.12,
        country="TR",
        device_type="iPhone",
    )
    db_session.add(sub)

    # 3 gün öncesine ait tekil köprü tıklaması (Bugün = 0 tıklama)
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    click = BridgeClick(
        route_path="/ios",
        channel="meta_ads_ios",
        os_family="ios",
        device_detail="iPhone",
        app_webview="Instagram App",
        target_store="app_store",
        is_bot=False,
        is_unique=True,
        ip_masked="10.0.0.xxx#a1b2",
        created_at=three_days_ago,
    )
    db_session.add(click)
    db_session.commit()

    sum_today = _build_analytics_summary(db_session, period="today")
    sum_all = _build_analytics_summary(db_session, period="all")

    assert sum_today["active_human_count"] == 0
    assert sum_all["active_human_count"] == 1

    fl = sum_all["financial_ledger"]
    assert fl["realized_gross_try"] == 449.97
    assert fl["realized_net_proceeds_try"] == 249.36
    assert fl["active_paid_mrr_gross_try"] == 149.99
    assert fl["active_paid_mrr_net_try"] == 83.12


def test_campaign_config_whitelist_and_csv_sanitization(client, db_session):
    """P1-3 & P2-2: Kampanya kanalı whitelist doğrulaması, URL'de PIN sızıntısı önleme ve CSV formül koruması."""
    from app.api.v1.endpoints.analytics import sanitize_csv_cell

    assert sanitize_csv_cell("  =cmd|' /C calc'!A0").startswith("'")
    assert sanitize_csv_cell("\n+SUM(1,2)").startswith("'")

    bad_res = client.post(
        "/api/v1/analytics/campaign-config",
        data={"pin": "MISIL-REV-9842", "channel_key": "arbitrary_injected_channel", "spend_usd": 10},
        follow_redirects=False,
    )
    assert bad_res.status_code == 400

    ok_res = client.post(
        "/api/v1/analytics/campaign-config",
        data={"pin": "MISIL-REV-9842", "channel_key": "apple_search_ads", "spend_usd": 42.5, "reported_installs": 12},
        follow_redirects=False,
    )
    assert ok_res.status_code == 303
    assert "pin=" not in ok_res.headers.get("location", "")


def test_store_daily_metric_aggregation_and_feedback_pin_isolation(client, db_session):
    """Claude CLI (task-202) & Codex CLI (task-203) bulguları: StoreDailyMetric kolon uyumu ve feedback.py PIN/XSS koruması."""
    from app.db.models import StoreDailyMetric, Feedback
    from app.api.v1.endpoints.analytics import _build_analytics_summary

    StoreDailyMetric.__table__.create(bind=db_session.connection(), checkfirst=True)
    Feedback.__table__.create(bind=db_session.connection(), checkfirst=True)
    dyn_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    db_session.add(
        StoreDailyMetric(
            metric_date=dyn_date,
            platform="ios",
            impressions=120,
            page_views=30,
            downloads_total=9,
            active_sessions=18,
        )
    )
    db_session.add(
        StoreDailyMetric(
            metric_date=dyn_date,
            platform="android",
            downloads_total=4,
        )
    )
    db_session.add(
        Feedback(
            message="<script>alert(1)</script>",
            sentiment="needs_improvement",
            contact_info="<img src=x onerror=alert(2)>",
            platform="ios",
        )
    )
    db_session.commit()

    summary = _build_analytics_summary(db_session, period="all")
    assert summary["cumulative_kpis"]["impressions_total"] == 120
    assert summary["cumulative_kpis"]["ios_downloads"] == 9
    assert summary["cumulative_kpis"]["android_downloads"] == 4
    assert summary["cumulative_kpis"]["downloads_total"] == 13
    assert summary["cumulative_kpis"]["active_sessions"] == 18

    # feedback.py: MISILREV2026 ve 984271 reddedilmeli (401)
    assert client.get("/api/v1/feedback/list", params={"pin": "MISILREV2026"}).status_code == 401
    assert client.get("/api/v1/feedback/list", params={"pin": "984271"}).status_code == 401
    assert client.get("/api/v1/feedback/export.csv", params={"pin": "MISILREV2026"}).status_code == 401

    # Geçerli PIN ile XSS payload'larının escape edildiği ve href içinde pin= sızmadığı doğrulanır
    fb_dash = client.get("/api/v1/feedback/dashboard", params={"pin": "MISIL-REV-9842"})
    assert fb_dash.status_code == 200
    assert "<script>alert(1)</script>" not in fb_dash.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in fb_dash.text
    assert "?pin=" not in fb_dash.text

    # Geçersiz period parametresi sessizce 'all' dönemine düşmemeli, 400 dönmeli
    bad_period = client.get("/api/v1/analytics/summary", params={"pin": "MISIL-REV-9842", "period": "invalid_period"})
    assert bad_period.status_code == 400

    # AuthKey dosya adı maskelemesi tüm alanlarda çalışmalı
    from app.api.v1.endpoints.analytics import _mask_sensitive_sync_value
    masked_payload = _mask_sensitive_sync_value({"status": "Loaded AuthKey_9X8Y7Z6W5V.p8 from disk"})
    assert "9X8Y7Z6W5V" not in masked_payload["status"]
    assert "AuthKey_[MASKED]" in masked_payload["status"]

    # Canlı HTML Kokpit (/admin/analytics -> /api/v1/analytics/dashboard) uçtan uca 200 OK dönmeli
    for p_val in ("all", "today", "yesterday", "7d"):
        dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842", "period": p_val})
        assert dash_res.status_code == 200
        assert "Kurumsal Büyüme" in dash_res.text

    # /api/v1/analytics/trigger-sync endpoint testi
    client.cookies.clear()
    unauth_trig = client.post("/api/v1/analytics/trigger-sync", params={"pin": "WRONG_PIN"})
    assert unauth_trig.status_code == 401

    from unittest.mock import patch
    with patch("app.api.v1.endpoints.analytics.sync_live_store_apis", return_value={"synced": True, "sources": ["Mock Store API"]}):
        auth_trig = client.post("/api/v1/analytics/trigger-sync", params={"pin": "MISIL-REV-9842", "days_back": 1})
        assert auth_trig.status_code == 200
        assert auth_trig.json()["status"] == "ok"


def test_obsidian_cockpit_v2_trial_mrr_healing_and_3row_grid(client, db_session):
    """v8.69.0: 0 TL kalan 7G denemelerin 149.99/83.12 TL'ye otomatik onarımı, 3 kademeli MRR şelalesi ve sıfır kaymalı 3-row CSS Grid doğrulaması."""
    from datetime import timedelta
    from app.db.models import SubscriberLedger, StoreDailyMetric
    from app.api.v1.endpoints.analytics import _build_analytics_summary

    SubscriberLedger.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    StoreDailyMetric.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    tz_tr = timezone(timedelta(hours=3))
    today_tr = datetime.now(tz_tr).date()
    d_matured_start = (today_tr - timedelta(days=9)).strftime("%Y-%m-%d")
    d_matured_end = (today_tr - timedelta(days=2)).strftime("%Y-%m-%d")
    d_upcoming_start = (today_tr - timedelta(days=2)).strftime("%Y-%m-%d")
    d_upcoming_end = (today_tr + timedelta(days=5)).strftime("%Y-%m-%d")

    # 1) Vadesi dolmuş ancak Apple mutabakatında olan 7G deneme (expected_next_price_try=0.0 -> 149.99/83.12 onarılmalı)
    db_session.add(
        SubscriberLedger(
            subscriber_id="SUB_RECONCILING_01",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date=d_matured_start,
            converted_or_renewed_date=d_matured_start,
            maturity_or_renewal_date=d_matured_end,
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=0.0,
            expected_next_proceeds_try=0.0,
            country="TR",
            device_type="iPhone",
        )
    )
    # 2) Vadesi gelecek 7G deneme (expected_next_price_try=0.0 -> 149.99/83.12 onarılmalı)
    db_session.add(
        SubscriberLedger(
            subscriber_id="SUB_UPCOMING_02",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date=d_upcoming_start,
            converted_or_renewed_date=d_upcoming_start,
            maturity_or_renewal_date=d_upcoming_end,
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=0.0,
            expected_next_proceeds_try=0.0,
            country="TR",
            device_type="iPhone",
        )
    )
    db_session.commit()

    summary = _build_analytics_summary(db_session, period="all")
    fl = summary["financial_ledger"]

    assert fl["pipeline_7d_trials_count"] == 2
    assert fl["reconciling_7d_trials_count"] == 1
    assert fl["upcoming_7d_trials_count"] == 1
    assert fl["reconciling_7d_mrr_net_try"] == 83.12
    assert fl["upcoming_7d_mrr_net_try"] == 83.12
    assert fl["pipeline_7d_mrr_net_try"] == 166.24
    assert fl["projected_total_mrr_net_try"] == 166.24

    ps = summary["platform_split"]
    assert "all" in ps and "ios" in ps and "android" in ps
    gp_cat = summary["google_play_subscriptions_catalog"]
    assert len(gp_cat) >= 2
    assert any(p["product_id"] == "misil" for p in gp_cat)
    assert any(p["product_id"] == "misilaylik" for p in gp_cat)

    dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
    assert dash_res.status_code == 200
    assert "grid-template-rows: 22px 1fr 22px" in dash_res.text
    assert "pollLiveTelemetry" in dash_res.text
    assert "window.location.reload()" not in dash_res.text
    assert "platBtn_all" in dash_res.text
    assert "platBtn_ios" in dash_res.text
    assert "platBtn_android" in dash_res.text
    assert "googlePlayLedgerCard" in dash_res.text
    assert "misilaylik" in dash_res.text
    assert "switchPlatform" in dash_res.text


def test_apple_connect_12_active_16_records_reconciliation_and_google_play_bridge(client, db_session):
    """Apple Connect (12 Aktif VIP = 1 Ücretli + 6 Deneme + 5 DamlaEge2026 Kodlu, 4 İptal, Toplam 16 Kayıt) ve Google Play köprüsü doğrulaması."""
    from app.db.models import SubscriberLedger, SubscriptionLifecycleEvent
    from app.api.v1.endpoints.analytics import _build_analytics_summary
    from app.services.subscription import SubscriptionService

    SubscriberLedger.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    SubscriptionLifecycleEvent.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    # 1) 1 Ücretli Aktif (#813562)
    db_session.add(
        SubscriberLedger(
            subscriber_id="520002815813562",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek",
            status="paid_active",
            offer_type="standard_paid",
            started_date="2026-10-20",
            converted_or_renewed_date="2026-10-27",
            maturity_or_renewal_date="2026-11-27",
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
            auto_renew_enabled=True,
        )
    )

    # 2) 5 DamlaEge2026 Kampanya Kodu (1 Yıl)
    for idx in range(1, 6):
        db_session.add(
            SubscriberLedger(
                subscriber_id=f"52000999000000{idx}",
                platform="ios",
                product_id="misil_annual",
                plan_label="Mışıl Yıllık VIP",
                status="offer_code_trial",
                offer_type="offer_code",
                offer_code_name="DamlaEge2026",
                started_date="2026-10-20",
                converted_or_renewed_date="2026-10-20",
                maturity_or_renewal_date="2027-10-20",
                customer_price_try=0.0,
                developer_proceeds_try=0.0,
                expected_next_price_try=599.99,
                expected_next_proceeds_try=332.50,
                country="TR",
                device_type="iPhone",
                auto_renew_enabled=True,
            )
        )

    # 3) 4 İptal Edilen Aylık Deneme (22-23 Ekim kohortu: 1 FR + 2 TR 10-22, 1 TR 10-23)
    cancelled_seeds = [
        ("520002749476306", "2026-10-22", "2026-10-29", "FR"),
        ("540001269107716", "2026-10-22", "2026-10-29", "TR"),
        ("560002227449600", "2026-10-22", "2026-10-29", "TR"),
        ("570001850954257", "2026-10-23", "2026-10-30", "TR"),
    ]
    for sub_id, st_d, mat_d, ctry in cancelled_seeds:
        db_session.add(
            SubscriberLedger(
                subscriber_id=sub_id,
                platform="ios",
                product_id="misil_monthly",
                plan_label="Aylık Esnek",
                status="intro_free_trial",
                offer_type="intro_7d_trial",
                started_date=st_d,
                converted_or_renewed_date=st_d,
                maturity_or_renewal_date=mat_d,
                customer_price_try=0.0,
                developer_proceeds_try=0.0,
                expected_next_price_try=149.99,
                expected_next_proceeds_try=83.12,
                country=ctry,
                device_type="iPhone",
                auto_renew_enabled=True,
            )
        )

    # 4) 3 Aktif Aylık 7G Deneme (28-30 Ekim)
    for idx, st_d, mat_d in [
        ("500001925784599", "2026-10-28", "2026-11-04"),
        ("530002725216337", "2026-10-30", "2026-11-06"),
        ("540001265067047", "2026-10-30", "2026-11-06"),
    ]:
        db_session.add(
            SubscriberLedger(
                subscriber_id=idx,
                platform="ios",
                product_id="misil_monthly",
                plan_label="Aylık Esnek",
                status="intro_free_trial",
                offer_type="intro_7d_trial",
                started_date=st_d,
                converted_or_renewed_date=st_d,
                maturity_or_renewal_date=mat_d,
                customer_price_try=0.0,
                developer_proceeds_try=0.0,
                expected_next_price_try=149.99,
                expected_next_proceeds_try=83.12,
                country="TR",
                device_type="iPhone",
                auto_renew_enabled=True,
            )
        )

    # 5) 3 Yıllık Default_Intro 7G Deneme (eski hatalı offer_code_trial ve 799.99 TL kaydıyla -> otomatik onarılmalı)
    for idx, st_d in [
        ("500001920786416", "2026-10-28"),
        ("500001917243135", "2026-10-30"),
        ("540001283217720", "2026-10-30"),
    ]:
        db_session.add(
            SubscriberLedger(
                subscriber_id=idx,
                platform="ios",
                product_id="misil_annual",
                plan_label="Mışıl Yıllık VIP",
                status="offer_code_trial",
                offer_type="offer_code",
                offer_code_name="7 Günlük Deneme",
                started_date=st_d,
                converted_or_renewed_date=st_d,
                maturity_or_renewal_date="2027-10-30",
                customer_price_try=0.0,
                developer_proceeds_try=0.0,
                expected_next_price_try=799.99,
                expected_next_proceeds_try=443.33,
                country="TR",
                device_type="iPhone",
                auto_renew_enabled=True,
            )
        )

    # 6) Apple SUBSCRIPTION_EVENT Cancel kayıtları (4 iptal)
    cancel_evts = [
        ("2026-10-28", "FR", "6"),
        ("2026-10-28", "TR", "6"),
        ("2026-10-29", "TR", "7"),
        ("2026-10-30", "TR", "7"),
    ]
    for e_date, ctry, dbc in cancel_evts:
        db_session.add(
            SubscriptionLifecycleEvent(
                event_date=e_date,
                event_type="Cancel",
                product_id="misil_monthly",
                plan_label="Aylık Esnek",
                quantity=1,
                country=ctry,
                days_before_canceling=dbc,
                platform="ios",
            )
        )
    db_session.commit()

    summary = _build_analytics_summary(db_session, period="all")
    fl = summary["financial_ledger"]

    # 16 toplam kayıt -> 12 Aktif VIP (1 Ücretli + 5 Kodlu + 6 Deneme) ve 4 İptal
    assert summary["product_funnel"]["subscriptions_count"] == 12
    assert fl["active_vip_subs_count"] == 12
    assert fl["total_vip_records_count"] == 16
    assert fl["cancelled_subs_count"] == 4
    assert fl["paid_subs_count"] == 1
    assert fl["offer_code_subs_count"] == 5
    assert fl["pipeline_7d_trials_count"] == 6
    # 3 × 149.99 + 3 × 599.99 = 2249.94 Brüt / 3 × 83.12 + 3 × 332.50 = 1246.86 Net
    assert fl["pipeline_7d_mrr_gross_try"] == 2249.94
    assert fl["pipeline_7d_mrr_net_try"] == 1246.86

    # Google Play /api/v1/analytics/subscriber-sync ve RevenueCat webhook testi
    sync_res = client.post(
        "/api/v1/analytics/subscriber-sync",
        json={
            "subscriber_id": "GPA.3381-9911-2233-44556",
            "device_uid": "msl_android_test01",
            "platform": "android",
            "product_id": "misilaylik",
            "plan": "monthly",
            "status": "intro_free_trial",
            "started_date": "2026-10-31",
            "maturity_or_renewal_date": "2026-11-07",
            "country": "TR",
            "device_type": "Android",
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["ok"] is True

    # RevenueCat PLAY_STORE anonim kullanıcı webhook testi (user DB'de olmasa bile SubscriberLedger'a yazmalı)
    from app.core.config import settings
    rc_res = SubscriptionService.process_revenuecat_webhook(
        db_session,
        payload={
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "$RCAnonymousID:8899aabbccdd",
                "original_transaction_id": "GPA.3399-8877-6655-00112",
                "product_id": "misil",
                "store": "PLAY_STORE",
                "period_type": "NORMAL",
                "price_in_purchased_currency": 599.99,
                "takehome_percentage": 0.727,
                "country_code": "TR",
                "currency": "TRY",
            }
        },
        auth_header=settings.REVENUECAT_WEBHOOK_SECRET,
    )
    assert rc_res["ledger_synced"] is True

    summary_after_and = _build_analytics_summary(db_session, period="all")
    ps_and = summary_after_and["platform_split"]["android"]
    ps_all = summary_after_and["platform_split"]["all"]
    assert ps_and["vip_count"] == 2
    assert ps_and["mrr_net_try"] > 0
    assert "vis_of_imp_pct" in ps_all
    assert "dl_of_imp_pct" in ps_all
    assert "vip_of_dl_pct" in ps_all
    assert "vip_of_vis_pct" in ps_all
    assert "vip_of_imp_pct" in ps_all

    dash_html = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"}).text
    assert "Gösterim ➔ VIP" in dash_html
    assert "İndirme ➔ VIP" in dash_html
    assert "conversionBridgeCard" in dash_html
    assert "convBridge1" in dash_html
    assert "convBridge2" in dash_html
    assert "convBridge2Sub" in dash_html
    assert "convStoreCvrPill" in dash_html
    assert "convBridge3" in dash_html
    assert "hero-stage-card" in dash_html
    assert "conv-bridge-grid" in dash_html
    assert "togglePresentationMode" in dash_html
    assert "toggleCompareDrawer" in dash_html
    assert "funStep1Val" not in dash_html
    assert "<strong>🌐 Kümülatif (Toplam — Apple + Google Play):</strong>" not in dash_html


def test_priority1_android_intent_bridge_and_separated_cvr_metrics(client, db_session):
    """
    Öncelik 1 Doğrulaması:
    1) Android IAB (Facebook / Instagram WebView) ve /ios köprüsü için native Google Play intent://
       (com.android.vending) + App Links meta etiketleri + store_button_click sinyali.
    2) Simpson Paradoksu çözümü: Mağaza Sayfası CVR (store_cvr_pct) vs Sosyal Köprü CVR (bridge_cvr_pct)
       vs Kesinleşen Günler CVR (settled_cvr_pct) ve Masaüstü (desktop_bridge_clicks) mutabakatı.
    """
    from app.main import generate_interstitial_html, GOOGLE_PLAY_INTENT_URL
    from app.api.v1.endpoints.analytics import (
        _build_analytics_summary,
        OFFICIAL_STORE_BASELINE,
        _empty_store_state,
        _BASELINE_LOCK,
    )
    from app.db.models import StoreDailyMetric

    StoreDailyMetric.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    db_session.add(
        StoreDailyMetric(
            metric_date="2026-10-30",
            platform="ios",
            impressions=1000,
            page_views=200,
            downloads_total=40,
            downloads_search=30,
            downloads_referrer=8,
            downloads_browse=2,
            active_sessions=120,
        )
    )
    db_session.commit()

    and_html = generate_interstitial_html(is_android=True)
    assert GOOGLE_PLAY_INTENT_URL in and_html
    assert "package=com.android.vending" in and_html
    assert 'property="al:android:package" content="com.levitas.misilbaby"' in and_html
    assert 'property="al:ios:app_store_id" content="6809223195"' in and_html
    assert 'id="storeOpenBtn"' in and_html
    assert 'id="storeWebFallbackBtn"' in and_html
    assert "store_button_click" in and_html

    ios_html = generate_interstitial_html(is_android=False)
    assert "id6809223195" in ios_html
    assert 'id="storeWebFallbackBtn"' not in ios_html

    # Meta Reklam (/ios) üzerinden gelen Android Facebook In-App Browser (FBAN) isteği
    from unittest.mock import patch
    with patch("app.main.record_bridge_click"):
        bridge_res = client.get(
            "/ios",
            headers={
                "user-agent": (
                    "Mozilla/5.0 (Linux; Android 14; SM-S918B Build/UP1A.231005.007; wv) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.6099.144 "
                    "Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/445.0.0.34.118;]"
                )
            },
        )
    assert bridge_res.status_code == 200
    assert "intent://details?id=com.levitas.misilbaby" in bridge_res.text

    # Manuel buton tıklama sinyali (store_button_click) kaydı
    btn_sig_res = client.post(
        "/api/v1/analytics/app-open-signal",
        json={
            "device_uid": "jump_testbtn01",
            "event_type": "store_button_click",
            "os_family": "android",
            "platform": "primary_cta",
            "app_version": "4.46.0",
        },
    )
    assert btn_sig_res.status_code == 200
    assert btn_sig_res.json()["status"] == "ok"

    with _BASELINE_LOCK:
        OFFICIAL_STORE_BASELINE.clear()
        OFFICIAL_STORE_BASELINE.update(_empty_store_state())

    summary = _build_analytics_summary(db_session, period="all")
    kpis = summary["cumulative_kpis"]
    ps_all = summary["platform_split"]["all"]
    ps_ios = summary["platform_split"]["ios"]
    ps_and = summary["platform_split"]["android"]

    assert summary["product_funnel"]["store_button_clicks_tracked"] >= 1
    assert "store_page_cvr_pct" in kpis
    assert "store_unique_cvr_pct" in kpis
    assert "bridge_cvr_pct" in kpis
    assert "settled_cvr_pct" in kpis
    assert "desktop_bridge_clicks" in kpis

    assert ps_all["store_cvr_pct"] == 20.0
    assert 0.0 <= ps_all["bridge_cvr_pct"] <= 100.0
    assert "Mağaza:" in ps_all["cvr_breakdown_label"]
    assert "Köprü:" in ps_all["cvr_breakdown_label"]
    assert "Mağaza:" in ps_ios["cvr_breakdown_label"]
    assert "Native Intent Aktif" in ps_and["cvr_breakdown_label"]


def test_paywall_funnel_telemetry_and_usage_signal_endpoint(client, db_session):
    from app.api.v1.endpoints.analytics import _build_analytics_summary

    events = [
        ("paywall_viewed", "ios"),
        ("paywall_cta_clicked", "ios"),
        ("purchase_cancelled", "ios"),
        ("paywall_viewed", "android"),
        ("paywall_skipped", "android"),
        ("purchase_error", "android"),
    ]
    for idx, (evt, os_fam) in enumerate(events):
        endpoint = "/api/v1/analytics/usage-signal" if idx % 2 == 0 else "/api/v1/analytics/app-open-signal"
        res = client.post(
            endpoint,
            json={
                "device_uid": f"msl_cro_test_{idx}",
                "event_type": evt,
                "os_family": os_fam,
                "platform": f"{os_fam}_native",
                "app_version": "4.46.22",
            },
        )
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    summary = _build_analytics_summary(db_session, period="all")
    pf = summary["product_funnel"]["paywall_funnel"]
    assert pf["paywall_viewed"] >= 2
    assert pf["paywall_cta_clicked"] >= 1
    assert pf["paywall_skipped"] >= 1
    assert pf["purchase_cancelled"] >= 1
    assert pf["purchase_error"] >= 1
    assert pf["ios"]["paywall_viewed"] >= 1
    assert pf["ios"]["paywall_cta_clicked"] >= 1
    assert pf["ios"]["purchase_cancelled"] >= 1
    assert pf["android"]["paywall_viewed"] >= 1
    assert pf["android"]["paywall_skipped"] >= 1
    assert pf["android"]["purchase_error"] >= 1

    dash_res = client.get("/api/v1/analytics/dashboard")
    assert dash_res.status_code == 200
    assert "Mışıl" in dash_res.text


def test_family_create_and_join_vip_inheritance_protection(client):
    """Ücretsiz aile kodunun bedelsiz VIP sızdırmadığını ve VIP aile kodunun eş/bakıcıya VIP aktardığını doğrular."""
    # 1. Ücretsiz aile oluşturma
    r_free = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "Defne",
            "birth_date": "2026-06-01",
            "creator_role": "mother",
            "creator_name": "Ayşe",
            "subscription_active": False,
            "subscription_plan": "free",
        },
    )
    assert r_free.status_code == 200
    free_code = r_free.json()["invite_code"]
    assert r_free.json()["family"]["subscription_active"] is False
    assert r_free.json()["family"]["subscription_plan"] == "free"

    # Ücretsiz aileye baba katıldığında subscription_active False kalmalı
    r_join_free = client.post(
        "/api/v1/family/join",
        json={"invite_code": free_code, "role": "father", "name": "Mehmet"},
    )
    assert r_join_free.status_code == 200
    assert r_join_free.json()["family"]["subscription_active"] is False
    assert r_join_free.json()["family"]["subscription_plan"] == "free"

    # 2. Anne VIP/Deneme başlattığında mevcut aile kodunu bulutta VIP'ye yükseltir
    r_upgrade = client.post(
        "/api/v1/family/create",
        json={
            "invite_code": free_code,
            "baby_name": "Defne",
            "birth_date": "2026-06-01",
            "creator_role": "mother",
            "creator_name": "Ayşe",
            "subscription_active": True,
            "subscription_plan": "yearly",
        },
    )
    assert r_upgrade.status_code == 200
    assert r_upgrade.json()["invite_code"] == free_code
    assert r_upgrade.json()["family"]["subscription_active"] is True
    assert r_upgrade.json()["family"]["subscription_plan"] == "yearly"

    # 3. Şimdi dadı katıldığında aktif VIP bilgisini alır
    r_join_vip = client.post(
        "/api/v1/family/join",
        json={"invite_code": free_code, "role": "nanny", "name": "Fatma"},
    )
    assert r_join_vip.status_code == 200
    assert r_join_vip.json()["family"]["subscription_active"] is True
    assert r_join_vip.json()["family"]["subscription_plan"] == "yearly"









