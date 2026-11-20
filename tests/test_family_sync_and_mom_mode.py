# -*- coding: utf-8 -*-
"""
v4.52.0 — Ortak Tek Bebek Aile Takibi (max_members=3) & Anne Köşesi (Mom Break + Mışıl Dadı audience='mom')
Kapsamlı Entegrasyon ve Güvenlik Test Paketi (P0-1..P0-7, P1-1..P1-6).
"""
from datetime import datetime, timezone, timedelta

from app.api.v1.endpoints.family import verify_realtime_token
from app.db.models import SubscriberLedger
from app.main import run_safe_schema_migrations
from tests.conftest import engine_test


def test_idempotent_safe_schema_migrations():
    """run_safe_schema_migrations arka arkaya çalıştırıldığında hata fırlatmadan idempotent tamamlanmalı."""
    run_safe_schema_migrations(engine_test)
    run_safe_schema_migrations(engine_test)


def test_family_max_3_members_idempotent_rejoin_and_leave_slot_recovery(client):
    """
    Aile başına maksimum 3 üye (Anne, Baba, Dadı) sınırını, doğrulanan token ile idempotent
    yeniden katılmayı ve DELETE /family/membership sonrası 3. koltuğun tekrar açılmasını doğrular.
    """
    r_create = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "Atlas",
            "birth_date": "2026-04-10",
            "creator_role": "mother",
            "creator_name": "Zeynep",
            "device_uid": "dev-atlas-mom",
        },
    )
    assert r_create.status_code == 200
    body = r_create.json()
    code = body["invite_code"]
    assert code.startswith("MB-") and len(code) >= 7
    assert body["family"]["max_members"] == 3
    assert len(body["family"]["members"]) == 1

    # HMAC-SHA256 realtime_token doğrulaması (P0-4: room_key içerir, ham invite_code sızdırmaz!)
    rt_claims = verify_realtime_token(body["realtime_token"])
    assert rt_claims is not None
    assert rt_claims["rk"] != code
    assert rt_claims["exp"] > int(datetime.now(timezone.utc).timestamp())

    # 2. Üye (Baba) katılır
    r_dad = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code,
            "role": "father",
            "name": "Kerem",
            "device_uid": "dev-atlas-dad",
        },
    )
    assert r_dad.status_code == 200
    dad_token = r_dad.json()["member_token"]
    assert len(r_dad.json()["family"]["members"]) == 2

    # Baba kendi member_token'ı ile tekrar join çağırırsa 4. üye sayılmaz, 200 OK döner
    r_dad_rejoin = client.post(
        "/api/v1/family/join",
        headers={"X-Family-Member-Token": dad_token},
        json={
            "invite_code": code,
            "role": "father",
            "name": "Kerem Baba",
            "device_uid": "dev-atlas-dad",
        },
    )
    assert r_dad_rejoin.status_code == 200
    assert len(r_dad_rejoin.json()["family"]["members"]) == 2

    # 3. Üye (Dadı) katılır
    r_nanny = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code,
            "role": "nanny",
            "name": "Ayten Abla",
            "device_uid": "dev-atlas-nanny",
        },
    )
    assert r_nanny.status_code == 200
    nanny_token = r_nanny.json()["member_token"]
    assert len(r_nanny.json()["family"]["members"]) == 3

    # 4. Farklı cihaz katılmak istediğinde 409 FAMILY_FULL döner
    r_fourth = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code,
            "role": "grandparent",
            "name": "Babaanne",
            "device_uid": "dev-atlas-grandma",
        },
    )
    assert r_fourth.status_code == 409
    err_body = r_fourth.json()
    assert err_body["error_code"] == "FAMILY_FULL"
    assert err_body["max_members"] == 3

    # P1-6: Dadı üyeliğini sildiğinde koltuk boşalır ve 4. cihaz artık katılabilir!
    r_leave = client.delete(
        f"/api/v1/family/membership?invite_code={code}&device_uid=dev-atlas-nanny",
        headers={"X-Family-Member-Token": nanny_token},
    )
    assert r_leave.status_code == 200
    assert r_leave.json()["status"] == "member_removed"
    assert r_leave.json()["remaining_members"] == 2

    r_grandma_now_fits = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code,
            "role": "grandparent",
            "name": "Babaanne",
            "device_uid": "dev-atlas-grandma",
        },
    )
    assert r_grandma_now_fits.status_code == 200
    assert len(r_grandma_now_fits.json()["family"]["members"]) == 3


