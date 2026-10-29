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



