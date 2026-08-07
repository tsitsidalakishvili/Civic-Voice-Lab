import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from starlette.requests import Request

from deliberation.api.app.core import auth, auth_store
from deliberation.api.app.core.config import (
    DEFAULT_OIDC_PUBLIC_RULES,
    get_settings,
    validate_auth_startup,
)
from deliberation.api.app.core.field_masking import mask_response_payload
from deliberation.api.app.core.oidc import _return_to
from deliberation.api.app.investigation_ftm import (
    EntityResolutionReviewRequest,
    _stable_id,
    review_entity_resolution_candidate,
)
from deliberation.api.app.investigation_governance import publication_governance_blockers
from deliberation.api.app import main


def request(path="/due-diligence/cases/case-1", method="GET", headers=None):
    raw_headers = [
        (str(key).lower().encode("latin1"), str(value).encode("latin1"))
        for key, value in (headers or {}).items()
    ]
    value = Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": raw_headers,
            "query_string": b"",
            "scheme": "https",
            "server": ("api.example", 443),
            "client": ("127.0.0.1", 1234),
        }
    )
    value.state.request_id = "request-1"
    return value


class SecurityComplianceTests(unittest.TestCase):
    def setUp(self):
        self.settings = replace(
            get_settings(),
            session_secret="s" * 32,
            compliance_hash_key="h" * 32,
            frontend_origin="https://app.example",
            csrf_header_name="X-FS-CSRF",
        )

    def test_invalid_or_incomplete_oidc_configuration_fails_closed(self):
        invalid = replace(
            self.settings,
            auth_enabled=True,
            auth_mode="oidc",
            auth_emergency_bearer_gate=False,
            oidc_provider="google",
            oidc_issuer="",
            oidc_client_id="",
            oidc_client_secret="",
            oidc_redirect_uri="",
            oidc_google_hosted_domain="",
            oidc_allowed_emails_json="",
            cors_origins=("https://app.example",),
        )
        with self.assertRaises(RuntimeError):
            validate_auth_startup(invalid)

    def test_email_normalization_keeps_plus_and_dots(self):
        self.assertEqual(
            auth_store.normalize_exact_email(" User.Name+case@EXAMPLE.com "),
            "user.name+case@example.com",
        )

    def test_return_to_rejects_external_redirects(self):
        self.assertEqual(_return_to("/cases/1"), "/cases/1")
        for unsafe in ("https://evil.example", "//evil.example", "/ok\\evil"):
            with self.assertRaises(ValueError):
                _return_to(unsafe)

    def test_oidc_transaction_cannot_be_replayed(self):
        row = {
            "transactionId": "tx-1",
            "nonceHash": "nonce-hash",
            "pkceVerifierCiphertext": "cipher",
            "redirectUri": "https://api.example/auth/callback/google",
            "returnTo": "/",
        }
        with patch.object(auth_store, "_write", side_effect=[[row], []]), patch.object(
            auth_store, "decrypt_short_secret", return_value="verifier"
        ):
            first = auth_store.consume_oidc_transaction(self.settings, "state", "google")
            second = auth_store.consume_oidc_transaction(self.settings, "state", "google")
        self.assertEqual(first["pkceVerifier"], "verifier")
        self.assertIsNone(second)

    def test_csrf_requires_exact_origin_and_token(self):
        csrf_token = "csrf-token"
        session = {"csrfHash": auth_store.keyed_hash(self.settings, "csrf", csrf_token)}
        good = request(
            method="POST",
            headers={"Origin": "https://app.example", "X-FS-CSRF": csrf_token},
        )
        self.assertIsNone(auth._csrf_failure(good, session, self.settings))
        bad = request(
            method="POST",
            headers={"Origin": "https://evil.example", "X-FS-CSRF": csrf_token},
        )
        self.assertEqual(auth._csrf_failure(bad, session, self.settings).status_code, 403)

    def test_role_case_and_purpose_authorization_is_deny_by_default(self):
        current = replace(self.settings, purpose_enforcement_enabled=True)
        req = request(headers={"X-FS-Purpose-Id": "dd-investigation"})
        principal = {
            "roles": ["investigator"],
            "caseScopes": ["case-1"],
            "purposeScopes": ["dd-investigation"],
        }
        with patch.object(auth, "_purpose_is_active", return_value=True):
            self.assertIsNone(auth._authorize_oidc_request(req, principal, current))
        wrong_case = request(path="/due-diligence/cases/case-2", headers={"X-FS-Purpose-Id": "dd-investigation"})
        with patch.object(auth, "_purpose_is_active", return_value=True):
            self.assertEqual(auth._authorize_oidc_request(wrong_case, principal, current).status_code, 403)

    def test_oidc_public_route_inventory_is_exact_and_business_routes_are_private(self):
        current = replace(
            self.settings,
            auth_enabled=True,
            auth_mode="oidc",
            auth_emergency_bearer_gate=False,
            auth_public_rules=DEFAULT_OIDC_PUBLIC_RULES,
        )
        public_requests = (
            request(path="/health", method="GET"),
            request(path="/healthz", method="GET"),
            request(path="/platform/auth/status", method="GET"),
            request(path="/auth/login", method="GET"),
            request(path="/auth/callback/google", method="GET"),
            request(path="/auth/callback/entra", method="GET"),
            request(path="/platform/access/verify", method="POST"),
        )
        for public_request in public_requests:
            self.assertTrue(
                auth.is_public_request(public_request, current),
                f"expected public: {public_request.method} {public_request.url.path}",
            )
        protected_paths = (
            "/crm/people",
            "/data-hub/imports",
            "/due-diligence/cases/case-1",
            "/admin/diagnostics/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/crm/export",
            "/data-hub/search",
        )
        for path in protected_paths:
            self.assertFalse(auth.is_public_request(request(path=path), current), path)
        self.assertFalse(auth.is_public_request(request(path="/health", method="POST"), current))
        self.assertFalse(auth.is_public_request(request(path="/healthz", method="DELETE"), current))

    def test_public_health_is_minimal_and_detailed_health_is_admin_only(self):
        sensitive = {
            "ok": False,
            "error": "secret database detail",
            "target_source": "DELIBERATION_*",
            "target_uri": "neo4j+s://database.example",
            "target_database": "private-db",
        }
        with patch.object(main, "db_health", return_value=sensitive):
            public_payload = main.healthz()
            detailed_payload = main.detailed_health_diagnostics()
        self.assertEqual(public_payload, {"status": "degraded"})
        self.assertNotIn("error", public_payload)
        self.assertNotIn("target_uri", public_payload)
        self.assertEqual(detailed_payload["database"], sensitive)
        self.assertEqual(auth._required_roles("/admin/diagnostics/health", "GET"), {"admin"})

    def test_sensitive_serializer_omits_and_masks_without_approved_policy(self):
        payload = {
            "name": "Allowed",
            "email": "person@example.com",
            "personalId": "01010101010",
            "birthDate": "1980-01-01",
            "nested": {"phone": "+995555123456", "politicalViews": "example"},
        }
        result, access = mask_response_payload(
            payload, roles={"viewer"}, purpose_id="", is_export=False, policies={}
        )
        self.assertNotIn("personalId", result)
        self.assertNotIn("birthDate", result)
        self.assertEqual(result["email"], "***@example.com")
        self.assertEqual(result["nested"]["phone"], "***3456")
        self.assertTrue(access["omittedFields"])

    def test_name_only_resolution_acceptance_is_blocked(self):
        case_id = "case-1"
        left_id, right_id = "left", "right"
        candidate_id = _stable_id("resolution", case_id, left_id, right_id)
        candidate = {
            "candidateId": candidate_id,
            "left": {"id": left_id},
            "right": {"id": right_id},
            "signals": [{"type": "shared-normalized-name"}],
            "sharedValues": {},
            "conflicts": [],
            "evidenceIds": [],
        }
        with patch("deliberation.api.app.investigation_ftm._load_resolution_candidates", return_value=[candidate]):
            response = review_entity_resolution_candidate(
                request(),
                case_id,
                candidate_id,
                EntityResolutionReviewRequest(
                    leftEntityId=left_id,
                    rightEntityId=right_id,
                    decision="accepted",
                    rationale="Same displayed name",
                ),
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"]["code"], "NAME_ONLY_MATCH_REQUIRES_MORE_EVIDENCE")

    def test_publication_blockers_include_purpose_redress_and_approvals(self):
        with patch(
            "deliberation.api.app.investigation_governance._read",
            return_value=[{"purposeId": None, "openDisputes": 1, "openAppeals": 1, "decisions": []}],
        ):
            codes = {item["code"] for item in publication_governance_blockers("case-1")}
        self.assertEqual(
            codes,
            {"CASE_PURPOSE_REQUIRED", "OPEN_DISPUTES", "OPEN_APPEALS", "LEGAL_APPROVAL_REQUIRED", "EDITORIAL_APPROVAL_REQUIRED"},
        )

    def test_auth_audit_hashes_subject_and_request_metadata(self):
        captured = {}

        def write(_query, params):
            captured.update(params)
            return []

        with patch.object(auth_store, "_write", side_effect=write):
            auth_store.record_auth_audit(
                self.settings,
                "login_failed",
                outcome="denied",
                subject="provider-subject",
                ip_address="192.0.2.1",
                user_agent="test-agent",
            )
        serialized = json.dumps(captured)
        self.assertNotIn("provider-subject", serialized)
        self.assertNotIn("192.0.2.1", serialized)
        self.assertNotIn("test-agent", serialized)


if __name__ == "__main__":
    unittest.main()
