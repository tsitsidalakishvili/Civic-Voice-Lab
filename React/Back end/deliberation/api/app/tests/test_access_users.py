import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from deliberation.api.app.core.access_users import (
    authenticate_access_user,
    hash_password,
    load_access_users,
)
from deliberation.api.app.core.config import get_settings, validate_auth_startup
from deliberation.api.app.core.oidc import PasswordLoginIn, password_login


def request(origin: str = "https://frontend.example.invalid") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"origin", origin.encode())],
            "client": ("127.0.0.1", 1234),
            "query_string": b"",
            "server": ("api.example.invalid", 443),
            "scheme": "https",
        }
    )


class AccessUserFileTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "access_users.json"
        self.password = "synthetic correct horse battery staple"
        self.path.write_text(
            json.dumps(
                [
                    {
                        "email": "partner@example.org",
                        "password_hash": hash_password(self.password),
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.env = {
            "FS_AUTH_ENABLED": "1",
            "FS_AUTH_MODE": "password",
            "FS_ACCESS_USERS_FILE": str(self.path),
            "FS_SESSION_SECRET": "s" * 48,
            "FS_COMPLIANCE_HASH_KEY": "c" * 48,
            "FS_FRONTEND_ORIGIN": "https://frontend.example.invalid",
            "CORS_ORIGINS": "https://frontend.example.invalid",
            "FS_SESSION_COOKIE_NAME": "__Host-fs_session",
            "FS_SESSION_COOKIE_SECURE": "true",
            "FS_SESSION_COOKIE_SAMESITE": "none",
        }

    def tearDown(self):
        get_settings.cache_clear()
        self.tempdir.cleanup()

    def test_exact_email_and_password_are_required(self):
        self.assertEqual(
            authenticate_access_user(
                str(self.path), "PARTNER@example.org", self.password
            ),
            "partner@example.org",
        )
        self.assertIsNone(
            authenticate_access_user(str(self.path), "other@example.org", self.password)
        )
        self.assertIsNone(
            authenticate_access_user(str(self.path), "partner@example.org", "wrong")
        )

    def test_duplicate_email_is_rejected(self):
        entry = json.loads(self.path.read_text(encoding="utf-8"))[0]
        self.path.write_text(json.dumps([entry, entry]), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_access_users(str(self.path))

    def test_file_mode_validates_at_startup(self):
        with patch.dict(os.environ, self.env, clear=True):
            get_settings.cache_clear()
            validate_auth_startup(get_settings())

    def test_valid_file_user_creates_secure_session(self):
        principal = {
            "allowlistId": "synthetic-id",
            "email": "partner@example.org",
            "provider": "password",
            "issuer": "fs:access-users-file",
            "subject": "hashed-subject",
            "roles": ["admin"],
            "caseScopes": ["*"],
            "purposeScopes": ["*"],
            "version": 1,
        }
        with patch.dict(os.environ, self.env, clear=True), patch(
            "deliberation.api.app.core.oidc.authorize_password_user",
            return_value=principal,
        ), patch(
            "deliberation.api.app.core.oidc.create_auth_session",
            return_value=("raw-session", "csrf", {}),
        ), patch("deliberation.api.app.core.oidc.record_auth_audit"):
            get_settings.cache_clear()
            response = password_login(
                request(),
                PasswordLoginIn(
                    username="partner@example.org", password=self.password
                ),
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            self.assertIn("Secure", response.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
