"""API contract tests for the credential-free MapWork.ai backend."""

import sys
import unittest
from pathlib import Path


PROJECT_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIRECTORY))

from app import create_app  # noqa: E402
from config import Config  # noqa: E402


class MapWorkApiTest(unittest.TestCase):
    def setUp(self) -> None:
        application = create_app(Config(log_level="CRITICAL"))
        application.config.update(TESTING=True)
        self.client = application.test_client()

    def test_health_reports_demo_mode_without_credentials(self) -> None:
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "healthy")
        self.assertEqual(response.json["mode"], "demo")
        self.assertIn("X-Request-ID", response.headers)
        self.assertIn("X-Response-Time", response.headers)

    def test_scan_filters_and_ranks_sample_leads(self) -> None:
        response = self.client.post("/api/v1/scans", json={
            "area": "waterloo",
            "minimum_score": 80,
            "signals": ["discoloration"],
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json["summary"]["matches"], 2)
        self.assertEqual(
            [lead["opportunity_score"] for lead in response.json["data"]],
            [92, 84],
        )
        self.assertEqual(response.json["mode"], "simulation")

    def test_scan_rejects_unknown_area(self) -> None:
        response = self.client.post("/api/v1/scans", json={"area": "toronto"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"]["code"], "invalid_scan_request")

    def test_scan_rejects_invalid_signal(self) -> None:
        response = self.client.post("/api/v1/scans", json={"signals": ["cracked"]})

        self.assertEqual(response.status_code, 400)
        self.assertIn("unsupported signals", response.json["error"]["message"])

    def test_pagination_has_a_hard_limit(self) -> None:
        response = self.client.post("/api/v1/scans", json={"per_page": 101})

        self.assertEqual(response.status_code, 400)

    def test_database_status_is_safe_when_not_configured(self) -> None:
        response = self.client.get("/api/v1/database/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "not_configured")


if __name__ == "__main__":
    unittest.main()
