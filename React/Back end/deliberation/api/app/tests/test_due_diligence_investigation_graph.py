import unittest
from unittest.mock import patch

from fastapi import HTTPException

from deliberation.api.app.routes_due_diligence import (
    FollowTheMoneyGraphImportRequest,
    InvestigationGraphImportRequest,
    _build_investigation_graph_bundle,
    _build_investigation_insights,
    import_due_diligence_investigation_graph,
    import_followthemoney_investigation_graph,
)


class TestDueDiligenceInvestigationGraph(unittest.TestCase):
    def setUp(self):
        self.case = {
            "caseId": "case-1",
            "subject": "Public Official",
            "subjectEnglish": "Public Official",
            "subjectGeorgian": "",
            "subjectType": "Person",
        }
        declaration = {
            "id": "decl-2026",
            "name": "Public Official",
            "declarationSubmitDate": "2026-02-01",
            "sourceUrl": "https://registry.example/declarations/decl-2026",
            "raw": {
                "Id": "decl-2026",
                "FirstName": "Public",
                "LastName": "Official",
                "FamilyMembers": [
                    {
                        "FirstName": "Related",
                        "LastName": "Person",
                        "BirthDate": "04.05.1986",
                        "Relationship": "Sibling",
                    }
                ],
                "Properties": [
                    {
                        "OwnerFirstName": "Related",
                        "OwnerLatsName": "Person",
                        "PropertyType": "Apartment",
                        "Address": "Example Street",
                        "Area": 90,
                        "Share": 100,
                    }
                ],
                "Jobs": [
                    {
                        "OwnerFirstName": "Public",
                        "OwnerLatsName": "Official",
                        "Organisation": "Public Agency",
                        "Position": "Director",
                        "StartDate": "2025-01-01",
                    }
                ],
                "Contracts": [],
                "Enterprice": [],
                "LinkedEnterprice": [],
            },
        }
        self.report = {
            "reportId": "report-1",
            "payload": {
                "subject": "Public Official",
                "sources": ["Asset Declarations", "OpenSanctions"],
                "declarations": [declaration],
                "news": [],
                "media": {"mentions": []},
                "opensanctions": [
                    {
                        "id": "screen-1",
                        "name": "Public Official",
                        "score": 82,
                        "topics": ["role.pep"],
                        "url": "https://screening.example/entities/screen-1",
                    }
                ],
            },
        }

    def test_builds_provenance_first_family_and_ownership_links(self):
        graph = _build_investigation_graph_bundle(self.case, self.report)
        evidence_ids = {row["evidenceId"] for row in graph["evidence"]}
        family_links = [
            row
            for row in graph["relationships"]
            if row["relationshipType"] == "Family: Sibling"
        ]
        self.assertEqual(len(family_links), 1)
        self.assertEqual(family_links[0]["verificationStatus"], "source-stated")
        self.assertTrue(family_links[0]["evidenceIds"])
        self.assertTrue(set(family_links[0]["evidenceIds"]).issubset(evidence_ids))

        ownership_links = [
            row
            for row in graph["relationships"]
            if row["relationshipType"] == "Declared ownership"
        ]
        self.assertEqual(len(ownership_links), 1)
        related = next(row for row in graph["entities"] if row["name"] == "Related Person")
        self.assertEqual(ownership_links[0]["fromEntityId"], related["entityId"])
        self.assertEqual(related["birthYear"], "1986")
        self.assertNotIn("birthDate", related)

    def test_screening_results_remain_candidate_matches(self):
        graph = _build_investigation_graph_bundle(self.case, self.report)
        screening_link = next(
            row
            for row in graph["relationships"]
            if row["relationshipType"] == "Candidate screening match"
        )
        self.assertEqual(screening_link["verificationStatus"], "candidate-match")
        self.assertAlmostEqual(screening_link["confidence"], 0.82)
        self.assertIn("not a confirmed identity", screening_link["details"])

    def test_ids_and_counts_are_stable_for_same_saved_report(self):
        first = _build_investigation_graph_bundle(self.case, self.report)
        second = _build_investigation_graph_bundle(self.case, self.report)
        self.assertEqual(
            {row["entityId"] for row in first["entities"]},
            {row["entityId"] for row in second["entities"]},
        )
        self.assertEqual(
            {row["relationshipId"] for row in first["relationships"]},
            {row["relationshipId"] for row in second["relationships"]},
        )
        evidence_ids = {row["evidenceId"] for row in first["evidence"]}
        self.assertTrue(
            all(
                set(row["evidenceIds"]).issubset(evidence_ids)
                for row in first["relationships"]
            )
        )

    def test_generated_insights_reference_the_existing_graph(self):
        bundle = _build_investigation_graph_bundle(self.case, self.report)
        graph = {
            "caseId": bundle["caseId"],
            "nodes": [
                {
                    "id": row["entityId"],
                    "label": row["name"],
                    "type": row["entityType"],
                    "isRoot": row.get("isRoot", False),
                    "properties": row,
                }
                for row in bundle["entities"]
            ],
            "relationships": [
                {
                    "id": row["relationshipId"],
                    "source": row["fromEntityId"],
                    "target": row["toEntityId"],
                    "label": row["relationshipType"],
                    "confidence": row["confidence"],
                    "verificationStatus": row["verificationStatus"],
                    "details": row["details"],
                    "evidenceIds": row["evidenceIds"],
                }
                for row in bundle["relationships"]
            ],
            "evidence": bundle["evidence"],
        }
        result = _build_investigation_insights(graph)
        lead_types = {row["leadType"] for row in result["insights"]}
        self.assertIn("relative_asset_or_business", lead_types)
        self.assertIn("candidate_screening_match", lead_types)
        self.assertEqual(result["summary"]["total"], len(result["insights"]))
        node_ids = {row["id"] for row in graph["nodes"]}
        relationship_ids = {row["id"] for row in graph["relationships"]}
        evidence_ids = {row["evidenceId"] for row in graph["evidence"]}
        for insight in result["insights"]:
            self.assertEqual(insight["status"], "lead")
            self.assertEqual(insight["verificationStatus"], "requires-review")
            self.assertTrue(set(insight["nodeIds"]).issubset(node_ids))
            self.assertTrue(set(insight["relationshipIds"]).issubset(relationship_ids))
            self.assertTrue(set(insight["evidenceIds"]).issubset(evidence_ids))
            self.assertNotIn("corruption", insight["title"].lower())

    @patch("deliberation.api.app.routes_due_diligence._persist_investigation_graph_bundle")
    @patch("deliberation.api.app.routes_due_diligence._load_investigation_graph")
    @patch("deliberation.api.app.routes_due_diligence._case_and_report_for_graph")
    def test_bulk_import_rejects_duplicate_external_ids(
        self, load_case, load_graph, persist
    ):
        load_case.return_value = (self.case, {"reportId": None, "payload": {}})
        load_graph.return_value = {"caseId": "case-1", "nodes": [], "relationships": [], "evidence": [], "sources": [], "stats": {}}
        payload = InvestigationGraphImportRequest.model_validate(
            {
                "source": {"name": "Company registry"},
                "entities": [
                    {"externalId": "entity-1", "name": "A", "entityType": "Organization"},
                    {"externalId": "entity-1", "name": "B", "entityType": "Organization"},
                ],
                "relationships": [],
            }
        )
        with self.assertRaises(HTTPException) as raised:
            import_due_diligence_investigation_graph("case-1", payload)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("must be unique", raised.exception.detail)
        persist.assert_not_called()

    @patch("deliberation.api.app.routes_due_diligence._persist_investigation_graph_bundle")
    @patch("deliberation.api.app.routes_due_diligence._load_investigation_graph")
    @patch("deliberation.api.app.routes_due_diligence._case_and_report_for_graph")
    def test_bulk_import_requires_resolvable_relationship_endpoints(
        self, load_case, load_graph, persist
    ):
        load_case.return_value = (self.case, {"reportId": None, "payload": {}})
        load_graph.return_value = {"caseId": "case-1", "nodes": [], "relationships": [], "evidence": [], "sources": [], "stats": {}}
        payload = InvestigationGraphImportRequest.model_validate(
            {
                "source": {"name": "Company registry"},
                "entities": [
                    {"externalId": "entity-1", "name": "A", "entityType": "Organization"},
                ],
                "relationships": [
                    {
                        "fromExternalId": "entity-1",
                        "toExternalId": "missing-entity",
                        "relationshipType": "Officer of",
                        "evidence": {"title": "Registry filing", "note": "The filing states the officer role."},
                    }
                ],
            }
        )
        with self.assertRaises(HTTPException) as raised:
            import_due_diligence_investigation_graph("case-1", payload)
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Unresolved externalId", raised.exception.detail)
        persist.assert_not_called()

    @patch("deliberation.api.app.routes_due_diligence._execute_write")
    @patch("deliberation.api.app.routes_due_diligence._db_session")
    @patch("deliberation.api.app.routes_due_diligence.get_driver")
    @patch("deliberation.api.app.routes_due_diligence._persist_investigation_graph_bundle")
    @patch("deliberation.api.app.routes_due_diligence._load_investigation_graph")
    @patch("deliberation.api.app.routes_due_diligence._case_and_report_for_graph")
    def test_native_ftm_import_preserves_interstitial_properties_and_evidence(
        self,
        load_case,
        load_graph,
        persist,
        get_driver,
        db_session,
        execute_write,
    ):
        load_case.return_value = (self.case, {"reportId": None, "payload": {}})
        empty_graph = {
            "caseId": "case-1",
            "nodes": [],
            "relationships": [],
            "evidence": [],
            "sources": [],
            "stats": {},
        }
        final_graph = dict(empty_graph)
        load_graph.side_effect = [empty_graph, final_graph]
        db_session.return_value.__enter__.return_value = object()
        payload = FollowTheMoneyGraphImportRequest.model_validate(
            {
                "dataset": {
                    "id": "company-register",
                    "name": "Company Register",
                    "url": "https://registry.example/",
                    "license": "Open data",
                },
                "entities": [
                    {
                        "id": "person-1",
                        "schema": "Person",
                        "properties": {
                            "name": ["Jane Doe"],
                            "birthDate": ["1980-01-02"],
                        },
                    },
                    {
                        "id": "company-1",
                        "schema": "Company",
                        "properties": {
                            "name": ["Example Holdings LLC"],
                            "registrationNumber": ["REG-1234567"],
                        },
                    },
                    {
                        "id": "directorship-1",
                        "schema": "Directorship",
                        "properties": {
                            "director": ["person-1"],
                            "organization": ["company-1"],
                            "role": ["Director"],
                            "startDate": ["2024-01-01"],
                            "sourceUrl": ["https://registry.example/record/1"],
                        },
                    },
                ],
            }
        )
        result = import_followthemoney_investigation_graph("case-1", payload)
        self.assertEqual(result["importResult"]["format"], "FollowTheMoney")
        self.assertEqual(result["importResult"]["entitiesProcessed"], 2)
        self.assertEqual(result["importResult"]["relationshipsProcessed"], 1)
        bundle = persist.call_args.args[0]
        relation = next(
            row for row in bundle["relationships"] if row["schema"] == "Directorship"
        )
        self.assertEqual(relation["properties"]["role"], ["Director"])
        self.assertEqual(relation["properties"]["startDate"], ["2024-01-01"])
        self.assertTrue(relation["evidenceIds"])
        company = next(
            row for row in bundle["entities"] if row.get("sourceExternalId") == "company-1"
        )
        self.assertIn("REG-1234567", company["identifiers"])
        self.assertTrue(company["evidenceIds"])
        get_driver.assert_called()
        execute_write.assert_called_once()


if __name__ == "__main__":
    unittest.main()
