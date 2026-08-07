import base64
import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from deliberation.api.app.core.config import get_settings, validate_auth_startup
from deliberation.api.app.core.oidc import PasswordLoginIn, password_login


def password_hash(password: str) -> str:
    salt = b"synthetic-test-salt-32-bytes!!"
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip("=")
    return f"pbkdf2_sha256$600000${encode(salt)}${encode(derived)}"


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


class PasswordAuthTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "FS_AUTH_ENABLED": "1",
            "FS_AUTH_MODE": "password",
            "FS_SHARED_USERNAME": "temporary-staff",
            "FS_SHARED_PASSWORD_HASH": password_hash("correct horse battery staple"),
            "FS_SHARED_CREDENTIAL_EXPIRES_AT": (
                datetime.now(timezone.utc) + timedelta(days=60)
            ).isoformat(),
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

    def test_password_mode_validates(self):
        with patch.dict(os.environ, self.env, clear=True):
            get_settings.cache_clear()
            validate_auth_startup(get_settings())

    def test_cors_is_outermost_for_fail_closed_responses(self):
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("app.add_middleware(OptionalAuthMiddleware)"),
            source.index("CORSMiddleware,"),
        )

    def test_wrong_origin_is_rejected(self):
        with patch.dict(os.environ, self.env, clear=True):
            get_settings.cache_clear()
            response = password_login(
                request("https://evil.example.invalid"),
                PasswordLoginIn(username="temporary-staff", password="correct horse battery staple"),
            )
            self.assertEqual(response.status_code, 403)

    def test_invalid_credentials_are_generic(self):
        with patch.dict(os.environ, self.env, clear=True), patch(
            "deliberation.api.app.core.oidc.record_auth_audit"
        ):
            get_settings.cache_clear()
            response = password_login(
                request(), PasswordLoginIn(username="wrong", password="wrong")
            )
            self.assertEqual(response.status_code, 401)
            self.assertNotIn(b"temporary-staff", response.body)

    def test_valid_credentials_create_secure_session(self):
        principal = {
            "allowlistId": "synthetic-id",
            "provider": "password",
            "issuer": "fs:shared-credential",
            "subject": "hashed-subject",
            "roles": ["admin"],
            "caseScopes": ["*"],
            "purposeScopes": ["*"],
            "version": 1,
        }
        with patch.dict(os.environ, self.env, clear=True), patch(
            "deliberation.api.app.core.oidc.authorize_shared_credential",
            return_value=principal,
        ), patch(
            "deliberation.api.app.core.oidc.create_auth_session",
            return_value=("raw-session", "csrf", {}),
        ), patch("deliberation.api.app.core.oidc.record_auth_audit"):
            get_settings.cache_clear()
            response = password_login(
                request(),
                PasswordLoginIn(
                    username="temporary-staff",
                    password="correct horse battery staple",
                ),
            )
            self.assertEqual(response.status_code, 200)
            cookie = response.headers["set-cookie"]
            self.assertIn("HttpOnly", cookie)
            self.assertIn("Secure", cookie)
            self.assertIn("SameSite=none", cookie)


if __name__ == "__main__":
    unittest.main()