def test_vip_ledger_expiry_revokes_family_vip_and_subscriber_sync_upgrades(client, db_session):
    """
    Süresi geçmiş SubscriberLedger kaydının VIP vermediğini ve doğrulanmış SubscriberLedger
    güncellemesi sonrası bulut ailesine VIP kazandırdığını doğrular.
    """
    expired_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    ledger_row = SubscriberLedger(
        subscriber_id="GPA_TOKEN_exp_test_001",
        device_uid="dev-ege-mom",
        platform="android",
        product_id="misilaylik",
        plan_label="Aylık Esnek",
        status="paid_active",
        offer_type="standard_paid",
        started_date="2026-08-01",
        maturity_or_renewal_date=expired_date,
        customer_price_try=129.99,
        developer_proceeds_try=110.49,
    )
    db_session.add(ledger_row)
    db_session.commit()

    r_create = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "Ege",
            "birth_date": "2026-05-01",
            "creator_role": "mother",
            "creator_name": "Selin",
            "device_uid": "dev-ege-mom",
            "subscriber_id": "GPA_TOKEN_exp_test_001",
            "subscription_active": True,
            "subscription_plan": "monthly",
        },
    )
    assert r_create.status_code == 200
    assert r_create.json()["family"]["subscription_active"] is False
    code = r_create.json()["invite_code"]
    token = r_create.json()["member_token"]

    # Abonelik yenilendiğinde (vade ileri alındığında) /family/sync otomatik olarak VIP aktif döner
    future_date = (datetime.now(timezone.utc) + timedelta(days=25)).strftime("%Y-%m-%d")
    ledger_row.maturity_or_renewal_date = future_date
    db_session.commit()

    r_sync = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": token},
        json={
            "invite_code": code,
            "device_uid": "dev-ege-mom",
            "subscriber_id": "GPA_TOKEN_exp_test_001",
        },
    )
    assert r_sync.status_code == 200
    assert r_sync.json()["family"]["subscription_active"] is True
    assert r_sync.json()["family"]["subscription_plan"] == "monthly"


def test_cross_tenant_isolation_and_bidirectional_family_sync(client):
    """
    P0-2 & P0-3:
    - Yabancı veya eksik token ile /baby/profile, /sleep/log ve /family/sync çağrıları 403 döner.
    - Anne rutin eklediğinde, aşı/atak işaretlediğinde ve canlı uykuyu başlattığında Baba /family/sync ile birebir alır.
    - Baba bir rutini sildiğinde (deleted=True) ve uykuyu bitirdiğinde Anne'nin sonraki sync'inde güncellenir.
    """
    r_fam_a = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "Mina",
            "birth_date": "2026-03-15",
            "creator_role": "mother",
            "creator_name": "Elif",
            "device_uid": "dev-mina-mom",
        },
    )
    assert r_fam_a.status_code == 200
    code_a = r_fam_a.json()["invite_code"]
    mom_token_a = r_fam_a.json()["member_token"]
    baby_id_a = r_fam_a.json()["family"]["baby"]["id"]

    r_dad_a = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code_a,
            "role": "father",
            "name": "Can",
            "device_uid": "dev-mina-dad",
        },
    )
    assert r_dad_a.status_code == 200
    dad_token_a = r_dad_a.json()["member_token"]

    # Aile B (yabancı aile)
    r_fam_b = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "Bora",
            "birth_date": "2026-02-10",
            "creator_role": "father",
            "creator_name": "Ozan",
            "device_uid": "dev-bora-dad",
        },
    )
    outsider_token_b = r_fam_b.json()["member_token"]

    # 1. Cross-tenant & unauthenticated erişim engeli (P0-3)
    assert client.get(f"/api/v1/baby/profile/{baby_id_a}").status_code == 403
    assert (
        client.get(
            f"/api/v1/baby/profile/{baby_id_a}",
            headers={"X-Family-Member-Token": outsider_token_b},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/sleep/log",
            headers={"X-Family-Member-Token": outsider_token_b},
            json={
                "family_code": code_a,
                "baby_id": baby_id_a,
                "start_time": "2026-11-15T01:00:00Z",
                "end_time": "2026-11-15T02:00:00Z",
                "duration_minutes": 60,
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/family/sync",
            headers={"X-Family-Member-Token": outsider_token_b},
            json={"invite_code": code_a},
        ).status_code
        == 403
    )

    # Yetkili Anne kendi bebeğinin profilini okuyabilir ve uyku logu atabilir
    assert (
        client.get(
            f"/api/v1/baby/profile/{baby_id_a}",
            headers={"X-Family-Member-Token": mom_token_a},
        ).status_code
        == 200
    )
    r_sleep_valid = client.post(
        "/api/v1/sleep/log",
        headers={"X-Family-Member-Token": mom_token_a},
        json={
            "family_code": code_a,
            "baby_id": baby_id_a,
            "start_time": "2026-11-15T01:00:00Z",
            "end_time": "2026-11-15T02:15:00Z",
            "duration_minutes": 75,
        },
    )
    assert r_sleep_valid.status_code in (200, 201)

    # Negatif süreli (end_time < start_time) bozuk uyku kaydı reddedilir (400)
    r_sleep_bad = client.post(
        "/api/v1/sleep/log",
        headers={"X-Family-Member-Token": mom_token_a},
        json={
            "family_code": code_a,
            "baby_id": baby_id_a,
            "start_time": "2026-11-15T03:00:00Z",
            "end_time": "2026-11-15T02:00:00Z",
            "duration_minutes": 60,
        },
    )
    assert r_sleep_bad.status_code in (400, 422)

    # 2. Anne /family/sync + /family/leap-override ile tüm ortak bebek durumunu buluta yazar
    live_sleep_iso = "2026-11-15T07:10:00.000Z"
    r_leap = client.post(
        "/api/v1/family/leap-override",
        headers={"X-Family-Member-Token": mom_token_a},
        json={"invite_code": code_a, "leap_number": 4, "is_active": True},
    )
    assert r_leap.status_code == 200

    r_mom_sync = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": mom_token_a},
        json={
            "invite_code": code_a,
            "active_sleep_start_iso": live_sleep_iso,
            "checked_vaccines": ["tr_m0_hepb", "tr_m2_karma1"],
            "checked_leaps": ["5", "8"],
            "routines": [
                {
                    "id": "rt_feed_101",
                    "type": "feeding",
                    "time": "06:45",
                    "timestamp": 1763189100000,
                    "detail": "Anne Sütü • Sağ • 15 dk",
                },
                {
                    "id": "rt_diaper_102",
                    "type": "diaper",
                    "time": "07:00",
                    "timestamp": 1763190000000,
                    "detail": "Islak Bez",
                },
            ],
        },
    )
    assert r_mom_sync.status_code == 200

    # 3. Baba GET /family/sync/{code} ile çektiğinde ortak tek bebek verilerini anında görür
    r_dad_pull = client.get(
        f"/api/v1/family/sync/{code_a}?device_uid=dev-mina-dad",
        headers={"X-Family-Member-Token": dad_token_a},
    )
    assert r_dad_pull.status_code == 200
    snap = r_dad_pull.json()["family"]
    assert snap["active_sleep_start_iso"] == live_sleep_iso
    assert set(snap["checked_vaccines"]) == {"tr_m0_hepb", "tr_m2_karma1"}
    assert set(snap["checked_leaps"]) == {"5", "8"}
    assert snap["baby"]["manual_leap"] == 4
    active_ids = {r["id"] for r in snap["routines"] if not r.get("deleted")}
    assert {"rt_feed_101", "rt_diaper_102"}.issubset(active_ids)

    # 4. Baba rt_diaper_102'yi siler (deleted=True) ve uykuyu sonlandırır (active_sleep_start_iso="")
    r_dad_del = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": dad_token_a},
        json={
            "invite_code": code_a,
            "active_sleep_start_iso": "",
            "routines": [{"id": "rt_diaper_102", "deleted": True}],
        },
    )
    assert r_dad_del.status_code == 200
    snap_after = r_dad_del.json()["family"]
    assert snap_after["active_sleep_start_iso"] is None
    deleted_map = {r["id"]: r["deleted"] for r in snap_after["routines"]}
    assert deleted_map["rt_diaper_102"] is True
    assert deleted_map["rt_feed_101"] is False


