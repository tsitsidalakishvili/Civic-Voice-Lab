import base64
import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request

from deliberation.api.app.core import auth_store
from deliberation.api.app.core.config import get_settings, validate_auth_startup
from deliberation.api.app.core.auth_store import (
    authorize_password_user,
    create_auth_session,
    load_auth_session,
    revoke_auth_session,
)
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

    def test_password_session_falls_back_when_graph_is_unavailable(self):
        with patch.dict(os.environ, self.env, clear=True), patch(
            "deliberation.api.app.core.auth_store._write",
            side_effect=RuntimeError("synthetic graph outage"),
        ), patch(
            "deliberation.api.app.core.auth_store._read",
            side_effect=RuntimeError("synthetic graph outage"),
        ):
            get_settings.cache_clear()
            settings = get_settings()
            principal = authorize_password_user(settings, "analyst@example.invalid")
            raw_session, csrf_token, _ = create_auth_session(settings, principal)
            loaded, reason = load_auth_session(settings, raw_session)

            self.assertEqual(reason, "")
            self.assertEqual(loaded["email"], "analyst@example.invalid")
            self.assertEqual(loaded["csrfToken"], csrf_token)
            self.assertTrue(revoke_auth_session(loaded["sessionIdHash"]))
            revoked, reason = load_auth_session(settings, raw_session)
            self.assertIsNone(revoked)
            self.assertEqual(reason, "AUTH_SESSION_REVOKED")

    def test_shared_fallback_session_honors_credential_expiry_and_is_bounded(self):
        with patch.dict(os.environ, self.env, clear=True), patch(
            "deliberation.api.app.core.auth_store._write",
            side_effect=RuntimeError("synthetic graph outage"),
        ), patch(
            "deliberation.api.app.core.auth_store._read",
            side_effect=RuntimeError("synthetic graph outage"),
        ), patch.object(auth_store, "_FALLBACK_SESSION_LIMIT", 2):
            get_settings.cache_clear()
            settings = get_settings()
            principal = {
                "allowlistId": "synthetic-shared",
                "email": "",
                "provider": "password",
                "issuer": "fs:shared-credential",
                "subject": "synthetic-subject",
                "roles": ["admin"],
                "caseScopes": ["*"],
                "purposeScopes": ["*"],
                "version": 1,
                "validUntil": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            }
            raw_session, _, _ = create_auth_session(settings, principal)
            loaded, reason = load_auth_session(settings, raw_session)
            self.assertIsNone(loaded)
            self.assertEqual(reason, "ACCESS_REVOKED")

            principal["validUntil"] = (
                datetime.now(timezone.utc) + timedelta(days=1)
            ).isoformat()
            sessions = [create_auth_session(settings, principal)[0] for _ in range(3)]
            oldest, reason = load_auth_session(settings, sessions[0])
            self.assertIsNone(oldest)
            self.assertEqual(reason, "AUTH_SESSION_INVALID")
            self.assertLessEqual(len(auth_store._fallback_sessions), 2)


if __name__ == "__main__":
    unittest.main()
