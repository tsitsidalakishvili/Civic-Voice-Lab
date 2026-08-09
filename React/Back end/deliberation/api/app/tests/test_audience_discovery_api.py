import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from deliberation.api.app.core.config import get_settings
from deliberation.api.app.main import app


class TestAudienceDiscoveryAPI(unittest.TestCase):
    def setUp(self):
        # Settings are read per request through an lru_cache, so the suite must
        # pin the auth env instead of inheriting a developer's .env files.
        self.env = {"FS_AUTH_ENABLED": "0", "FS_AUTH_MODE": "bearer"}

    def tearDown(self):
        get_settings.cache_clear()

    def test_start_analysis(self):
        with patch.dict(os.environ, self.env):
            get_settings.cache_clear()
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