def test_whisper_handoff_night_watch_pulse_and_invite_landing_xss_safety(client):
    """
    - Sessiz Eş Nöbet Fısıltısı (/whisper & /whisper/ack) HTML etiketlerini temizler, <=140 karakter sınırlar.
    - Gece Nöbeti Feneri (/night-watch/pulse) anonim sayacı döner.
    - GET /invite/{code} XSS kaçışlı HTML döner ve eski MSL782 kodunu içermez.
    """
    r_create = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "<script>alert(1)</script>Mert",
            "birth_date": "2026-07-01",
            "creator_role": "mother",
            "creator_name": "Derya",
            "device_uid": "dev-mert-mom",
        },
    )
    assert r_create.status_code == 200
    code = r_create.json()["invite_code"]
    mom_token = r_create.json()["member_token"]

    r_dad = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code,
            "role": "father",
            "name": "Emre",
            "device_uid": "dev-mert-dad",
        },
    )
    dad_token = r_dad.json()["member_token"]

    # Anne fısıltı gönderir (içinde kötücül HTML olsa bile temizlenmeli)
    r_whisper = client.post(
        "/api/v1/family/whisper",
        headers={"X-Family-Member-Token": mom_token},
        json={
            "invite_code": code,
            "device_uid": "dev-mert-mom",
            "template_key": "tea_water",
            "custom_note": "<b>Bir bardak ılık su</b> getirir misin? <img src=x onerror=alert(1)>",
        },
    )
    assert r_whisper.status_code == 200
    whisper_obj = r_whisper.json()["whisper"]
    assert "<script>" not in whisper_obj["message_text"]
    assert "<img" not in whisper_obj["message_text"]
    assert "<b>" not in whisper_obj["message_text"]
    assert "Bir bardak ılık su" in whisper_obj["message_text"]

    # Baba /family/sync ile bekleyen fısıltıyı görür ve ack eder
    r_dad_sync = client.get(
        f"/api/v1/family/sync/{code}?device_uid=dev-mert-dad",
        headers={"X-Family-Member-Token": dad_token},
    )
    pending = r_dad_sync.json()["family"]["whispers"]
    assert len(pending) == 1
    wid = pending[0]["id"]

    r_ack = client.post(
        "/api/v1/family/whisper/ack",
        headers={"X-Family-Member-Token": dad_token},
        json={
            "invite_code": code,
            "whisper_id": wid,
            "device_uid": "dev-mert-dad",
        },
    )
    assert r_ack.status_code == 200
    assert r_ack.json()["success"] is True

    # Ack sonrası tekrar görünmez
    r_dad_sync_after = client.get(
        f"/api/v1/family/sync/{code}?device_uid=dev-mert-dad",
        headers={"X-Family-Member-Token": dad_token},
    )
    assert r_dad_sync_after.json()["family"]["whispers"] == []

    # Gece nöbeti feneri nabzı + anonim dayanışma kalbi
    r_pulse_1 = client.post(
        "/api/v1/family/night-watch/pulse",
        json={"device_uid": "dev-mert-mom", "is_sleeping_watch": True, "send_heart": False},
    )
    assert r_pulse_1.status_code == 200
    assert r_pulse_1.json()["active_watchers"] >= 1

    r_pulse_2 = client.post(
        "/api/v1/family/night-watch/pulse",
        json={"device_uid": "dev-other-night-parent", "is_sleeping_watch": True, "send_heart": True},
    )
    assert r_pulse_2.status_code == 200
    assert r_pulse_2.json()["active_watchers"] >= 2
    assert r_pulse_2.json()["heart_sent"] is True

    # Anne tekrar yokladığında diğer ebeveynin gönderdiği kalp sayısını görür
    r_pulse_mom_check = client.post(
        "/api/v1/family/night-watch/pulse",
        json={"device_uid": "dev-mert-mom", "is_sleeping_watch": True, "send_heart": False},
    )
    assert r_pulse_mom_check.json()["peer_hearts_recent"] >= 1

    # Davet köprü sayfası (/invite/{code}) XSS-safe olmalı ve MSL782 barındırmamalı
    r_inv = client.get(f"/invite/{code}")
    assert r_inv.status_code == 200
    html = r_inv.text
    assert code in html
    assert "<script>alert(1)</script>" not in html
    assert "MSL782" not in html
    assert f"/app?code={code}" in html


