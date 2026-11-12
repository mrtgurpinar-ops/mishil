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


def test_dashboard_audit_remediation_dev_purge_mrr_and_aso_ios_isolation(client, db_session):
    """
    Dashboard Mutabakat Denetimi (5 Kritik Düzeltme Doğrulaması):
    1) DEV_IOS_* ve DEV_ANDROID_* hayalet/mükerrer istemci kayıtlarının temizlenmesi ve engellenmesi,
    2) Yanlışlıkla iptal edilen gerçek Apple denemesinin (#184012) active_trials_target ile geri yüklenmesi,
    3) Yıllık ücretli abonenin (#996540) auto_renew_enabled=True onarımı ve MRR/kohorta dahil edilmesi,
    4) ASO Attribution tablosunda matched_meta_installs için yalnızca iOS sinyallerinin sayılması.
    """
    from app.db.models import SubscriberLedger, SubscriptionLifecycleEvent, AppInstallSignal, StoreDailyMetric
    from app.api.v1.endpoints.analytics import (
        _build_analytics_summary,
        OFFICIAL_STORE_BASELINE,
        _empty_store_state,
        _BASELINE_LOCK,
    )

    SubscriberLedger.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    SubscriptionLifecycleEvent.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    AppInstallSignal.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    StoreDailyMetric.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    with _BASELINE_LOCK:
        OFFICIAL_STORE_BASELINE.clear()
        OFFICIAL_STORE_BASELINE.update(_empty_store_state())
        OFFICIAL_STORE_BASELINE["apple_vip_active_trials"] = 3
        OFFICIAL_STORE_BASELINE["apple_downloads_total"] = 136
        OFFICIAL_STORE_BASELINE["apple_downloads_search"] = 70
        OFFICIAL_STORE_BASELINE["apple_downloads_referrer"] = 50
        OFFICIAL_STORE_BASELINE["apple_downloads_browse"] = 11

    # 1) Aylık ücretli aktif (#813562) + Yıllık ücretli aktif (#996540 - auto_renew_enabled=False kalmış)
    db_session.add_all([
        SubscriberLedger(
            subscriber_id="602650322813562",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="paid_active",
            offer_type="standard_paid",
            started_date="2026-10-20",
            converted_or_renewed_date="2026-10-27",
            maturity_or_renewal_date="2026-11-26",
            auto_renew_enabled=True,
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="791488183996540",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="paid_active",
            offer_type="standard_paid",
            started_date="2026-10-28",
            converted_or_renewed_date="2026-11-04",
            maturity_or_renewal_date="2027-11-04",
            auto_renew_enabled=False,  # Hatalı False kalmış -> True'ya onarılmalı
            customer_price_try=599.99,
            developer_proceeds_try=332.49,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.49,
            country="TR",
            device_type="iPhone",
        ),
        # 2) Yanlışlıkla iptal edilmiş gerçek Apple denemesi (#184012 - Cancel olayı yok)
        SubscriberLedger(
            subscriber_id="441709785184012",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="cancelled",
            offer_type="intro_7d_trial",
            started_date="2026-10-29",
            maturity_or_renewal_date="2026-11-05",
            auto_renew_enabled=False,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=0.0,
            expected_next_proceeds_try=0.0,
            country="TR",
            device_type="iPhone",
        ),
        # 3) 2 aktif yıllık deneme (#786416 & #243135)
        SubscriberLedger(
            subscriber_id="259753775786416",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-10-30",
            maturity_or_renewal_date="2026-11-06",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.50,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="238741809243135",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-10-30",
            maturity_or_renewal_date="2026-11-06",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.50,
            country="TR",
            device_type="iPhone",
        ),
        # 4) Gerçek iptal edilmiş deneme (2026-10-22 FR)
        SubscriberLedger(
            subscriber_id="307840202476306",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            status="cancelled",
            offer_type="intro_7d_trial",
            started_date="2026-10-22",
            maturity_or_renewal_date="2026-10-29",
            auto_renew_enabled=False,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=0.0,
            expected_next_proceeds_try=0.0,
            country="FR",
            device_type="iPhone",
        ),
        # 5) Temizlenmesi gereken hayalet DEV_IOS_* ve DEV_ANDROID_* kayıtları
        SubscriberLedger(
            subscriber_id="DEV_IOS_msl_anon",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-10-31",
            maturity_or_renewal_date="2026-11-07",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.50,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="DEV_ANDROID_msl_ghost01",
            platform="android",
            product_id="misil",
            plan_label="Mışıl Baby Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-10-31",
            maturity_or_renewal_date="2026-11-07",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=436.20,
            country="TR",
            device_type="Android",
        ),
    ])
    db_session.add(
        SubscriptionLifecycleEvent(
            event_date="2026-10-28",
            event_type="EVENT:Cancel:2026-10-22:FR",
            product_id="misil_monthly",
            plan_label="Aylık Esnek VIP",
            quantity=1,
            country="FR",
            days_before_canceling="6",
            platform="ios",
        )
    )
    # 40 adet Android first_open (matched_channel='meta_ads') r3_ref'i 50'nin üzerine şişirmemeli
    for idx in range(40):
        db_session.add(
            AppInstallSignal(
                device_uid=f"and_meta_dev_{idx}",
                event_type="first_open",
                os_family="android",
                platform="android_native",
                matched_channel="meta_ads",
                match_confidence="high",
            )
        )
    db_session.commit()

    # Kimliksiz DEV_IOS_* senkron çağrısı reddedilmeli/yoksayılmalı
    unv_res = client.post(
        "/api/v1/analytics/subscriber-sync",
        json={
            "subscriber_id": "DEV_IOS_msl_newghost",
            "device_uid": "msl_newghost",
            "platform": "ios",
            "product_id": "misil_annual",
            "status": "intro_free_trial",
        },
    )
    assert unv_res.status_code == 200
    assert unv_res.json()["status"] == "ignored_unverified_dev_id"

    summary = _build_analytics_summary(db_session, period="all")
    fl = summary["financial_ledger"]

    # DEV_* kayıtları silinmiş olmalı; 2 paid + 3 trial = 5 aktif VIP, 1 iptal = 6 toplam kayıt
    assert fl["paid_subs_count"] == 2
    assert fl["pipeline_7d_trials_count"] == 3
    assert fl["active_vip_subs_count"] == 5
    assert fl["cancelled_subs_count"] == 1
    assert fl["total_vip_records_count"] == 6

    # MRR: 149.99 + (599.99 / 12) = 199.99 Brüt, 83.12 + (332.49 / 12) = 110.83 Net
    assert fl["active_paid_mrr_gross_try"] == 199.99
    assert fl["active_paid_mrr_net_try"] == 110.83

    # 7G Pipeline: 149.99 + 599.99 + 599.99 = 1349.97 Brüt, 83.12 + 332.50 + 332.50 = 748.12 Net
    assert fl["pipeline_7d_mrr_gross_try"] == 1349.97
    assert fl["pipeline_7d_mrr_net_try"] == 748.12

    # ASO Sosyal Yönlendirme (r3_ref) Android sinyallerinden etkilenmeyip 50 kalmalı
    social_row = next(r for r in summary["aso_attribution_matrix"] if "Sosyal Yönlendirme" in r["channel"])
    assert social_row["downloads"] == 50


