import unittest
from unittest.mock import patch

from deliberation.api.app.investigation_ftm import (
    InvestigationPathQueryRequest,
    _enumerate_paths,
    _normalize_name,
    _projection_rows,
)
from deliberation.api.app.investigation_reuse import (
    toolkit_capabilities,
    validate_ftm_entity,
)


class TestInvestigationFollowTheMoney(unittest.TestCase):
    def test_toolkit_validates_ftm_shape_and_reports_runtime(self):
        entity, warnings = validate_ftm_entity(
            {
                "id": "payment-1",
                "schema": "Payment",
                "properties": {
                    "payer": ["company-1"],
                    "beneficiary": ["company-2"],
                    "amount": [12500],
                    "currency": ["USD"],
                },
            }
        )
        self.assertEqual(entity["schema"], "Payment")
        self.assertEqual(entity["properties"]["amount"], ["12500"])
        self.assertEqual(warnings, [])
        capabilities = toolkit_capabilities()
        self.assertTrue(capabilities["features"]["nativeFtmImport"])
        self.assertTrue(capabilities["features"]["humanResolutionRequired"])

    def test_projection_preserves_names_and_statement_provenance(self):
        bundle = {
            "caseId": "case-1",
            "entities": [
                {
                    "entityId": "person-1",
                    "name": "Jane Doe",
                    "aliases": ["J. Doe"],
                    "entityType": "Person",
                    "entityRole": "Public official",
                    "birthYear": "1980",
                },
                {
                    "entityId": "screening-1",
                    "name": "Jane Doe",
                    "entityType": "Screening record",
                },
            ],
            "relationships": [
                {
                    "relationshipId": "link-1",
                    "fromEntityId": "person-1",
                    "toEntityId": "screening-1",
                    "relationshipType": "Candidate screening match",
                    "confidence": 0.72,
                    "verificationStatus": "candidate-match",
                    "details": "Identity is unresolved.",
                    "evidenceIds": ["evidence-1"],
                }
            ],
            "evidence": [
                {
                    "evidenceId": "evidence-1",
                    "sourceId": "source-1",
                    "sourceUrl": "https://example.test/record",
                }
            ],
        }
        statements, names = _projection_rows(bundle)
        self.assertEqual(_normalize_name("J. DOE"), "j doe")
        self.assertEqual(
            {row["normalizedName"] for row in names}, {"jane doe", "j doe"}
        )
        relationship_statements = [
            row for row in statements if row["relationshipId"] == "link-1"
        ]
        self.assertTrue(relationship_statements)
        self.assertTrue(
            all(row["assertionKind"] == "hypothesis" for row in relationship_statements)
        )
        self.assertTrue(
            all(row["evidenceId"] == "evidence-1" for row in relationship_statements)
        )
        birth_statement = next(
            row for row in statements if row["predicate"] == "Person:birthDate"
        )
        self.assertEqual(birth_statement["value"], "1980")
        self.assertEqual(birth_statement["sourceId"], "source-1")

    @patch(
        "deliberation.api.app.investigation_ftm._path_statement_ids",
        return_value={"family": ["s1"], "contract": ["s2"]},
    )
    def test_path_query_returns_evidence_and_statement_lineage(self, _statement_ids):
        graph = {
            "caseId": "case-1",
            "nodes": [
                {"id": "official", "label": "Official", "type": "Person", "isRoot": True},
                {"id": "relative", "label": "Relative", "type": "Person", "isRoot": False},
                {"id": "contract-node", "label": "Contract", "type": "Contract", "isRoot": False},
            ],
            "relationships": [
                {
                    "id": "family",
                    "source": "official",
                    "target": "relative",
                    "label": "Family: spouse",
                    "confidence": 0.98,
                    "verificationStatus": "source-stated",
                    "evidenceIds": ["e1"],
                },
                {
                    "id": "contract",
                    "source": "relative",
                    "target": "contract-node",
                    "label": "Party to declared contract",
                    "confidence": 0.91,
                    "verificationStatus": "source-stated",
                    "evidenceIds": ["e2"],
                },
            ],
        }
        paths, warnings, truncated = _enumerate_paths(
            graph,
            "official-relative-contract",
            InvestigationPathQueryRequest(maxDepth=4, limit=10),
        )
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0]["nodeIds"], ["official", "relative", "contract-node"])
        self.assertEqual(paths[0]["statementIds"], ["s1", "s2"])
        self.assertEqual(paths[0]["evidenceIds"], ["e1", "e2"])
        self.assertEqual(paths[0]["verificationStatus"], "source-stated")
        self.assertEqual(warnings, [])
        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()