def test_mishil_dadi_mom_audience_and_crisis_safety_guardrail(client):
    """
    Mışıl Dadı audience='mom' modunda TR/EN/DE anne öz-şefkat yanıtı döner;
    kendine/bebeğe zarar kriz ifadelerinde LLM beklemeden deterministik acil destek hattı döner.
    """
    for lang, msg in [
        ("tr", "Gece emzirirken kendimi çok yalnız ve tükenmiş hissediyorum."),
        ("en", "Everyone asks about the baby, nobody asks how I am feeling tonight."),
        ("de", "Ich bin heute Nacht so müde und fühle mich allein beim Stillen."),
    ]:
        r_mom = client.post(
            "/api/v1/coach/chat",
            json={
                "message": msg,
                "baby_name": "Defne",
                "birth_date": "2026-07-01",
                "lang": lang,
                "audience": "mom",
            },
        )
        assert r_mom.status_code == 200
        body = r_mom.json()
        assert body["audience"] == "mom"
        assert body["reply"] and len(body["reply"]) > 20

    # Kriz Güvenlik Kalkanı (TR -> 112 / 182, EN -> 988, DE -> 0800 111 0 111)
    r_crisis_tr = client.post(
        "/api/v1/coach/chat",
        json={
            "message": "Artık dayanamıyorum, kendime zarar vermek istiyorum.",
            "baby_name": "Defne",
            "lang": "tr",
            "audience": "mom",
        },
    )
    assert r_crisis_tr.status_code == 200
    assert "Safety" in r_crisis_tr.json()["tier_used"] or "Crisis" in r_crisis_tr.json()["tier_used"]
    assert "112" in r_crisis_tr.json()["reply"]
    assert "182" in r_crisis_tr.json()["reply"]

    r_crisis_en = client.post(
        "/api/v1/coach/chat",
        json={
            "message": "I don't want to live anymore, I want to hurt myself",
            "lang": "en",
            "audience": "mom",
        },
    )
    assert r_crisis_en.status_code == 200
    assert "988" in r_crisis_en.json()["reply"]

    r_crisis_de = client.post(
        "/api/v1/coach/stream",
        json={
            "message": "Ich kann nicht mehr leben und will mir wehtun",
            "lang": "de",
            "audience": "mom",
        },
    )
    assert r_crisis_de.status_code == 200
    assert "0800 111 0 111" in r_crisis_de.text