def test_v4_48_0_returning_users_and_paywall_cancellation_cro(client, db_session):
    """v4.48.0: Apple r8 Tekrar Giren (Returning) Cihaz Kohortu, Paywall İptal Kurtarma ve Aylık Esnek VIP Varsayılanı."""
    import os
    from app.db.models import AppInstallSignal, StoreSyncState
    from app.api.v1.endpoints.analytics import (
        _aggregate_apple_r8_cohorts,
        _build_analytics_summary,
        _empty_store_state,
        OFFICIAL_STORE_BASELINE,
    )

    # 1. _empty_store_state() sıfır statik veri ilkesi gereği 0 dönmeli
    empty_st = _empty_store_state()
    assert empty_st["apple_sessions_optin_devices"] == 0
    assert empty_st["apple_returning_optin_devices"] == 0

    # 2. _aggregate_apple_r8_cohorts() birim testi (boş küme, page_type örtüşmesi ve udev > 1 güvercin yuvası ilkesi)
    assert _aggregate_apple_r8_cohorts({})["apple_sessions_optin_devices"] == 0
    sample_r8 = {
        # Kohort A: Aynı gün 2 farklı page_type dilimi (maksimumu alınmalı, çift toplanmamalı) + ertesi gün 2. oturum -> returning & loyal (toplam 3 oturum)
        ("2026-11-01", "2026-10-30", "iPhone", "iOS 18.1", "App Store Search", "TR", "Product Page"): (2, 120, 1),
        ("2026-11-01", "2026-10-30", "iPhone", "iOS 18.1", "App Store Search", "TR", "No Page"): (1, 60, 1),
        ("2026-11-02", "2026-10-30", "iPhone", "iOS 18.1", "App Store Search", "TR", "Product Page"): (1, 90, 1),
        # Kohort B: Unique Devices = 2 ve toplam Sessions = 2 (aynı gün) -> 2 farklı cihaz 1'er kez girmiş olabileceği için returning SAYILMAMALI (0)
        ("2026-11-02", "2026-11-02", "iPhone", "iOS 18.0", "Web Referrer", "TR", "Product Page"): (2, 45, 2),
        # Kohort C: Aynı gün 2 oturum açmış 1 cihaz -> returning (2+ oturum), fakat loyal (3+) değil
        ("2026-11-03", "2026-11-03", "iPhone", "iOS 17.6", "App Store Browse", "TR", "Product Page"): (2, 80, 1),
    }
    agg = _aggregate_apple_r8_cohorts(sample_r8)
    assert agg["apple_sessions_optin_devices"] == 4  # 1 (A) + 2 (B) + 1 (C)
    assert agg["apple_returning_optin_devices"] == 2  # 1 (A) + 0 (B: 2 sess / 2 udev aynı gün) + 1 (C)
    assert agg["apple_loyal_optin_devices"] == 1  # Sadece Kohort A (3 oturum >= 3)
    assert agg["apple_returning_sessions_total"] == 5  # 3 (A) + 2 (C)
    assert agg["apple_max_sessions_per_device"] == 3
    assert agg["apple_sessions_duration_sec"] == 335

    StoreSyncState.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    OFFICIAL_STORE_BASELINE.update(agg)

    AppInstallSignal.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    for ev_type, os_fam in [
        ("daily_active", "ios"),
        ("daily_active", "android"),
        ("paywall_cta_clicked", "ios"),
        ("paywall_cta_clicked", "android"),
        ("purchase_cancelled", "android"),
        ("sound_preview_60s_ended", "ios"),
        ("cry_limit_reached", "ios"),
        ("dadi_limit_reached", "android"),
        ("routine_limit_reached", "ios"),
        ("paywall_cancel_recovery_shown", "android"),
    ]:
        db_session.add(
            AppInstallSignal(
                device_uid=f"v448_{ev_type}_{os_fam}",
                event_type=ev_type,
                os_family=os_fam,
                platform=f"{os_fam}_native",
            )
        )
    db_session.commit()

    summary = _build_analytics_summary(db_session, period="all")
    pr = summary["product_retention"]
    pf = summary["product_funnel"]["paywall_funnel"]

    assert pr["optin_ios_total_devices"] == 4
    assert pr["returning_optin_ios_devices"] == 2
    assert pr["loyal_optin_ios_devices"] == 1
    assert pr["optin_ios_return_rate_pct"] == 50.0
    assert pr["returning_sessions_total"] == 5
    assert pr["max_sessions_single_device"] == 3
    assert pr["verified_returning_devices_floor"] == 2

    assert pf["sound_preview_60s_ended"] >= 1
    assert pf["cry_limit_reached"] >= 1
    assert pf["dadi_limit_reached"] >= 1
    assert pf["routine_limit_reached"] >= 1
    assert pf["paywall_cancel_recovery_shown"] >= 1
    assert pf["cancel_rate_pct"] == 50.0

    app_html_path = os.path.join(os.path.dirname(__file__), "..", "public", "app.html")
    with open(app_html_path, "r", encoding="utf-8") as fh:
        app_html = fh.read()

    assert "applyQuickBabyAgeMonths(" in app_html
    assert "applyQuickLastWakeMinsAgo(" in app_html
    assert "vipRenewalSelectedPlan = 'monthly';" in app_html
    assert "paywall_cancel_recovery_shown" in app_html
    assert "sound_preview_60s_ended" in app_html
    assert "getDynamicPricingState" in app_html
    assert "report-next-sweetspot-time" in app_html
    assert "onboarding-trial-end-text" in app_html
    assert "vip-calibration-progress-box" in app_html
    assert "mishil_family_vip_verified" in app_html
    assert "mishil_soft_vip_24h_granted" in app_html
    assert "mishil_soft_vip_cry_count" in app_html
    assert "version: '4.50.2'" in app_html


