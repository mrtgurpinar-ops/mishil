# -*- coding: utf-8 -*-
"""
Auth, Baby ve Routines endpoint entegrasyon testleri.
pytest fixtures (conftest.py'daki client ve db_session) kullanır.
In-memory SQLite ile tam test izolasyonu sağlanır.
"""
from datetime import datetime, timezone, timedelta
from app.models.enums import RoutineType, SubscriptionStatus


class TestAuthRegistrationAndLogin:
    """Kullanıcı kaydı, tekrar kayıt engeli ve giriş testleri."""

    def test_registration_returns_token(self, client):
        unique_email = f"parent_{int(datetime.now().timestamp())}@mishil.app"
        res = client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "securepassword", "full_name": "Canan Dağ"}
        )
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["email"] == unique_email
        assert data["subscription_status"] == SubscriptionStatus.TRIAL.value

    def test_duplicate_registration_fails(self, client):
        unique_email = f"dup_{int(datetime.now().timestamp())}@mishil.app"
        client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "securepassword"}
        )
        dup_res = client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "anotherpassword"}
        )
        assert dup_res.status_code == 400

    def test_login_with_valid_credentials(self, client):
        unique_email = f"login_{int(datetime.now().timestamp())}@mishil.app"
        client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "securepassword"}
        )
        login_res = client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "securepassword"}
        )
        assert login_res.status_code == 200
        assert "access_token" in login_res.json()

    def test_login_with_wrong_password_fails(self, client):
        unique_email = f"wrong_{int(datetime.now().timestamp())}@mishil.app"
        client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "correctpassword"}
        )
        res = client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "wrongpassword"}
        )
        assert res.status_code == 401

    def test_get_profile_requires_auth(self, client):
        res = client.get("/api/v1/auth/me")
        assert res.status_code == 401

    def test_get_profile_returns_user(self, client):
        unique_email = f"profile_{int(datetime.now().timestamp())}@mishil.app"
        reg = client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "securepassword"}
        )
        token = reg.json()["access_token"]
        me_res = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert me_res.status_code == 200
        assert me_res.json()["email"] == unique_email


class TestBabyAndRoutines:
    """Bebek profili oluşturma, wake window ve rutin günlüğü testleri."""

    def _register_and_get_token(self, client) -> str:
        unique_email = f"baby_{int(datetime.now().timestamp())}@mishil.app"
        reg = client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "password123"}
        )
        return reg.json()["access_token"]

    def test_baby_creation(self, client):
        token = self._register_and_get_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
        baby_res = client.post(
            "/api/v1/auth/babies",
            headers=headers,
            json={"name": "Mavi", "birth_date": six_months_ago.isoformat(), "gender": "female"}
        )
        assert baby_res.status_code == 201
        data = baby_res.json()
        assert data["name"] == "Mavi"
        assert 5.5 <= data["age_in_months"] <= 6.5

    def test_routine_feeding_log(self, client):
        token = self._register_and_get_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
        baby_res = client.post(
            "/api/v1/auth/babies",
            headers=headers,
            json={"name": "Emir", "birth_date": six_months_ago.isoformat()}
        )
        baby_id = baby_res.json()["id"]

        routine_res = client.post(
            "/api/v1/routines/feeding",
            headers=headers,
            json={
                "baby_id": baby_id,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "details": {"amount_ml": 150, "type": "breast_milk"}
            }
        )
        assert routine_res.status_code == 201
        assert routine_res.json()["routine_type"] == RoutineType.FEEDING.value

    def test_wake_window_calculate_by_baby_id(self, client):
        token = self._register_and_get_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
        baby_res = client.post(
            "/api/v1/auth/babies",
            headers=headers,
            json={"name": "Leyla", "birth_date": six_months_ago.isoformat()}
        )
        baby_id = baby_res.json()["id"]

        ww_res = client.get(
            f"/api/v1/wake-window/calculate/baby/{baby_id}",
            headers=headers
        )
        assert ww_res.status_code == 200
        # 6 months → bracket 6-9 months → 150 min base wake window
        assert ww_res.json()["base_wake_window_minutes"] == 150

    def test_get_baby_routines_log(self, client):
        token = self._register_and_get_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
        baby_res = client.post(
            "/api/v1/auth/babies",
            headers=headers,
            json={"name": "Ada", "birth_date": six_months_ago.isoformat()}
        )
        baby_id = baby_res.json()["id"]
        client.post(
            "/api/v1/routines/diaper",
            headers=headers,
            json={"baby_id": baby_id, "details": {"type": "wet"}}
        )
        logs_res = client.get(
            f"/api/v1/routines/logs/baby/{baby_id}",
            headers=headers
        )
        assert logs_res.status_code == 200
        assert len(logs_res.json()) >= 1

    def test_health_endpoint(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
