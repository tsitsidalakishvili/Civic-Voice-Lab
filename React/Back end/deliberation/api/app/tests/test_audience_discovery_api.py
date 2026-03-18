import unittest

from fastapi.testclient import TestClient

from deliberation.api.app.main import app


class TestAudienceDiscoveryAPI(unittest.TestCase):
    def test_start_analysis(self):
        client = TestClient(app)
        response = client.post(
            "/audience-discovery/analysis/start",
            json={"url": "https://example.com", "description": "Test"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("runId", payload)
        self.assertIn("status", payload)


if __name__ == "__main__":
    unittest.main()