def test_s8_ios_rc_anonymous_id_ghost_purge_and_unverified_sync_ignore(client, db_session):
    """S8: Doğrulanmamış sıfır tutarlı iOS RCAnonymousID hayalet satırlarının temizlendiğini ve istemci sync'te reddedildiğini doğrular."""
    from app.db.models import SubscriberLedger
    from app.api.v1.endpoints.analytics import _build_analytics_summary

    ghost_sid = "$RCAnonymousID:03541926461e499fb7b22b285ec26174"
    db_session.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == ghost_sid).delete()
    db_session.add(
        SubscriberLedger(
            subscriber_id=ghost_sid,
            platform="ios",
            product_id="misil_annual",
            plan_label="Mışıl Baby Yıllık VIP",
            status="cancelled",
            offer_type="intro_free_trial",
            started_date="2026-09-16",
            maturity_or_renewal_date="2026-09-23",
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            auto_renew_enabled=False,
        )
    )
    db_session.commit()

    # Mutabakat çalıştığında 0 TL'lik iOS RCAnonymousID hayalet kaydı silinmeli
    _ = _build_analytics_summary(db_session, period="all")
    remaining = db_session.query(SubscriberLedger).filter(SubscriberLedger.subscriber_id == ghost_sid).first()
    assert remaining is None

    # Doğrulanmamış istemci /subscriber-sync çağrısı RCAnonymousID gönderdiğinde yoksayılmalı
    res = client.post(
        "/api/v1/analytics/subscriber-sync",
        json={
            "subscriber_id": "$RCAnonymousID:ghost_test_999",
            "platform": "ios",
            "product_id": "misil_annual",
            "status": "intro_free_trial",
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ignored_unverified_dev_id"


def test_dashboard_6_anomalies_remediation_and_live_polling(client, db_session):
    """
    Kurucu Kokpiti 6 Anomali Onarımı Doğrulaması:
    1) Redundant '🔄 Senkronize Et' butonunun kaldırılması ve 15sn canlı telemetrinin (pollLiveTelemetry)
       livePeriodSub / convCum4 / liveClicksTbody alanlarını bozmadan güncellemesi,
    2) Apple Sales TSV (indirme > 0) gelmiş ancak Apple r14 Analytics (impressions = 0) 24s gecikmeli
       günde is_r14_pending=True işaretlenerek Gösterim sparkline'ının 0'a çakılmasının önlenmesi,
    3) Sosyal köprü tıklamalarının (9.487 tık) Mağaza Gösterimi (5.782) paydasına bölünerek %177.6
       üretmesinin engellenmesi (vis_of_imp_pct <= 100.0 ve imp_breakdown_label ayrımı),
    4) Sekme 3 Keşfet (Browse) satırında '0 Cihaz' hatasının giderilmesi,
    5) Sekme 4 içinde sabit '213 kurulumda opt-in düzeltmeli ~64–100 kullanıcı' metninin dinamikleştirilmesi.
    """
    from app.db.models import StoreDailyMetric, BridgeClick
    from app.api.v1.endpoints.analytics import (
        _build_analytics_summary,
        OFFICIAL_STORE_BASELINE,
        _empty_store_state,
        _BASELINE_LOCK,
    )

    StoreDailyMetric.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    BridgeClick.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    db_session.query(StoreDailyMetric).delete()
    db_session.add_all([
        StoreDailyMetric(
            metric_date="2026-11-05",
            platform="ios",
            impressions=600,
            page_views=90,
            downloads_total=12,
            downloads_search=8,
            downloads_referrer=3,
            downloads_browse=1,
            active_sessions=40,
        ),
        StoreDailyMetric(
            metric_date="2026-11-06",
            platform="ios",
            impressions=680,
            page_views=110,
            downloads_total=10,
            downloads_search=7,
            downloads_referrer=2,
            downloads_browse=1,
            active_sessions=45,
        ),
        # 2026-11-07: Apple Sales TSV indirmesi (8) gelmiş fakat r14 impressions (0) henüz gelmemiş
        StoreDailyMetric(
            metric_date="2026-11-07",
            platform="ios",
            impressions=0,
            page_views=0,
            downloads_total=8,
            downloads_search=5,
            downloads_referrer=3,
            downloads_browse=0,
            active_sessions=0,
        ),
    ])
    # Çok sayıda sosyal köprü tıklaması eklendiğinde bile vis_of_imp_pct %100'ü aşmamalı
    for idx in range(25):
        db_session.add(
            BridgeClick(
                route_path="/ios",
                channel="meta_ads_ios",
                os_family="ios" if idx % 2 == 0 else "android",
                device_detail="iPhone",
                app_webview="Instagram",
                target_store="app_store" if idx % 2 == 0 else "google_play",
                is_bot=False,
                is_unique=True,
                ip_masked=f"192.0.2.{idx}#u{idx}",
            )
        )
    db_session.commit()

    with _BASELINE_LOCK:
        OFFICIAL_STORE_BASELINE.clear()
        OFFICIAL_STORE_BASELINE.update(_empty_store_state())
        OFFICIAL_STORE_BASELINE["apple_impressions_total"] = 1280
        OFFICIAL_STORE_BASELINE["apple_page_views_total"] = 200
        OFFICIAL_STORE_BASELINE["apple_taps_total"] = 75
        OFFICIAL_STORE_BASELINE["apple_taps_unique"] = 68

    summary = _build_analytics_summary(db_session, period="all")
    t_days = {d["date"]: d for d in summary["timeline_days"]}
    assert "2026-11-07" in t_days
    assert t_days["2026-11-07"]["is_store_pending"] is False
    assert t_days["2026-11-07"]["is_r14_pending"] is True
    assert t_days["2026-11-06"]["is_r14_pending"] is False

    ps_all = summary["platform_split"]["all"]
    ps_ios = summary["platform_split"]["ios"]
    assert 0.0 < ps_all["vis_of_imp_pct"] <= 100.0
    assert 0.0 < ps_ios["vis_of_imp_pct"] <= 100.0
    assert "Mağaza:" in ps_all["imp_breakdown_label"]
    assert "Köprü" in ps_all["imp_breakdown_label"]

    browse_row = next(r for r in summary["aso_attribution_matrix"] if "Keşfet" in r["channel"])
    assert "(0 Cihaz)" not in browse_row["page_views_or_clicks"]
    assert "Bio Köprü Tıkı" in browse_row["page_views_or_clicks"]

    dash_html = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"}).text
    assert "🔄 Senkronize Et" not in dash_html
    assert "213 kurulumda opt-in düzeltmeli" not in dash_html
    assert 'id="convBridge1Sub"' in dash_html
    assert 'id="liveClicksTbody"' in dash_html
    assert 'id="liveClicksHeadSpan"' in dash_html
    assert "if (isPolling || document.hidden) return;" in dash_html
    assert "if (cc4) cc4.textContent = '%' + vipOfVis;" in dash_html


def test_apple_t1_lag_period_revenue_reconciliation_and_rc_v2_bridge(client, db_session):
    """
    Apple App Store Connect Trends (1 Gün / T-1 PST Gecikmeli) & Google Play Console & RevenueCat V2
    gelir mutabakatı doğrulaması:
    1) Tüm Zamanlar (period=all) 27 Ekim (149.99 ₺ / 83.12 ₺) + 04 Kasım (599.99 ₺ / 332.49 ₺) = 749.98 ₺ Brüt / 415.61 ₺ Net (~$17.50 / ~$9.70),
    2) Son 7 Gün (period=7d, Apple T-1 penceresi: 2026-11-01 ➔ 2026-11-07) yalnızca 04 Kasım tahsilatını içerir = 599.99 ₺ Brüt / 332.49 ₺ Net (~$14.00 / ~$7.76),
    3) RC_T0_* geçici köprü kaydının resmi Apple SUBSCRIBER TSV satırı geldiğinde otomatik tekilleştirilmesi (deduplication),
    4) Dashboard HTML (GET /api/v1/analytics/dashboard?period=7d) üzerinde storeReconciliationCard render kontrolü.
    """
    from app.db.models import StoreDailyMetric, SubscriberLedger
    from app.api.v1.endpoints.analytics import (
        _build_analytics_summary,
        _reconcile_ios_ledger_and_cancellations,
        OFFICIAL_STORE_BASELINE,
        _empty_store_state,
        _BASELINE_LOCK,
    )

    StoreDailyMetric.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    SubscriberLedger.__table__.create(bind=db_session.get_bind(), checkfirst=True)

    db_session.query(StoreDailyMetric).delete()
    db_session.query(SubscriberLedger).delete()

    # Son kesinleşen Apple rapor tarihi T-1 = 2026-11-07 olarak simüle edilir
    db_session.add(
        StoreDailyMetric(
            metric_date="2026-11-07",
            platform="ios",
            impressions=520,
            page_views=85,
            downloads_total=9,
            downloads_search=6,
            downloads_referrer=2,
            downloads_browse=1,
            active_sessions=40,
        )
    )

    # 1) 2026-10-27 Aylık Ücretli (149.99 ₺ Brüt / 83.12 ₺ Net) — Son 7 Gün (01–07 Kasım) dışında
    # 2) 2026-11-04 Yıllık Ücretli (599.99 ₺ Brüt / 332.49 ₺ Net) — Son 7 Gün (01–07 Kasım) içinde
    # 3) DamlaEge2026 Yıllık Kodlu fakat RevenueCat V2 will_change_product ile 149.99 ₺ Aylık pakete geçiş planlamış abone
    # 4) Aynı gün (2026-11-07) için hem RC_T0_* geçici köprü kaydı hem resmi Apple SUBSCRIBER satırı (dedup testi)
    db_session.add_all([
        SubscriberLedger(
            subscriber_id="420003382813562",
            platform="ios",
            product_id="misil_monthly",
            plan_label="Aylık VIP",
            status="paid_active",
            offer_type="standard_paid",
            started_date="2026-10-20",
            converted_or_renewed_date="2026-10-27",
            maturity_or_renewal_date="2026-11-27",
            auto_renew_enabled=True,
            customer_price_try=149.99,
            developer_proceeds_try=83.12,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="540002819996540",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="paid_active",
            offer_type="standard_paid",
            started_date="2026-10-28",
            converted_or_renewed_date="2026-11-04",
            maturity_or_renewal_date="2027-11-04",
            auto_renew_enabled=True,
            customer_price_try=599.99,
            developer_proceeds_try=332.49,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.49,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="540002813825863",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP (Kod ➔ Aylık VIP Geçişi Planlı)",
            status="offer_code_trial",
            offer_type="offer_code_trial",
            offer_code_name="DamlaEge2026",
            started_date="2026-10-22",
            converted_or_renewed_date="2026-10-22",
            maturity_or_renewal_date="2027-10-22",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=149.99,
            expected_next_proceeds_try=83.12,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="RC_T0_9988776655",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-11-07",
            converted_or_renewed_date="2026-11-07",
            maturity_or_renewal_date="2026-11-14",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.49,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="RC_T0_9988776699",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-11-07",
            converted_or_renewed_date="2026-11-07",
            maturity_or_renewal_date="2026-11-14",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.49,
            country="TR",
            device_type="iPhone",
        ),
        SubscriberLedger(
            subscriber_id="440002975544332",
            platform="ios",
            product_id="misil_annual",
            plan_label="Yıllık VIP",
            status="intro_free_trial",
            offer_type="intro_7d_trial",
            started_date="2026-11-07",
            converted_or_renewed_date="2026-11-07",
            maturity_or_renewal_date="2026-11-14",
            auto_renew_enabled=True,
            customer_price_try=0.0,
            developer_proceeds_try=0.0,
            expected_next_price_try=599.99,
            expected_next_proceeds_try=332.49,
            country="TR",
            device_type="iPhone",
        ),
    ])
    db_session.commit()

    # Resmi Apple SUBSCRIBER satırı (440002975544332, 1 adet) mevcutken 2 adet RC_T0_* kaydından yalnızca 1'i silinmeli, 2. abone korunmalı
    _reconcile_ios_ledger_and_cancellations(db_session)
    db_session.commit()
    remaining_ids = {r.subscriber_id for r in db_session.query(SubscriberLedger).all()}
    assert "RC_T0_9988776655" not in remaining_ids
    assert "RC_T0_9988776699" in remaining_ids
    assert "440002975544332" in remaining_ids

    with _BASELINE_LOCK:
        OFFICIAL_STORE_BASELINE.clear()
        OFFICIAL_STORE_BASELINE.update(_empty_store_state())
        OFFICIAL_STORE_BASELINE["apple_latest_report_date"] = "2026-11-07"
        OFFICIAL_STORE_BASELINE["apple_report_lag_days"] = 1

    sum_all = _build_analytics_summary(db_session, period="all")
    fl_all = sum_all["financial_ledger"]
    sr = fl_all["store_reconciliation"]

    assert fl_all["realized_gross_try"] == 749.98
    assert fl_all["realized_net_proceeds_try"] == 415.61
    assert fl_all["period_realized_gross_try"] == 749.98
    assert fl_all["period_realized_net_proceeds_try"] == 415.61
    assert sr["all_time"]["gross_try"] == 749.98
    assert sr["all_time"]["net_try"] == 415.61
    assert sr["last_7d_t1"]["gross_try"] == 599.99
    assert sr["last_7d_t1"]["net_try"] == 332.49
    assert sr["rc_v2_crossgrades_count"] == 1
    assert sr["rc_v2_crossgrades_net_try"] == 83.12

    sum_7d = _build_analytics_summary(db_session, period="7d")
    fl_7d = sum_7d["financial_ledger"]
    assert fl_7d["period_realized_gross_try"] == 599.99
    assert fl_7d["period_realized_net_proceeds_try"] == 332.49
    assert fl_7d["realized_gross_try"] == 749.98
    assert fl_7d["realized_net_proceeds_try"] == 415.61

    dash_7d = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842", "period": "7d"})
    assert dash_7d.status_code == 200
    assert 'id="storeReconciliationCard"' in dash_7d.text
    assert 'id="countryRevenueCard"' in dash_7d.text
    assert 'id="tab2SubNav"' in dash_7d.text
    assert "332.49 ₺" in dash_7d.text
    assert "415.61 ₺" in dash_7d.text
    assert fl_all["paid_countries_count"] == 1
    assert len(fl_all["country_revenue_breakdown"]) >= 1
    tr_row = next(r for r in fl_all["country_revenue_breakdown"] if r["code"] == "TR")
    assert tr_row["paid_subs_count"] == 2
    assert tr_row["paid_annual_count"] == 1
    assert tr_row["paid_monthly_count"] == 1
    assert tr_row["realized_gross_try"] == 749.98
    assert tr_row["realized_net_try"] == 415.61
    assert tr_row["share_of_revenue_pct"] == 100.0


def test_ppp_store_pricing_invariants_and_multicurrency_fx():
    """
    PPP Küresel Mağaza Fiyatlandırma Motoru ve Çoklu Para Birimi (FX_RATES_TO_TRY) Bütünlük Testi:
    1) TR (149.99 / 599.99 TRY) ve CH (5.00 / 25.00 CHF) koruma kilitlerinin doğrulanması,
    2) Tüm hedef ülkelerde (UZ, AZ, KZ, IN, BR, MX, PL, RO, DE, GB, US, AE, SA) en ucuz rakibin altında kalındığının doğrulanması,
    3) Google Play 174 bölge yapılandırıcısının (build_google_play_174_configs) ve FX_RATES_TO_TRY dönüşümlerinin doğrulanması.
    """
    from app.api.v1.endpoints.analytics import FX_RATES_TO_TRY, _convert_to_try
    from scripts.sync_ppp_store_pricing import (
        APPLE_PPP_TARGETS,
        GOOGLE_PLAY_EXPLICIT_TARGETS,
        assert_tr_ch_invariants,
        build_google_play_174_configs,
        float_to_gp_price,
        gp_price_to_float,
    )

    assert_tr_ch_invariants()

    # En ucuz rakip tavanları (Aylık, Yıllık): Mışıl Baby daima <= olmalı
    cheapest_competitor_ceilings = {
        "UZ": (2.99, 13.99),
        "AZ": (2.99, 19.99),
        "KZ": (1490.0, 9990.0),
        "IN": (199.0, 1200.0),
        "BR": (22.90, 69.90),
        "MX": (49.0, 399.0),
        "PL": (14.99, 99.99),
        "RO": (14.99, 99.99),
        "DE": (4.99, 38.49),
        "GB": (4.99, 31.99),
        "US": (4.99, 39.99),
        "AE": (17.99, 119.99),
    }
    for cc, (comp_m, comp_y) in cheapest_competitor_ceilings.items():
        m_val, y_val, _ = APPLE_PPP_TARGETS[cc]
        assert m_val <= comp_m, f"{cc} aylık fiyat ({m_val}) rakip tavanını ({comp_m}) aşıyor!"
        assert y_val < comp_y, f"{cc} yıllık fiyat ({y_val}) rakip tavanının ({comp_y}) altında değil!"

    # Google Play Money dönüşümü ve 174 bölge şablon testi
    sample_template = [
        {"regionCode": "TR", "price": float_to_gp_price(719.99, "TRY")},
        {"regionCode": "CH", "price": float_to_gp_price(10.0, "CHF")},
        {"regionCode": "DE", "price": float_to_gp_price(12.99, "EUR")},
        {"regionCode": "BG", "price": float_to_gp_price(12.99, "EUR")},
        {"regionCode": "UZ", "price": float_to_gp_price(166560.0, "UZS")},
        {"regionCode": "AZ", "price": float_to_gp_price(21.06, "AZN")},
        {"regionCode": "PL", "price": float_to_gp_price(56.99, "PLN")},
        {"regionCode": "JP", "price": {"currencyCode": "JPY", "units": "2120", "nanos": 0}},
        {"regionCode": "CL", "price": {"currencyCode": "CLP", "units": "13800", "nanos": 0}},
    ]
    gp_ann = build_google_play_174_configs(sample_template, is_annual=True)
    gp_mon = build_google_play_174_configs(sample_template, is_annual=False)
    ann_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_ann}
    mon_map = {x["regionCode"]: gp_price_to_float(x["price"]) for x in gp_mon}
    mon_raw_map = {x["regionCode"]: x["price"] for x in gp_mon}

    assert ann_map["TR"] == (599.99, "TRY")
    assert mon_map["TR"] == (149.99, "TRY")
    assert ann_map["CH"] == (25.00, "CHF")
    assert mon_map["CH"] == (5.00, "CHF")
    assert ann_map["DE"] == (29.99, "EUR")
    assert mon_map["DE"] == (4.99, "EUR")
    assert ann_map["BG"] == (16.99, "EUR")
    assert mon_map["BG"] == (3.49, "EUR")
    assert ann_map["PL"] == (69.99, "PLN")
    assert mon_map["PL"] == (14.99, "PLN")
    assert mon_raw_map["JP"]["nanos"] == 0
    assert mon_raw_map["CL"]["nanos"] == 0 and int(mon_raw_map["CL"]["units"]) % 100 == 0

    # FX_RATES_TO_TRY çoklu para birimi ve USD<->TRY parite mutabakat kontrolü
    from app.api.v1.endpoints.analytics import APPLE_TRENDS_USD_TRY_RATE, _convert_try_to_usd
    assert abs(FX_RATES_TO_TRY["USD"] - APPLE_TRENDS_USD_TRY_RATE) < 1e-4
    assert _convert_try_to_usd(_convert_to_try(100.0, "USD")) == 100.0
    for req_ccy in ("PLN", "RON", "KZT", "UZS", "AZN", "INR", "BRL", "MXN", "AED", "SAR"):
        assert req_ccy in FX_RATES_TO_TRY
        assert _convert_to_try(100.0, req_ccy) > 0.0


def test_cockpit_v3_ssot_no_ratchet_and_data_architecture_tab(client, db_session):
    """
    3 Ajanlı Konsensüs (Claude task-48 + Codex task-54 + Antigravity) Doğrulaması:
    1) StoreDailyMetric resmi iOS indirme verisi (15) mevcutken 25 adet first_open istemci sinyaliyle
       max() alınarak resmi iOS indirme sayısının 25'e şişirilmemesi (SSOT korunması),
    2) Üst barda referans kartı kalabalığının kaldırılması ve 5. sekmenin '🏛️ 5. Referanslar & Veri Mimarisi'
       olarak Hangi Veri, Hangi Yöntemle, Ne Frekansta Güncellenir? tablosunu içermesi.
    """
    from app.db.models import StoreDailyMetric, AppInstallSignal
    from app.api.v1.endpoints.analytics import (
        _build_analytics_summary,
        OFFICIAL_STORE_BASELINE,
        _empty_store_state,
        _BASELINE_LOCK,
    )

    StoreDailyMetric.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    AppInstallSignal.__table__.create(bind=db_session.get_bind(), checkfirst=True)
    db_session.query(StoreDailyMetric).delete()
    db_session.query(AppInstallSignal).delete()

    with _BASELINE_LOCK:
        OFFICIAL_STORE_BASELINE.clear()
        OFFICIAL_STORE_BASELINE.update(_empty_store_state())

    db_session.add(
        StoreDailyMetric(
            metric_date="2026-11-08",
            platform="ios",
            impressions=400,
            page_views=80,
            downloads_total=15,
            active_sessions=30,
        )
    )
    for idx in range(25):
        db_session.add(
            AppInstallSignal(
                device_uid=f"ios_sig_dev_{idx}",
                event_type="first_open",
                os_family="ios",
                platform="ios_native",
            )
        )
    db_session.commit()

    summary = _build_analytics_summary(db_session, period="all")
    # Resmi iOS indirmesi StoreDailyMetric (15) olmalı, 25 istemci sinyaliyle şişirilmemeli;
    # first_open_signals ise kendi T-0 alanında 25 olarak görünmeli.
    assert summary["cumulative_kpis"]["ios_downloads"] == 15
    assert summary["product_funnel"]["first_open_signals"] == 25
    assert len(summary["data_governance_matrix"]) == 6
    assert len(summary["architecture_principles"]) == 4

    dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
    assert dash_res.status_code == 200
    html_txt = dash_res.text
    assert '<div class="freshness-strip' not in html_txt
    assert "🏛️ 5. Referanslar & Veri Mimarisi" in html_txt
    assert 'id="dataGovernanceMatrixCard"' in html_txt
    assert 'id="architecturePrinciplesCard"' in html_txt
    assert 'id="syncPipelinesStatusCard"' in html_txt
    assert "Hangi Veri, Hangi Yöntemle, Ne Frekansta Güncellenir?" in html_txt


def test_cockpit_v4_executive_app_shell_progressive_disclosure_and_search(client):
    """
    v4.56.1 3-Ajanlı Konsensüs Full-Viewport App Shell & Minimalist Bento UI Denetimi:
    1. Sol sabit 100vh koyu sidebar (.cockpit-shell & .cockpit-sidebar, position: fixed) ve 2 sütunlu Bento (.bento-split-2col) aktif olmalı,
    2. Uzun açıklama paragrafları (.sr-only, .card-desc, .step-sub) gizlenip tek satırlık mikro çipler (.kpi-micro-meta / .kpi-micro-chip) gösterilmeli,
    3. Kuzey Yıldızı hunisi daraltılabilir (toggleHeroFunnel / btnToggleHeroFunnel) olmalı,
    4. Yoğun tablolarda canlı arama (filterTableByQuery) ve sabit yükseklikli kaydırma (table-scroll-bounded) bulunmalı,
    5. Gereksiz ara 'cat-header' şeritleri DOM'dan temizlenmiş olmalı.
    """
    dash_res = client.get("/api/v1/analytics/dashboard", params={"pin": "MISIL-REV-9842"})
    assert dash_res.status_code == 200
    html_txt = dash_res.text

    assert 'class="cockpit-shell"' in html_txt
    assert 'class="cockpit-sidebar hide-in-pres"' in html_txt
    assert 'class="cockpit-main"' in html_txt
    assert 'class="bento-split-2col"' in html_txt
    assert 'class="bento-split-2col-equal"' in html_txt
    assert 'class="kpi-micro-meta"' in html_txt
    assert 'class="kpi-micro-chip"' in html_txt
    assert 'id="btnToggleHeroFunnel"' in html_txt
    assert "function toggleHeroFunnel()" in html_txt
    assert "function filterTableByQuery(inputEl, tbodyId)" in html_txt
    assert 'id="countryRevenueTableBody"' in html_txt
    assert 'id="appleLedgerTbody"' in html_txt
    assert 'class="table-wrap table-scroll-bounded"' in html_txt
    assert '<div class="cat-header">' not in html_txt