def test_cli_audit_remediations_non_family_idor_token_bypass_and_prod_secret(client, db_session):
    """
    Seviye 3 CLI Denetim Bulguları Doğrulaması (Claude task-518 & Codex task-519):
    1) Non-family baby_id üzerinde device_uid / Bearer JWT olmadan okuma ve yazma (IDOR) 403 döner.
    2) device_uid=None olan eski/JWT bebek kaydı kimlik doğrulamasız okunamaz/yazılamaz; yalnızca JWT sahibi erişir.
    3) Korumalı ailede X-Family-Member-Token olmadan salt device_uid bilgisini göndererek /baby/profile veya /sleep/log yazılamaz.
    4) ENVIRONMENT='production' altında varsayılan JWT_SECRET ile başlatma RuntimeError fırlatır.
    5) /invite/{code}?baby=... sayfasında <script> içindeki JS URL'sinde '&amp;baby=' çift-escape oluşmaz.
    """
    import pytest
    from app.core.config import Settings

    # 1. Cihaz izole (non-family) bebek oluştur
    r_solo = client.post(
        "/api/v1/baby/profile",
        json={
            "device_uid": "dev-solo-owner-99",
            "name": "SoloBebek",
            "birth_date": "2026-08-01",
        },
    )
    assert r_solo.status_code == 200
    solo_baby_id = r_solo.json()["baby_id"]

    # Yabancı cihaz veya kimliksiz çağrı uyku YAZAMAZ ve OKUYAMAZ (IDOR kapalı)
    assert (
        client.post(
            "/api/v1/sleep/log",
            json={"baby_id": solo_baby_id, "duration_minutes": 45},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/sleep/log",
            json={"baby_id": solo_baby_id, "device_uid": "dev-attacker-00", "duration_minutes": 45},
        ).status_code
        == 403
    )
    assert client.get(f"/api/v1/sleep/logs/{solo_baby_id}").status_code == 403
    assert client.get(f"/api/v1/baby/profile/{solo_baby_id}").status_code == 403

    # Gerçek cihaz sahibi hem yazabilir hem okuyabilir
    assert (
        client.post(
            "/api/v1/sleep/log",
            json={"baby_id": solo_baby_id, "device_uid": "dev-solo-owner-99", "duration_minutes": 45},
        ).status_code
        == 200
    )
    assert (
        client.get(f"/api/v1/sleep/logs/{solo_baby_id}?device_uid=dev-solo-owner-99").status_code
        == 200
    )

    # 2. device_uid=None olan JWT kullanıcısı bebeği kimliksiz erişime kapalı, kendi Bearer JWT'sine açık
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "jwt_owner_audit@mishil.app", "password": "securepassword123"},
    )
    jwt_token = reg.json()["access_token"]
    b_res = client.post(
        "/api/v1/auth/babies",
        headers={"Authorization": f"Bearer {jwt_token}"},
        json={"name": "JwtBebek", "birth_date": "2026-06-15T00:00:00Z"},
    )
    jwt_baby_id = b_res.json()["id"]

    assert client.get(f"/api/v1/sleep/logs/{jwt_baby_id}").status_code == 403
    assert client.get(f"/api/v1/baby/profile/{jwt_baby_id}").status_code == 403
    assert (
        client.post(
            "/api/v1/sleep/log",
            json={"baby_id": jwt_baby_id, "duration_minutes": 30},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/sleep/log",
            headers={"Authorization": f"Bearer {jwt_token}"},
            json={"baby_id": jwt_baby_id, "duration_minutes": 30},
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/sleep/logs/{jwt_baby_id}",
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).status_code
        == 200
    )

    # 3. Korumalı ailede X-Family-Member-Token olmadan bilinen device_uid ile bypass engeli
    r_fam = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "KorumaliBebek",
            "birth_date": "2026-05-20",
            "creator_role": "mother",
            "creator_name": "Seda",
            "device_uid": "dev-known-mom-uid",
        },
    )
    fcode = r_fam.json()["invite_code"]
    assert (
        client.post(
            "/api/v1/baby/profile",
            json={
                "family_code": fcode,
                "device_uid": "dev-known-mom-uid",
                "name": "Hacklendi",
                "birth_date": "2026-05-20",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/sleep/log",
            json={
                "family_code": fcode,
                "device_uid": "dev-known-mom-uid",
                "duration_minutes": 50,
            },
        ).status_code
        == 403
    )

    # 4. Production + default JWT_SECRET RuntimeError fırlatır
    with pytest.raises(RuntimeError, match="FATAL SECURITY ERROR"):
        Settings(
            ENVIRONMENT="production",
            JWT_SECRET="mishil_default_dev_jwt_secret_key_change_in_production_32_bytes",
        )

    # 5. /invite/{code}?baby=Mina JS URL çift-escape regresyon kontrolü
    r_inv_q = client.get(f"/invite/{fcode}?baby=Mina")
    assert r_inv_q.status_code == 200
    inv_html = r_inv_q.text
    assert f'href="/app?code={fcode}&amp;baby=Mina"' in inv_html
    assert f'window.location.href = "/app?code={fcode}&baby=Mina";' in inv_html

    # 6. Yetim family_id (karşılığı silinmiş FamilyGroup) bebek kaydı okuma/yazmada 403 döner (Codex Round 2 bulgusu)
    from app.db.models import Baby
    orphan_baby = Baby(
        user_id=1,
        family_id=999999,
        name="YetimKayit",
        birth_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    db_session.add(orphan_baby)
    db_session.commit()
    assert client.get(f"/api/v1/baby/profile/{orphan_baby.id}").status_code == 403
    assert client.get(f"/api/v1/sleep/logs/{orphan_baby.id}").status_code == 403
    assert (
        client.post(
            "/api/v1/sleep/log",
            json={"baby_id": orphan_baby.id, "duration_minutes": 30},
        ).status_code
        == 403
    )


def test_v4530_live_nursing_routine_sync_and_context_whispers(client):
    """
    v4.53.0:
    1. Canlı emzirme yapısal alanlarının (side='left'|'right'|'both', leftMin, rightMin, durationMin, method, note)
       hem client_id/category hem id/type biçiminde aile üyeleri arasında kayıpsız senkronlandığını,
       geçersiz side değerlerinin ise reddedildiğini doğrular.
    2. Emzirme bağlamlı eş fısıltılarının (nursing_water, nursing_burp_help) TR/EN/DE 3 dilde ve
       message / custom_note geriye dönük uyumluluğuyla çalıştığını doğrular.
    """
    r_create = client.post(
        "/api/v1/family/create",
        json={
            "baby_name": "Defne",
            "birth_date": "2026-07-01",
            "creator_role": "mother",
            "creator_name": "Elif",
            "device_uid": "dev-nurse-mom",
        },
    )
    assert r_create.status_code == 200
    code = r_create.json()["invite_code"]
    mom_token = r_create.json()["member_token"]

    r_dad = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": code,
            "role": "father",
            "name": "Mert",
            "device_uid": "dev-nurse-dad",
        },
    )
    assert r_dad.status_code == 200
    dad_token = r_dad.json()["member_token"]

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    r_sync = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": mom_token},
        json={
            "invite_code": code,
            "device_uid": "dev-nurse-mom",
            "routines": [
                {
                    "client_id": "rt_nurse_both_1",
                    "category": "feeding",
                    "sub_type": "breast",
                    "side": "both",
                    "leftMin": 12,
                    "rightMin": 8,
                    "duration_minutes": 20,
                    "title": "Beslenme",
                    "detail": "Anne Sütü • Sol 12 dk + Sağ 8 dk • 20 dk",
                    "notes": "<b>Sakin emdi</b>",
                    "time": "03:15",
                    "timestamp_ms": now_ms,
                },
                {
                    "id": "rt_nurse_invalid_side",
                    "type": "feeding",
                    "method": "breast",
                    "side": "invalid_hack",
                    "durationMin": 14,
                    "title": "Beslenme",
                    "detail": "Anne Sütü • 14 dk",
                    "time": "05:30",
                    "timestamp": now_ms + 1000,
                },
            ],
        },
    )
    assert r_sync.status_code == 200

    # Baba snapshot çektiğinde yapısal emzirme alanlarını ve temizlenmiş notu eksiksiz görür
    r_pull = client.get(
        f"/api/v1/family/sync/{code}?device_uid=dev-nurse-dad",
        headers={"X-Family-Member-Token": dad_token},
    )
    assert r_pull.status_code == 200
    routines = r_pull.json()["family"]["routines"]
    by_id = {item["id"]: item for item in routines}

    assert "rt_nurse_both_1" in by_id
    both_item = by_id["rt_nurse_both_1"]
    assert both_item["type"] == "feeding"
    assert both_item["method"] == "breast"
    assert both_item["side"] == "both"
    assert both_item["leftMin"] == 12
    assert both_item["rightMin"] == 8
    assert both_item["durationMin"] == 20
    assert both_item["note"] == "Sakin emdi"

    assert "rt_nurse_invalid_side" in by_id
    assert "side" not in by_id["rt_nurse_invalid_side"]
    assert by_id["rt_nurse_invalid_side"]["durationMin"] == 14

    # Emzirme ve nöbet devri fısıltı şablonları TR / EN / DE ve message alias kontrolü
    for lang_code, tpl_key, expected_word in [
        ("tr", "nursing_water", "Emziriyorum"),
        ("en", "nursing_burp_help", "burping"),
        ("de", "nursing_water", "stille"),
        ("tr", "handoff_fed_burped", "gazı çıkarıldı"),
        ("en", "handoff_fed_burped", "burped"),
        ("de", "handoff_fed_burped", "Bäuerchen"),
    ]:
        rw = client.post(
            "/api/v1/family/whisper",
            headers={"X-Family-Member-Token": mom_token},
            json={
                "invite_code": code,
                "device_uid": "dev-nurse-mom",
                "template_key": tpl_key,
                "lang": lang_code,
            },
        )
        assert rw.status_code == 200
        w_out = rw.json()["whisper"]
        assert expected_word in w_out["message_text"]
        assert w_out["message"] == w_out["message_text"]

    # Geriye dönük `send_cheer` alias desteği kontrolü (/night-watch/pulse)
    r_cheer_alias = client.post(
        "/api/v1/family/night-watch/pulse",
        json={"device_uid": "dev-legacy-cheer-client", "send_cheer": True},
    )
    assert r_cheer_alias.status_code == 200
    assert r_cheer_alias.json()["heart_sent"] is True

    # Geriye dönük `message` alanı ile custom fısıltı
    rw_custom = client.post(
        "/api/v1/family/whisper",
        headers={"X-Family-Member-Token": mom_token},
        json={
            "invite_code": code,
            "device_uid": "dev-nurse-mom",
            "template_key": "custom",
            "message": "Emzirme yastığını getirir misin?",
            "lang": "tr",
        },
    )
    assert rw_custom.status_code == 200
    assert rw_custom.json()["whisper"]["message_text"] == "Emzirme yastığını getirir misin?"


