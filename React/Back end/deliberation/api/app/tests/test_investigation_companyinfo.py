import json
import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from deliberation.api.app.investigation_companyinfo import (
    CompanyInfoAdapterError,
    CompanyInfoEnrichmentRequest,
    NaprVerificationRequest,
    _companyinfo_get,
    build_companyinfo_bundle,
    normalize_companyinfo_payload,
)
from deliberation.api.app.investigation_sources import source_adapter_catalog


class TestCompanyInfoEnrichment(unittest.TestCase):
    def _payload(self):
        return {
            "id": 771,
            "identificationCode": "123456789",
            "name": "Example Georgia LLC",
            "legalForm": "Limited Liability Company",
            "status": "Active",
            "registrationDate": "2019-04-03",
            "registrationNumber": "123456789",
            "address": "Tbilisi, Example Street 1",
            "email": "office@example.test",
            "updatedAt": "2026-07-15T00:00:00Z",
            "directors": [
                {
                    "id": 11,
                    "name": "Current Director",
                    "personalNumber": "01010101010",
                    "startDate": "2024-01-01",
                    "isCurrent": True,
                    "documentUrl": "https://companyinfo.ge/documents/director.pdf",
                }
            ],
            "formerDirectors": [
                {
                    "id": 12,
                    "name": "Former Director",
                    "personalNumber": "02020202020",
                    "startDate": "2020-01-01",
                    "endDate": "2023-12-31",
                }
            ],
            "shareholders": [
                {
                    "id": 13,
                    "name": "Current Shareholder",
                    "personalNumber": "03030303030",
                    "sharePercentage": "75%",
                    "isCurrent": True,
                }
            ],
            "relatedCompanies": [
                {
                    "id": 990,
                    "name": "Related Holdings LLC",
                    "identificationCode": "987654321",
                }
            ],
            "politicalDonations": [{"year": 2024, "amount": 5000}],
            "procurementBlacklist": [],
            "miningLicenses": None,
        }

    def test_request_contract_rejects_non_company_code(self):
        with self.assertRaises(ValidationError):
            CompanyInfoEnrichmentRequest.model_validate(
                {"identificationCode": "company-name"}
            )

    def test_normalization_preserves_history_and_indicator_states(self):
        normalized = normalize_companyinfo_payload(self._payload(), "123456789")
        company = normalized["company"]
        self.assertEqual(company["identificationCode"], "123456789")
        self.assertEqual(company["legalForm"], "Limited Liability Company")
        relationships = normalized["relationships"]
        current_director = next(
            row
            for row in relationships
            if row["roleType"] == "director" and row["current"]
        )
        former_director = next(
            row
            for row in relationships
            if row["roleType"] == "director" and not row["current"]
        )
        shareholder = next(
            row for row in relationships if row["roleType"] == "shareholder"
        )
        self.assertEqual(current_director["startDate"], "2024-01-01")
        self.assertEqual(former_director["endDate"], "2023-12-31")
        self.assertEqual(shareholder["sharePercentage"], 75.0)
        indicators = {row["indicatorId"]: row for row in normalized["indicators"]}
        self.assertEqual(indicators["political-donations"]["valueState"], "present")
        self.assertEqual(indicators["procurement-blacklist"]["valueState"], "absent")
        self.assertEqual(indicators["construction-permits"]["status"], "unknown")

    @patch.dict(os.environ, {"FS_DD_ID_HASH_KEY": "unit-test-key"})
    def test_personal_ids_are_only_used_as_keyed_internal_identity_material(self):
        normalized = normalize_companyinfo_payload(self._payload(), "123456789")
        people = [
            row
            for row in normalized["relationships"]
            if row["roleType"] in {"director", "shareholder"}
        ]
        self.assertTrue(all(row["personalIdentityHash"].startswith("hmac-sha256:") for row in people))
        bundle, _ = build_companyinfo_bundle(
            case_id="case-1",
            root_entity_id="root-1",
            normalized=normalized,
            payload_hash="hash-1",
            fetched_at="2026-08-07T00:00:00+00:00",
        )
        serialized = json.dumps(bundle)
        self.assertNotIn("01010101010", serialized)
        self.assertNotIn("02020202020", serialized)
        self.assertNotIn("03030303030", serialized)
        self.assertNotIn("hmac-sha256", serialized)
        person_nodes = [row for row in bundle["entities"] if row["entityType"] == "Person"]
        self.assertTrue(person_nodes)
        self.assertTrue(all(row["personalIdentifiersExposed"] is False for row in person_nodes))

    def test_bundle_is_idempotent_and_keeps_secondary_source_caveat(self):
        normalized = normalize_companyinfo_payload(self._payload(), "123456789")
        kwargs = {
            "case_id": "case-1",
            "root_entity_id": "root-1",
            "normalized": normalized,
            "payload_hash": "hash-1",
            "fetched_at": "2026-08-07T00:00:00+00:00",
        }
        first, first_metrics = build_companyinfo_bundle(**kwargs)
        second, second_metrics = build_companyinfo_bundle(**kwargs)
        self.assertEqual(
            {row["entityId"] for row in first["entities"]},
            {row["entityId"] for row in second["entities"]},
        )
        self.assertEqual(
            {row["relationshipId"] for row in first["relationships"]},
            {row["relationshipId"] for row in second["relationships"]},
        )
        self.assertEqual(first_metrics, second_metrics)
        company = next(
            row
            for row in first["entities"]
            if row.get("identificationCode") == "123456789"
        )
        self.assertEqual(company["sourceAuthorityLevel"], "secondary")
        labels = {row["relationshipType"] for row in first["relationships"]}
        self.assertIn("Director of", labels)
        self.assertIn("Former director of", labels)
        self.assertIn("Shareholder of", labels)
        self.assertIn("Related company", labels)
        self.assertTrue(
            all(
                row["verificationStatus"] == "source-stated"
                for row in first["relationships"]
            )
        )

    def test_napr_verification_accepts_only_official_host(self):
        with self.assertRaises(ValidationError):
            NaprVerificationRequest.model_validate(
                {
                    "status": "verified",
                    "officialUrl": "https://example.test/fake-registry",
                    "verifiedBy": "Analyst",
                    "notes": "Checked the registry record.",
                }
            )
        valid = NaprVerificationRequest.model_validate(
            {
                "status": "mismatch",
                "officialUrl": "https://enreg.reestri.gov.ge/main.php?m=new_index",
                "verifiedBy": "Analyst",
                "notes": "The legal form differs.",
                "comparedFields": {"legalForm": "mismatch", "name": "match"},
            }
        )
        self.assertEqual(valid.status, "mismatch")

    @patch.dict(
        os.environ,
        {"FS_COMPANYINFO_ENABLED": "0", "FS_COMPANYINFO_PERMISSION_ACKNOWLEDGED": "0"},
    )
    def test_undocumented_companyinfo_interface_is_disabled_by_default(self):
        with self.assertRaises(CompanyInfoAdapterError) as raised:
            _companyinfo_get("getcorporation/123456789")
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.error_type, "permission-required")

    @patch.dict(
        os.environ,
        {"FS_COMPANYINFO_ENABLED": "0", "FS_COMPANYINFO_PERMISSION_ACKNOWLEDGED": "0"},
    )
    def test_generic_source_contract_has_precedence_governance_and_kill_switches(self):
        adapters = {row["adapterId"]: row for row in source_adapter_catalog()}
        self.assertIn("companyinfo-ge", adapters)
        self.assertIn("gleif", adapters)
        self.assertIn("official-sanctions", adapters)
        companyinfo = adapters["companyinfo-ge"]
        self.assertEqual(companyinfo["authorityTier"], 4)
        self.assertEqual(companyinfo["governance"]["killSwitch"], "FS_COMPANYINFO_ENABLED")
        self.assertFalse(companyinfo["ingestion"]["enabled"])
        self.assertTrue(companyinfo["artifactPolicy"]["immutableSnapshot"])
        self.assertEqual(companyinfo["artifactPolicy"]["contentHash"], "sha256")


if __name__ == "__main__":
    unittest.main()
