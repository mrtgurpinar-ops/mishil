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
