import json
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from joserfc import jwt
from joserfc.jwk import RSAKey
from starlette.requests import Request

from deliberation.api.app.core import auth, auth_store, oidc
from deliberation.api.app.core.config import (
    DEFAULT_OIDC_PUBLIC_RULES,
    GOOGLE_OIDC_ISSUER,
    get_settings,
    validate_auth_startup,
)


ORG_DOMAIN = "freedomsquare.ge"
SYNTHETIC_LOCAL = "__automated_auth_test_never_provision__"


def synthetic_email(local: str = SYNTHETIC_LOCAL) -> str:
    return f"{local}@{ORG_DOMAIN}"


def make_request(path="/auth/callback/google", method="GET", headers=None):
    value = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [
                (str(key).lower().encode("latin1"), str(item).encode("latin1"))
                for key, item in (headers or {}).items()
            ],
            "query_string": b"",
            "scheme": "https",
            "server": ("backend-service.onrender.com", 443),
            "client": ("192.0.2.10", 1234),
        }
    )
    value.state.request_id = "request-test"
    return value


class GoogleWorkspaceOidcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signing_key = RSAKey.generate_key(2048, auto_kid=True)
        cls.other_key = RSAKey.generate_key(2048, auto_kid=True)

    def setUp(self):
        frontend_origin = "https://frontend-project.vercel.app"
        self.settings = replace(
            get_settings(),
            auth_enabled=True,
            auth_mode="oidc",
            auth_emergency_bearer_gate=False,
            auth_token="",
            oidc_provider="google",
            oidc_issuer=GOOGLE_OIDC_ISSUER,
            oidc_client_id="synthetic-client-id.apps.googleusercontent.com",
            oidc_client_secret="synthetic-client-secret-placeholder",
            oidc_redirect_uri="https://backend-service.onrender.com/auth/callback/google",
            oidc_google_hosted_domain=ORG_DOMAIN,
            oidc_allowed_emails_json=json.dumps(
                [{"email": synthetic_email(), "roles": ["viewer"]}]
            ),
            frontend_origin=frontend_origin,
            cors_origins=(frontend_origin,),
            cors_origin_regex="",
            session_secret="s" * 48,
            compliance_hash_key="h" * 48,
            session_cookie_name="__Host-fs_session",
            session_cookie_secure=True,
            session_cookie_samesite="none",
            csrf_header_name="X-FS-CSRF",
            auth_public_rules=DEFAULT_OIDC_PUBLIC_RULES,
        )

    def token(self, **overrides):
        now = int(time.time())
        claims = {
            "iss": GOOGLE_OIDC_ISSUER,
            "aud": self.settings.oidc_client_id,
            "sub": "synthetic-google-subject",
            "email": synthetic_email(),
            "email_verified": True,
            "hd": ORG_DOMAIN,
            "nonce": "synthetic-nonce",
            "iat": now,
            "nbf": now - 1,
            "exp": now + 300,
        }
        claims.update(overrides)
        return jwt.encode(
            {"alg": "RS256", "kid": self.signing_key.kid},
            claims,
            self.signing_key,
            algorithms=["RS256"],
        )

    def validate(self, token=None):
        with patch.object(
            oidc,
            "_jwks",
            return_value={"keys": [self.signing_key.as_dict(private=False)]},
        ):
            return oidc._validate_id_token(
                self.settings,
                id_token=token or self.token(),
                metadata={"jwks_uri": "https://accounts.google.com/.well-known/jwks"},
                expected_nonce_hash=auth_store.keyed_hash(
                    self.settings, "oidc-nonce", "synthetic-nonce"
                ),
            )

    def test_confirmed_google_workspace_configuration_passes_startup(self):
        validate_auth_startup(self.settings)
        self.assertEqual(self.settings.oidc_provider, "google")
        self.assertEqual(self.settings.oidc_issuer, GOOGLE_OIDC_ISSUER)
        self.assertEqual(self.settings.oidc_google_hosted_domain, ORG_DOMAIN)
        self.assertFalse(self.settings.auth_emergency_bearer_gate)

    def test_signed_google_token_validates_signature_and_required_claims(self):
        identity = self.validate()
        self.assertEqual(identity["provider"], "google")
        self.assertEqual(identity["issuer"], GOOGLE_OIDC_ISSUER)
        self.assertEqual(identity["subject"], "synthetic-google-subject")

    def test_bad_signature_issuer_audience_or_authorized_party_is_rejected(self):
        with self.subTest("signature"):
            forged = jwt.encode(
                {"alg": "RS256", "kid": self.other_key.kid},
                {
                    "iss": GOOGLE_OIDC_ISSUER,
                    "aud": self.settings.oidc_client_id,
                    "sub": "synthetic-google-subject",
                    "email": synthetic_email(),
                    "email_verified": True,
                    "hd": ORG_DOMAIN,
                    "nonce": "synthetic-nonce",
                    "iat": int(time.time()),
                    "exp": int(time.time()) + 300,
                },
                self.other_key,
                algorithms=["RS256"],
            )
            with self.assertRaises(ValueError):
                self.validate(forged)
        for name, overrides in (
            ("issuer", {"iss": "https://issuer.example.invalid"}),
            ("audience", {"aud": "different-client"}),
            (
                "authorized-party",
                {"aud": [self.settings.oidc_client_id, "other-client"], "azp": "other-client"},
            ),
        ):
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    self.validate(self.token(**overrides))

    def test_email_verified_and_exact_hosted_domain_are_required(self):
        for name, overrides in (
            ("unverified", {"email_verified": False}),
            ("missing-hd", {"hd": None}),
            ("wrong-hd", {"hd": "other.example.invalid"}),
        ):
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    self.validate(self.token(**overrides))

    def test_non_allowlisted_and_alias_variants_do_not_match(self):
        for local in (
            "different-synthetic-identity",
            f"{SYNTHETIC_LOCAL}+alias",
            "automated.auth.test.never.provision",
        ):
            with self.subTest(local):
                with patch.object(auth_store, "_write") as write:
                    principal = auth_store.authorize_and_bind_allowlist(
                        self.settings,
                        email=synthetic_email(local),
                        provider="google",
                        issuer=GOOGLE_OIDC_ISSUER,
                        subject="synthetic-subject",
                    )
                self.assertIsNone(principal)
                write.assert_not_called()

    def test_allowlist_binding_is_immutable_for_issuer_and_subject(self):
        stored = {}

        def fake_write(_query, params):
            if stored and (
                stored["issuer"] != params["issuer"]
                or stored["subject"] != params["subject"]
            ):
                return []
            stored.update(
                {
                    "issuer": params["issuer"],
                    "subject": params["subject"],
                    "allowlistId": stored.get("allowlistId", params["allowlistId"]),
                }
            )
            return [
                {
                    "allowlistId": stored["allowlistId"],
                    "email": synthetic_email(),
                    "provider": "google",
                    "issuer": stored["issuer"],
                    "subject": stored["subject"],
                    "roles": ["viewer"],
                    "caseScopes": [],
                    "purposeScopes": [],
                    "version": 1,
                }
            ]

        with patch.object(auth_store, "_write", side_effect=fake_write):
            first = auth_store.authorize_and_bind_allowlist(
                self.settings,
                email=synthetic_email(),
                provider="google",
                issuer=GOOGLE_OIDC_ISSUER,
                subject="subject-one",
            )
            repeated = auth_store.authorize_and_bind_allowlist(
                self.settings,
                email=synthetic_email(),
                provider="google",
                issuer=GOOGLE_OIDC_ISSUER,
                subject="subject-one",
            )
            reassigned = auth_store.authorize_and_bind_allowlist(
                self.settings,
                email=synthetic_email(),
                provider="google",
                issuer=GOOGLE_OIDC_ISSUER,
                subject="subject-two",
            )
        self.assertIsNotNone(first)
        self.assertEqual(first["allowlistId"], repeated["allowlistId"])
        self.assertIsNone(reassigned)

    def test_session_expiry_and_revocation_fail_closed(self):
        now = datetime.now(timezone.utc)
        base = {
            "sessionIdHash": "hash",
            "issuedAt": (now - timedelta(minutes=2)).isoformat(),
            "lastSeenAt": (now - timedelta(minutes=1)).isoformat(),
            "idleExpiresAt": (now + timedelta(minutes=20)).isoformat(),
            "absoluteExpiresAt": (now + timedelta(hours=2)).isoformat(),
            "revokedAt": None,
            "sessionVersion": 1,
            "csrfHash": "csrf-hash",
            "csrfCiphertext": "cipher",
            "allowlistId": "allowlist-id",
            "email": synthetic_email(),
            "provider": "google",
            "issuer": GOOGLE_OIDC_ISSUER,
            "subject": "subject-one",
            "roles": ["viewer"],
            "caseScopes": [],
            "purposeScopes": [],
            "allowlistVersion": 1,
            "allowlistStatus": "active",
            "validFrom": None,
            "validUntil": None,
        }
        cases = (
            ("expired", {**base, "idleExpiresAt": (now - timedelta(seconds=1)).isoformat()}, "AUTH_SESSION_EXPIRED"),
            ("revoked", {**base, "revokedAt": now.isoformat()}, "AUTH_SESSION_REVOKED"),
            ("allowlist-revoked", {**base, "allowlistStatus": "revoked"}, "ACCESS_REVOKED"),
            ("version-revoked", {**base, "allowlistVersion": 2}, "AUTH_SESSION_REVOKED"),
        )
        for name, row, expected in cases:
            with self.subTest(name), patch.object(auth_store, "_read", return_value=[row]):
                session, code = auth_store.load_auth_session(
                    self.settings, "synthetic-session-token"
                )
            self.assertIsNone(session)
            self.assertEqual(code, expected)

    def test_callback_is_one_use_and_sets_host_only_cross_site_cookie(self):
        transaction = {
            "pkceVerifier": "verifier",
            "redirectUri": self.settings.oidc_redirect_uri,
            "nonceHash": "nonce-hash",
            "returnTo": "/workspace",
        }
        identity = {
            "issuer": GOOGLE_OIDC_ISSUER,
            "subject": "subject-one",
            "email": synthetic_email(),
            "provider": "google",
        }
        principal = {
            **identity,
            "allowlistId": "allowlist-id",
            "roles": ["viewer"],
            "caseScopes": [],
            "purposeScopes": [],
            "version": 1,
        }
        with patch.object(oidc, "get_settings", return_value=self.settings), patch.object(
            oidc, "consume_oidc_transaction",
            return_value=transaction,
        ) as consume_transaction, patch.object(oidc, "_metadata", return_value={"token_endpoint": "https://oauth2.googleapis.com/token", "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs"}), patch.object(
            oidc, "_exchange_code", return_value="signed-token"
        ), patch.object(oidc, "_validate_id_token", return_value=identity), patch.object(
            oidc, "authorize_and_bind_allowlist", return_value=principal
        ), patch.object(
            oidc,
            "create_auth_session",
            return_value=("synthetic-session-token", "csrf", {}),
        ), patch.object(oidc, "record_auth_audit") as audit, patch.object(
            oidc, "_login_failure_redirect", wraps=oidc._login_failure_redirect
        ) as failure_redirect:
            first = oidc.oidc_callback(
                make_request(), "google", code="code", state="state", error=""
            )
            consume_transaction.return_value = None
            replay = oidc.oidc_callback(
                make_request(), "google", code="code", state="state", error=""
            )
        self.assertEqual(consume_transaction.call_count, 2)
        self.assertEqual(failure_redirect.call_count, 1)
        self.assertGreaterEqual(audit.call_count, 2)
        cookie = first.headers.get("set-cookie", "")
        self.assertEqual(first.status_code, 303)
        self.assertIn(
            "__Host-fs_session=synthetic-session-token",
            cookie,
            msg=f"callback response was {first.status_code}: {dict(first.headers)}",
        )
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=none", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertEqual(replay.status_code, 303)
        self.assertIn("error=login_failed", replay.headers["location"])
        self.assertNotIn("set-cookie", replay.headers)

    def test_csrf_accepts_exact_origin_or_referer_only(self):
        token = "synthetic-csrf-token"
        session = {"csrfHash": auth_store.keyed_hash(self.settings, "csrf", token)}
        for headers in (
            {"Origin": self.settings.frontend_origin, "X-FS-CSRF": token},
            {"Referer": f"{self.settings.frontend_origin}/workspace", "X-FS-CSRF": token},
        ):
            self.assertIsNone(
                auth._csrf_failure(
                    make_request(path="/auth/logout", method="POST", headers=headers),
                    session,
                    self.settings,
                )
            )
        for headers in (
            {"Origin": "https://preview-project.vercel.app", "X-FS-CSRF": token},
            {"Referer": "https://other.example.invalid/path", "X-FS-CSRF": token},
            {"Origin": self.settings.frontend_origin},
        ):
            response = auth._csrf_failure(
                make_request(path="/auth/logout", method="POST", headers=headers),
                session,
                self.settings,
            )
            self.assertEqual(response.status_code, 403)

    def test_exact_cors_and_cross_site_cookie_validation(self):
        validate_auth_startup(self.settings)
        for invalid in (
            replace(self.settings, cors_origins=("*",)),
            replace(self.settings, cors_origins=("https://preview-project.vercel.app",)),
            replace(self.settings, session_cookie_samesite="lax"),
            replace(self.settings, frontend_origin="https://*.vercel.app", cors_origins=("https://*.vercel.app",)),
        ):
            with self.assertRaises(RuntimeError):
                validate_auth_startup(invalid)
        custom_frontend = "https://app.freedomsquare.ge"
        custom_domain = replace(
            self.settings,
            frontend_origin=custom_frontend,
            cors_origins=(custom_frontend,),
            oidc_redirect_uri="https://api.freedomsquare.ge/auth/callback/google",
            session_cookie_samesite="lax",
        )
        validate_auth_startup(custom_domain)

    def test_missing_crypto_dependency_fails_startup(self):
        real_find_spec = __import__("importlib.util", fromlist=["find_spec"]).find_spec

        def missing_joserfc(name):
            return None if name == "joserfc" else real_find_spec(name)

        with patch(
            "deliberation.api.app.core.config.importlib.util.find_spec",
            side_effect=missing_joserfc,
        ), self.assertRaises(RuntimeError):
            validate_auth_startup(self.settings)

    def test_business_and_signup_routes_remain_closed(self):
        for path in (
            "/crm/supporter-signup",
            "/crm/events/event-id/register",
            "/crm/people",
            "/data-hub/search",
            "/due-diligence/cases/case-id",
            "/docs",
            "/openapi.json",
            "/admin/diagnostics/health",
        ):
            self.assertFalse(auth.is_public_request(make_request(path=path), self.settings))

    def test_audit_parameters_never_contain_raw_identity_or_request_metadata(self):
        captured = {}

        def capture(_query, params):
            captured.update(params)
            return []

        with patch.object(auth_store, "_write", side_effect=capture):
            auth_store.record_auth_audit(
                self.settings,
                "login_failed",
                outcome="denied",
                subject="synthetic-subject-value",
                ip_address="192.0.2.10",
                user_agent="synthetic-user-agent",
            )
        raw = json.dumps(captured)
        self.assertNotIn("synthetic-subject-value", raw)
        self.assertNotIn("192.0.2.10", raw)
        self.assertNotIn("synthetic-user-agent", raw)
        self.assertNotIn(synthetic_email(), raw)


if __name__ == "__main__":
    unittest.main()