def test_family_create_and_sync_accept_dict_vaccines_custom_routines_and_pending_whispers(client):
    """
    E2E Regresyon Koruması (v4.54.0):
    1) app.html `checked_vaccines` ve `checked_leaps` alanlarını Dict (`{"vac_0": True}`, `{}`) olarak gönderdiğinde 422 dönmemeli.
    2) `sleep` veya `custom` rutinleri `/family/sync` ile gönderildiğinde `RoutineType.CUSTOM` AttributeError (500) oluşmamalı.
    3) Snapshot yanıtı hem `whispers` hem `pending_whispers` dizisini dönmeli.
    """
    r_create = client.post(
        "/api/v1/family/create",
        json={
            "invite_code": "MB-E2E987",
            "device_uid": "dev-e2e-mom-1",
            "creator_role": "mother",
            "creator_name": "Zeynep",
            "baby_name": "Atlas",
            "birth_date": "2026-07-15",
            "checked_vaccines": {"vac_hep_b_1": True, "vac_unused": False},
            "checked_leaps": {"leap_1": True},
            "manual_leap": None,
        },
    )
    assert r_create.status_code == 200
    c_body = r_create.json()
    mom_tok = c_body["member_token"]
    assert c_body["family"]["checked_vaccines"] == ["vac_hep_b_1"]
    assert c_body["family"]["checked_leaps"] == ["leap_1"]

    r_join = client.post(
        "/api/v1/family/join",
        json={
            "invite_code": "MB-E2E987",
            "role": "father",
            "name": "Murat",
            "device_uid": "dev-e2e-dad-1",
        },
    )
    assert r_join.status_code == 200
    dad_tok = r_join.json()["member_token"]

    r_sync = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": mom_tok},
        json={
            "invite_code": "MB-E2E987",
            "device_uid": "dev-e2e-mom-1",
            "checked_vaccines": {"vac_bcg": True},
            "checked_leaps": {},
            "deleted_routine_ids": [],
            "routines": [
                {"id": "rt_sleep_1", "type": "sleep", "title": "Gece Uykusu", "durationMins": 45, "timestamp": 1795120000000},
                {"id": "rt_custom_1", "type": "custom", "title": "D Vitamini", "detail": "3 damla", "timestamp": 1795120500000},
            ],
        },
    )
    assert r_sync.status_code == 200
    synced_by_id = {r["id"]: r for r in r_sync.json()["family"]["routines"]}
    assert synced_by_id["rt_sleep_1"]["type"] == "sleep"
    assert synced_by_id["rt_custom_1"]["type"] == "custom"

    r_w = client.post(
        "/api/v1/family/whisper",
        headers={"X-Family-Member-Token": mom_tok},
        json={
            "invite_code": "MB-E2E987",
            "device_uid": "dev-e2e-mom-1",
            "template_key": "handoff_fed_burped",
            "lang": "tr",
        },
    )
    assert r_w.status_code == 200

    r_dad_pull = client.get(
        "/api/v1/family/sync/MB-E2E987?device_uid=dev-e2e-dad-1",
        headers={"X-Family-Member-Token": dad_tok},
    )
    assert r_dad_pull.status_code == 200
    dad_fam = r_dad_pull.json()["family"]
    assert len(dad_fam["pending_whispers"]) == 1
    assert dad_fam["pending_whispers"] == dad_fam["whispers"]


