"""Safe, non-destructive smoke checks. Requires project dependencies installed."""
import unittest
from app import app


class SecuritySmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_register_page_loads(self):
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)

    def test_admin_prefix_alone_is_not_authorization(self):
        response = self.client.post("/register", data={
            "name": "Security Test",
            "email": "security-test-admin@example.invalid",
            "password": "long-test-password",
            "confirm_password": "long-test-password",
            "role": "admin",
            "admin_code": "AD001",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("restricted", response.headers.get("Location", "").lower())

    def test_department_prefix_alone_is_not_authorization(self):
        response = self.client.post("/register", data={
            "name": "Security Test",
            "email": "security-test-dept@example.invalid",
            "password": "long-test-password",
            "confirm_password": "long-test-password",
            "role": "department",
            "department_name": "Roads",
            "department_code": "DP1001",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("restricted", response.headers.get("Location", "").lower())

    def test_status_update_requires_login(self):
        response = self.client.post("/api/complaints/1/status", json={"status": "Resolved"})
        self.assertEqual(response.status_code, 401)

    def test_ai_analysis_requires_login(self):
        response = self.client.post("/api/ai/analyze-complaint", json={"title": "test"})
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
