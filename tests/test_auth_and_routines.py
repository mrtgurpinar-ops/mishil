# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.db.base import Base, engine
from app.models.enums import RoutineType, SubscriptionStatus


class TestAuthAndRoutines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    def setUp(self):
        self.client = TestClient(app)

    def test_auth_registration_and_login(self):
        """Test user registration, duplicate prevention, and login."""
        unique_email = f"parent_{int(datetime.now().timestamp())}@mishil.app"
        # Register
        res = self.client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "securepassword", "full_name": "Canan Dağ"}
        )
        self.assertEqual(res.status_code, 201)
        token_data = res.json()
        self.assertIn("access_token", token_data)
        token = token_data["access_token"]

        # Duplicate register should fail
        dup_res = self.client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "anotherpassword"}
        )
        self.assertEqual(dup_res.status_code, 400)

        # Login
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"email": unique_email, "password": "securepassword"}
        )
        self.assertEqual(login_res.status_code, 200)
        self.assertIn("access_token", login_res.json())

        # Get profile
        me_res = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_res.status_code, 200)
        self.assertEqual(me_res.json()["email"], unique_email)

    def test_baby_creation_and_routines(self):
        """Test baby registration, wake window calculation by baby_id, and routine logging."""
        unique_email = f"baby_tester_{int(datetime.now().timestamp())}@mishil.app"
        reg = self.client.post(
            "/api/v1/auth/register",
            json={"email": unique_email, "password": "password123"}
        )
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create baby (born 6 months ago)
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=182)
        baby_res = self.client.post(
            "/api/v1/auth/babies",
            headers=headers,
            json={"name": "Mavi", "birth_date": six_months_ago.isoformat(), "gender": "female"}
        )
        self.assertEqual(baby_res.status_code, 201)
        baby_id = baby_res.json()["id"]
        self.assertTrue(5.5 <= baby_res.json()["age_in_months"] <= 6.5)

        # Log Feeding Routine
        routine_res = self.client.post(
            "/api/v1/routines/feeding",
            headers=headers,
            json={
                "baby_id": baby_id,
                "start_time": datetime.now(timezone.utc).isoformat(),
                "details": {"amount_ml": 150, "type": "breast_milk"}
            }
        )
        self.assertEqual(routine_res.status_code, 201)

        # Get baby's dynamic wake window
        ww_res = self.client.get(f"/api/v1/wake-window/calculate/baby/{baby_id}", headers=headers)
        self.assertEqual(ww_res.status_code, 200)
        self.assertEqual(ww_res.json()["base_wake_window_minutes"], 150)


if __name__ == "__main__":
    unittest.main()
