from datetime import datetime, timezone, timedelta
import pytest
from app.models.enums import RoutineType, SubscriptionStatus


def test_auth_registration_and_login(client):
    """Test user registration, duplicate prevention, and login."""
    # Register
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "parent@mishil.app", "password": "securepassword", "full_name": "Canan Dağ"}
    )
    assert res.status_code == 201
    token_data = res.json()
    assert "access_token" in token_data
    token = token_data["access_token"]

    # Duplicate register should fail
    dup_res = client.post(
        "/api/v1/auth/register",
        json={"email": "parent@mishil.app", "password": "anotherpassword"}
    )
    assert dup_res.status_code == 400

    # Login
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "parent@mishil.app", "password": "securepassword"}
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # Get profile
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "parent@mishil.app"


def test_baby_creation_and_routines(client):
    """Test baby registration, wake window calculation by baby_id, and routine logging."""
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "baby_tester@mishil.app", "password": "password123"}
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create baby (born 6 months ago)
    six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
    baby_res = client.post(
        "/api/v1/auth/babies",
        headers=headers,
        json={"name": "Mavi", "birth_date": six_months_ago.isoformat(), "gender": "female"}
    )
    assert baby_res.status_code == 201
    baby_id = baby_res.json()["id"]
    assert 5.5 <= baby_res.json()["age_in_months"] <= 6.5

    # Log Feeding Routine
    routine_res = client.post(
        f"/api/v1/routines/{RoutineType.FEEDING.value}",
        headers=headers,
        json={
            "baby_id": baby_id,
            "routine_type": "feeding",
            "details": {"type": "formula", "amount_ml": 150},
            "notes": "Hepsini içti, gazı çıkarıldı."
        }
    )
    assert routine_res.status_code == 201
    assert routine_res.json()["details"]["amount_ml"] == 150

    # Log Sleep Routine
    sleep_start = datetime.now(timezone.utc) - timedelta(minutes=90)
    sleep_end = datetime.now(timezone.utc)
    sleep_routine_res = client.post(
        f"/api/v1/routines/{RoutineType.SLEEP.value}",
        headers=headers,
        json={
            "baby_id": baby_id,
            "routine_type": "sleep",
            "start_time": sleep_start.isoformat(),
            "end_time": sleep_end.isoformat(),
            "details": {"environment": "dark_room_pink_noise"},
            "notes": "90 dk derin uyku."
        }
    )
    assert sleep_routine_res.status_code == 201

    # List baby routines
    list_res = client.get(f"/api/v1/routines/baby/{baby_id}", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 2


def test_sounds_catalog(client):
    """Test retrieving sleep sounds library."""
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "sound_tester@mishil.app", "password": "password123"}
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/sounds/list", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 5
    assert "sounds" in data
    # Verify Pink Noise exists
    assert any(s["sound_type"] == "pink_noise_432hz" for s in data["sounds"])


def test_subscription_trial_and_webhook(client):
    """Test 3-day trial activation and RevenueCat webhook receiver."""
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "subscriber@mishil.app", "password": "password123"}
    )
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Start trial
    trial_res = client.post("/api/v1/subscription/start-trial", headers=headers, json={})
    assert trial_res.status_code == 200
    trial_data = trial_res.json()
    assert trial_data["status"] == SubscriptionStatus.TRIAL
    assert trial_data["is_active"] is True
    assert trial_data["days_left_in_trial"] == 3

    # RevenueCat Webhook (renewal event)
    webhook_res = client.post(
        "/api/v1/subscription/webhook",
        headers={"Authorization": "rc_webhook_secret_example_key"},
        json={
            "api_version": "1.0",
            "event": {
                "type": "INITIAL_PURCHASE",
                "app_user_id": "subscriber@mishil.app",
                "product_id": "mishil_yearly_premium",
                "original_transaction_id": "txn_123456789",
            }
        }
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["status"] == "success"

    # Status check after webhook
    status_res = client.get("/api/v1/subscription/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == SubscriptionStatus.ACTIVE
    assert status_res.json()["is_active"] is True