def test_morning_sync_timestamp_parity_anti_poison_shield_and_sleeplog_self_heal(client):
    """
    v4.54.1 regresyon testi:
    1) /family/sync hem camelCase (timestamp/startTs/endTs) hem snake_case (timestamp_ms/start_ts/end_ts) döner.
    2) Düzenlenmemiş (editedAtMs yok) ve saat etiketleri değişmemiş dünkü kaydın eski istemci tarafından
       sabah 07:25 Date.now() ile ileri sarılması engellenir; buna karşın editedAtMs veya repairedAtMs ile
       yapılan gerçek güncelleme kabul edilir.
    3) Zaten bozulmuş bir RoutineLog kaydı, aynı client_id'li SleepLog kaydı üzerinden otomatik iyileşir.
    """
    r_create = client.post(
        "/api/v1/family/create",
        json={
            "invite_code": "MB-SYNC725",
            "baby_name": "Atlas",
            "birth_date": "2026-08-15",
            "creator_role": "mother",
            "creator_name": "Elif",
            "device_uid": "dev-sync-mom",
        },
    )
    assert r_create.status_code == 200
    mom_tok = r_create.json()["member_token"]

    yest_start_ms = 1795114200000  # Dün 21:30
    yest_end_ms = 1795118700000    # Dün 22:45
    morning_725_ms = yest_end_ms + 9 * 3600 * 1000  # Ertesi sabah 07:45 sahte zehirlenme

    # 1. Normal dün gece uykusu hem /sleep/log hem /family/sync ile kaydedilir
    r_slp = client.post(
        "/api/v1/sleep/log",
        headers={"X-Family-Member-Token": mom_tok},
        json={
            "family_code": "MB-SYNC725",
            "device_uid": "dev-sync-mom",
            "client_id": "slp_1795118700000_ab12",
            "start_time": "2026-11-19T18:30:00Z",
            "end_time": "2026-11-19T19:45:00Z",
            "duration_minutes": 75,
            "sleep_type": "night",
        },
    )
    assert r_slp.status_code == 200
    true_slp_end_ms = int(datetime(2026, 11, 19, 19, 45, tzinfo=timezone.utc).timestamp() * 1000)
    true_slp_start_ms = int(datetime(2026, 11, 19, 18, 30, tzinfo=timezone.utc).timestamp() * 1000)

    # Diyelim ki eski v4.54.0 istemcisi ilk kayıtta zaten zehirlenmiş 07:25 damgası yazmış olsun:
    r_poisoned_initial = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": mom_tok},
        json={
            "invite_code": "MB-SYNC725",
            "device_uid": "dev-sync-mom",
            "routines": [
                {
                    "id": "slp_1795118700000_ab12",
                    "type": "sleep",
                    "title": "Gece Uykusu",
                    "start": "21:30",
                    "end": "22:45",
                    "time": "22:45",
                    "durationMins": 75,
                    "timestamp": true_slp_end_ms + 31200000,  # Bozuk 07:25 damgası!
                    "startTs": true_slp_end_ms + 31200000 - 75 * 60000,
                    "endTs": true_slp_end_ms + 31200000,
                },
                {
                    "id": "rt_1763575200000",
                    "type": "feeding",
                    "title": "Emzirme",
                    "time": "21:00",
                    "timestamp": 1763575200000,
                },
            ],
        },
    )
    assert r_poisoned_initial.status_code == 200
    by_id = {r["id"]: r for r in r_poisoned_initial.json()["family"]["routines"]}

    # SleepLog çapası sayesinde bozuk RoutineLog anında gerçek dün saatine iyileşmiş dönmeli!
    healed_slp = by_id["slp_1795118700000_ab12"]
    assert healed_slp["endTs"] == true_slp_end_ms
    assert healed_slp["end_ts"] == true_slp_end_ms
    assert healed_slp["startTs"] == true_slp_start_ms
    assert healed_slp["start_ts"] == true_slp_start_ms
    assert healed_slp["timestamp"] == true_slp_end_ms
    assert healed_slp["timestamp_ms"] == true_slp_end_ms
    assert healed_slp["createdAtMs"] == 1795118700000

    # 2. Eski bir istemci rt_1763575200000 kaydını düzenlemeden (editedAtMs yok) ileri sararsa kalkan engeller!
    r_stale_push = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": mom_tok},
        json={
            "invite_code": "MB-SYNC725",
            "device_uid": "dev-sync-mom",
            "routines": [
                {
                    "id": "rt_1763575200000",
                    "type": "feeding",
                    "title": "Emzirme",
                    "time": "21:00",
                    "timestamp": 1763575200000 + 36000000,  # Sahte sabah Date.now()
                }
            ],
        },
    )
    assert r_stale_push.status_code == 200
    feed_after_stale = {r["id"]: r for r in r_stale_push.json()["family"]["routines"]}["rt_1763575200000"]
    assert feed_after_stale["timestamp"] == 1763575200000

    # 3. Kullanıcı kaydı gerçekten düzenlediğinde (editedAtMs mevcut) yeni saat kabul edilir!
    r_real_edit = client.post(
        "/api/v1/family/sync",
        headers={"X-Family-Member-Token": mom_tok},
        json={
            "invite_code": "MB-SYNC725",
            "device_uid": "dev-sync-mom",
            "routines": [
                {
                    "id": "rt_1763575200000",
                    "type": "feeding",
                    "title": "Emzirme",
                    "time": "21:15",
                    "timestamp": 1763576100000,
                    "editedAtMs": 1763612000000,
                }
            ],
        },
    )
    assert r_real_edit.status_code == 200
    feed_after_edit = {r["id"]: r for r in r_real_edit.json()["family"]["routines"]}["rt_1763575200000"]
    assert feed_after_edit["timestamp"] == 1763576100000
    assert feed_after_edit["editedAtMs"] == 1763612000000




