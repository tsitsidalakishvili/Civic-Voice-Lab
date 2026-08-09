from __future__ import annotations

import copy
import hashlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from pydantic import ValidationError
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from deliberation.api.app.dd_workflow_v2 import (
    CreateCaseRequest,
    DuplicateDecisionRequest,
    DuplicateScanRequest,
    InMemoryWorkflowStore,
    IntakeReplaceRequest,
    TransitionRequest,
    WorkflowDomainError,
    WorkflowPolicy,
    WorkflowService,
    _context,
    compute_blockers,
    initial_projection,
    legacy_mutation_disabled_response,
    router as workflow_router,
    workflow_v2_enabled,
)


NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
ACTOR = {
    "actorId": "actor-synthetic-investigator",
    "displayName": "Synthetic Investigator",
    "method": "oidc_session",
}
PURPOSE = "dd-investigation"


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_hash(value: str, purpose: str) -> str:
    return stable_hash(f"{purpose}:{value}")


def active_policy() -> WorkflowPolicy:
    return WorkflowPolicy(
        retention_classes={"dd-test-active": "active"},
        allowed_identifier_types=frozenset({"company_registration_number", "lei"}),
        coverage_threshold=0.75,
        policy_version=1,
    )


def intake_payload(
    *,
    alias: str = "სატესტო ორგანიზაცია",
    latin_alias: str = "Satesto Organizatsia",
    identifier: str | None = "SYNTHETIC-0001",
    purpose_id: str = PURPOSE,
    prior_status: str = "none",
) -> dict:
    identifiers = []
    if identifier is not None:
        identifiers.append(
            {
                "type": "company_registration_number",
                "value": identifier,
                "issuer": "synthetic-registry",
                "country": "GE",
            }
        )
    return {
        "purpose": "investigative_research",
        "purposeDetails": "Synthetic workflow validation only.",
        "intendedDecision": "inform_only",
        "requestor": {
            "actorId": "actor-synthetic-requestor",
            "displayName": "Synthetic Requestor",
            "teamId": "team-synthetic",
        },
        "owner": {
            "actorId": "actor-synthetic-investigator",
            "displayName": "Synthetic Investigator",
            "teamId": "team-synthetic",
        },
        "subjectCategory": "organization",
        "jurisdictions": ["GE"],
        "dateRange": {"from": "2024-01-01", "to": "2026-08-01"},
        "identifiers": identifiers,
        "aliases": [
            {"value": alias, "script": "Geor", "language": "ka", "type": "official"},
            {"value": latin_alias, "script": "Latn", "language": "ka-Latn", "type": "transliteration"},
        ],
        "diligenceDepth": "enhanced",
        "processingPurposeId": purpose_id,
        "lawfulBasisRef": "basis-synthetic-approved",
        "deadline": "2026-08-31T17:00:00+04:00",
        "retentionClass": "dd-test-active",
        "conflictDeclaration": {
            "status": "declared_none",
            "details": None,
            "attestation": {"attested": True},
        },
        "priorScreening": {"status": prior_status, "refs": []},
    }


def create_payload(**kwargs) -> CreateCaseRequest:
    return CreateCaseRequest.model_validate(
        {
            "intake": intake_payload(**kwargs),
            "preparationAttestation": {"attested": True},
        }
    )


def make_service(store: InMemoryWorkflowStore | None = None, policy: WorkflowPolicy | None = None) -> WorkflowService:
    return WorkflowService(
        store or InMemoryWorkflowStore(),
        policy=policy or active_policy(),
        now=lambda: NOW,
        identifier_hasher=stable_hash,
        request_hasher=request_hash,
        field_policy_checker=lambda purpose_id, fields: (True, []),
    )


def create_case(service: WorkflowService, *, key: str = "synthetic-create-key-0001", **kwargs) -> dict:
    return service.create_case(
        create_payload(**kwargs),
        idempotency_key=key,
        actor=ACTOR,
        purpose_id=PURPOSE,
        path="/due-diligence/cases/v2",
    )


def transition_payload(version: int, code: str, to_stage: str, *, waivers: list | None = None, reviewed: bool = False) -> TransitionRequest:
    return TransitionRequest.model_validate(
        {
            "expectedWorkflowVersion": version,
            "transitionCode": code,
            "toStage": to_stage,
            "waivers": waivers or [],
            "attestations": {
                "preparedBy": {"attested": True},
                "reviewedBy": {"attested": True} if reviewed else None,
            },
        }
    )


class IntakeAndPrivacyTests(unittest.TestCase):
    def test_unicode_alias_round_trip_and_identifier_is_hmac_only(self):
        store = InMemoryWorkflowStore()
        service = make_service(store)
        response = create_case(service)
        state = store.load_case(response["caseId"])

        self.assertEqual("სატესტო ორგანიზაცია", state["intake"]["aliases"][0]["value"])
        stored_identifier = state["intake"]["identifiers"][0]
        self.assertNotIn("value", stored_identifier)
        self.assertNotIn("SYNTHETIC-0001", json.dumps(state, ensure_ascii=False))
        self.assertEqual(64, len(stored_identifier["valueHash"]))
        public_identifier = response["case"]["intake"]["identifiers"][0]
        self.assertIsNone(public_identifier["value"])
        self.assertTrue(public_identifier["masked"])
        self.assertTrue(public_identifier["displayValue"].endswith("0001"))

    def test_actor_spoof_fields_are_rejected_at_every_attestation_boundary(self):
        raw = {
            "intake": intake_payload(),
            "preparationAttestation": {"attested": True, "actorId": "spoofed"},
            "actorId": "spoofed",
        }
        raw["intake"]["conflictDeclaration"]["attestation"]["actor"] = {"actorId": "spoofed"}
        with self.assertRaises(ValidationError):
            CreateCaseRequest.model_validate(raw)

        with self.assertRaises(ValidationError):
            TransitionRequest.model_validate(
                {
                    "expectedWorkflowVersion": 1,
                    "transitionCode": "complete_identity",
                    "toStage": "sources",
                    "waivers": [
                        {
                            "blockerCode": "DD_DUPLICATE_REVIEW_PENDING",
                            "reason": "Synthetic accepted exception.",
                            "expiresAt": None,
                            "attestation": {"attested": True, "method": "spoofed"},
                        }
                    ],
                    "attestations": {"preparedBy": {"attested": True}, "reviewedBy": None},
                }
            )

    def test_person_identifier_type_is_rejected_without_echo(self):
        raw = intake_payload()
        raw["identifiers"][0]["type"] = "national_personal_id"
        raw["identifiers"][0]["value"] = "DO-NOT-ECHO-SYNTHETIC"
        payload = CreateCaseRequest.model_validate(
            {"intake": raw, "preparationAttestation": {"attested": True}}
        )
        with self.assertRaises(WorkflowDomainError) as raised:
            make_service().create_case(
                payload,
                idempotency_key="synthetic-prohibited-0001",
                actor=ACTOR,
                purpose_id=PURPOSE,
                path="/due-diligence/cases/v2",
            )
        self.assertEqual("DD_IDENTIFIER_TYPE_PROHIBITED", raised.exception.code)
        self.assertNotIn("DO-NOT-ECHO", raised.exception.message)
        self.assertNotIn("DO-NOT-ECHO", json.dumps(raised.exception.details))

    def test_field_policy_denies_identifier_collection(self):
        service = WorkflowService(
            InMemoryWorkflowStore(),
            policy=active_policy(),
            now=lambda: NOW,
            identifier_hasher=stable_hash,
            request_hasher=request_hash,
            field_policy_checker=lambda purpose_id, fields: (False, fields),
        )
        with self.assertRaises(WorkflowDomainError) as raised:
            create_case(service)
        self.assertEqual("DD_IDENTIFIER_FIELD_POLICY_DENIED", raised.exception.code)

    def test_established_purpose_cannot_be_silently_changed(self):
        store = InMemoryWorkflowStore()
        service = make_service(store)
        created = create_case(service)
        replacement = intake_payload(purpose_id="dd-second-purpose")
        payload = IntakeReplaceRequest.model_validate(
            {
                "expectedWorkflowVersion": created["workflowVersion"],
                "intake": replacement,
                "preparationAttestation": {"attested": True},
            }
        )
        with self.assertRaises(WorkflowDomainError) as raised:
            service.replace_intake(
                created["caseId"],
                payload,
                idempotency_key="synthetic-purpose-change-0001",
                actor=ACTOR,
                purpose_id="dd-second-purpose",
                principal_purpose_scopes={PURPOSE, "dd-second-purpose"},
                path=f"/due-diligence/cases/{created['caseId']}/intake",
            )
        self.assertEqual("DD_PURPOSE_CHANGE_NOT_SUPPORTED", raised.exception.code)

    def test_proposed_purpose_must_match_header_and_declared_conflict_requires_details(self):
        service = make_service()
        with self.assertRaises(WorkflowDomainError) as mismatch:
            service.create_case(
                create_payload(),
                idempotency_key="synthetic-purpose-mismatch-0001",
                actor=ACTOR,
                purpose_id="different-approved-purpose",
                path="/due-diligence/cases/v2",
            )
        self.assertEqual("DD_PURPOSE_MISMATCH", mismatch.exception.code)

        raw = intake_payload()
        raw["conflictDeclaration"] = {
            "status": "declared_conflict",
            "details": None,
            "attestation": {"attested": True},
        }
        with self.assertRaises(ValidationError):
            CreateCaseRequest.model_validate(
                {"intake": raw, "preparationAttestation": {"attested": True}}
            )


class TransitionAndIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryWorkflowStore()
        self.service = make_service(self.store)
        self.created = create_case(self.service)
        self.case_id = self.created["caseId"]

    def transition(self, payload: TransitionRequest, key: str) -> dict:
        return self.service.transition(
            self.case_id,
            payload,
            idempotency_key=key,
            actor=ACTOR,
            purpose_id=PURPOSE,
            path=f"/due-diligence/cases/{self.case_id}/transitions",
        )

    def test_transition_order_completion_and_exact_once_increment(self):
        first = self.transition(
            transition_payload(1, "complete_intake", "identity"),
            "synthetic-transition-0001",
        )
        self.assertEqual(2, first["workflowVersion"])
        self.assertEqual("identity", first["workflow"]["stage"])
        intake_completion = next(item for item in first["workflow"]["completion"] if item["stage"] == "intake")
        self.assertEqual("complete", intake_completion["state"])
        self.assertEqual("case_prepared", intake_completion["actorAttestation"]["statementCode"])

        second = self.transition(
            transition_payload(2, "complete_identity", "sources"),
            "synthetic-transition-0002",
        )
        self.assertEqual(3, second["workflowVersion"])
        self.assertEqual("sources", second["workflow"]["stage"])
        self.assertEqual([], second["workflow"]["allowedTransitions"])
        self.assertIn("DD_BE2_COVERAGE_NOT_AVAILABLE", {item["code"] for item in second["workflow"]["blockers"]})

    def test_transition_code_and_stage_must_match_current_offer(self):
        with self.assertRaises(WorkflowDomainError) as raised:
            self.transition(
                transition_payload(1, "complete_identity", "identity"),
                "synthetic-wrong-offer-0001",
            )
        self.assertEqual("DD_TRANSITION_OUT_OF_ORDER", raised.exception.code)
        self.assertEqual(1, self.store.load_case(self.case_id)["workflowVersion"])

    def test_new_key_checks_version_but_replay_precedes_version(self):
        first_payload = transition_payload(1, "complete_intake", "identity")
        first = self.transition(first_payload, "synthetic-replay-key-0001")
        self.transition(
            transition_payload(2, "complete_identity", "sources"),
            "synthetic-replay-key-0002",
        )
        replay = self.transition(first_payload, "synthetic-replay-key-0001")
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(first["workflowVersion"], replay["workflowVersion"])

        with self.assertRaises(WorkflowDomainError) as stale:
            self.transition(first_payload, "synthetic-new-stale-key-0003")
        self.assertEqual("DD_WORKFLOW_VERSION_CONFLICT", stale.exception.code)
        self.assertEqual(3, stale.exception.details["actualWorkflowVersion"])

    def test_same_idempotency_key_different_body_is_rejected(self):
        self.transition(
            transition_payload(1, "complete_intake", "identity"),
            "synthetic-body-mismatch-0001",
        )
        with self.assertRaises(WorkflowDomainError) as raised:
            self.transition(
                transition_payload(1, "complete_intake", "sources"),
                "synthetic-body-mismatch-0001",
            )
        self.assertEqual("DD_IDEMPOTENCY_KEY_REUSED", raised.exception.code)

    def test_shared_twelve_character_idempotency_minimum_is_enforced(self):
        accepted = self.transition(
            transition_payload(1, "complete_intake", "identity"),
            "123456789012",
        )
        self.assertEqual(2, accepted["workflowVersion"])
        with self.assertRaises(WorkflowDomainError) as invalid:
            self.service.scan_duplicates(
                self.case_id,
                DuplicateScanRequest.model_validate({"expectedWorkflowVersion": 2}),
                idempotency_key="12345678901",
                actor=ACTOR,
                purpose_id=PURPOSE,
                path=f"/due-diligence/cases/{self.case_id}/duplicate-candidates/scan",
            )
        self.assertEqual("DD_IDEMPOTENCY_KEY_INVALID", invalid.exception.code)

    def test_multiple_waivers_commit_atomically(self):
        self.transition(
            transition_payload(1, "complete_intake", "identity"),
            "synthetic-to-identity-0001",
        )
        state = self.store.load_case(self.case_id)
        state["intake"]["priorScreening"]["status"] = "unknown"
        state["duplicateCandidates"] = [
            {
                "caseId": "case-synthetic-candidate",
                "subjectDisplay": "S•••t",
                "subjectMasked": True,
                "confidence": 0.65,
                "reasons": [{"code": "NORMALIZED_ALIAS_MATCH", "field": "aliases", "summary": "Name-only lead."}],
                "conflicts": [],
                "state": "pending",
                "analystDecision": None,
                "actions": [],
            }
        ]
        self.store.cases[self.case_id] = state
        before = copy.deepcopy(state)

        one_waiver = [
            {
                "blockerCode": "DD_DUPLICATE_REVIEW_PENDING",
                "reason": "Synthetic exception for contract test.",
                "attestation": {"attested": True},
                "expiresAt": None,
            }
        ]
        with self.assertRaises(WorkflowDomainError) as missing:
            self.transition(
                transition_payload(2, "complete_identity", "sources", waivers=one_waiver),
                "synthetic-partial-waiver-0001",
            )
        self.assertEqual("DD_TRANSITION_BLOCKED", missing.exception.code)
        self.assertEqual(before, self.store.load_case(self.case_id))

        both = [
            *one_waiver,
            {
                "blockerCode": "DD_PRIOR_SCREENING_REVIEW_PENDING",
                "reason": "Synthetic second exception for contract test.",
                "attestation": {"attested": True},
                "expiresAt": (NOW + timedelta(days=7)).isoformat(),
            },
        ]
        result = self.transition(
            transition_payload(2, "complete_identity", "sources", waivers=both),
            "synthetic-atomic-waiver-0002",
        )
        self.assertEqual(3, result["workflowVersion"])
        self.assertEqual(2, len(result["transitionEvent"]["waivers"]))
        self.assertTrue(all(item["actor"]["statementCode"] == "blocker_waived" for item in result["transitionEvent"]["waivers"]))

    def test_nonwaivable_blocker_cannot_be_waived(self):
        provisional_service = make_service(self.store, WorkflowPolicy(
            retention_classes={"dd-test-active": "provisional"},
            allowed_identifier_types=active_policy().allowed_identifier_types,
            coverage_threshold=0.75,
            policy_version=1,
        ))
        payload = transition_payload(
            1,
            "complete_intake",
            "identity",
            waivers=[
                {
                    "blockerCode": "DD_RETENTION_POLICY_DECISION_REQUIRED",
                    "reason": "This must be rejected by governance.",
                    "attestation": {"attested": True},
                    "expiresAt": None,
                }
            ],
        )
        with self.assertRaises(WorkflowDomainError) as raised:
            provisional_service.transition(
                self.case_id,
                payload,
                idempotency_key="synthetic-nonwaivable-0001",
                actor=ACTOR,
                purpose_id=PURPOSE,
                path=f"/due-diligence/cases/{self.case_id}/transitions",
            )
        self.assertEqual("DD_BLOCKER_NON_WAIVABLE", raised.exception.code)

    def test_extra_expired_and_unattested_waivers_fail_without_writes(self):
        self.transition(
            transition_payload(1, "complete_intake", "identity"),
            "synthetic-waiver-prep-0001",
        )
        before = self.store.load_case(self.case_id)
        extra = [
            {
                "blockerCode": "DD_SYNTHETIC_EXTRA_WAIVER",
                "reason": "Synthetic waiver is not required.",
                "attestation": {"attested": True},
                "expiresAt": None,
            }
        ]
        with self.assertRaises(WorkflowDomainError) as unnecessary:
            self.transition(
                transition_payload(2, "complete_identity", "sources", waivers=extra),
                "synthetic-waiver-extra-0002",
            )
        self.assertEqual("DD_WAIVER_NOT_REQUIRED", unnecessary.exception.code)
        self.assertEqual(before, self.store.load_case(self.case_id))

        state = self.store.load_case(self.case_id)
        state["duplicateCandidates"] = [
            {
                "caseId": "case-synthetic-candidate",
                "subjectDisplay": "Sâ€¢â€¢â€¢t",
                "subjectMasked": True,
                "confidence": 0.65,
                "reasons": [],
                "conflicts": [],
                "state": "pending",
                "analystDecision": None,
                "actions": [],
            }
        ]
        self.store.cases[self.case_id] = state
        expired = [
            {
                "blockerCode": "DD_DUPLICATE_REVIEW_PENDING",
                "reason": "Synthetic expired waiver is rejected.",
                "attestation": {"attested": True},
                "expiresAt": (NOW - timedelta(seconds=1)).isoformat(),
            }
        ]
        with self.assertRaises(WorkflowDomainError) as expiry:
            self.transition(
                transition_payload(2, "complete_identity", "sources", waivers=expired),
                "synthetic-waiver-expired-0003",
            )
        self.assertEqual("DD_WAIVER_EXPIRY_INVALID", expiry.exception.code)

        raw = transition_payload(2, "complete_identity", "sources", waivers=expired).model_dump(by_alias=True)
        raw["waivers"][0]["attestation"] = {"attested": False}
        with self.assertRaises(ValidationError):
            TransitionRequest.model_validate(raw)


class DuplicateTests(unittest.TestCase):
    def test_name_only_scan_is_a_masked_lead_and_link_never_merges(self):
        store = InMemoryWorkflowStore()
        service = make_service(store)
        first = create_case(service, key="synthetic-create-first-0001", identifier=None)
        second = create_case(service, key="synthetic-create-second-0002", identifier=None)

        scan = service.scan_duplicates(
            first["caseId"],
            DuplicateScanRequest.model_validate({"expectedWorkflowVersion": 1}),
            idempotency_key="synthetic-scan-duplicates-0001",
            actor=ACTOR,
            purpose_id=PURPOSE,
            path=f"/due-diligence/cases/{first['caseId']}/duplicate-candidates/scan",
        )
        self.assertEqual(1, len(scan["duplicateCandidates"]))
        candidate = scan["duplicateCandidates"][0]
        self.assertEqual(second["caseId"], candidate["caseId"])
        self.assertEqual(0.65, candidate["confidence"])
        self.assertTrue(candidate["subjectMasked"])
        self.assertEqual("pending", candidate["state"])
        actions = {action["actionCode"]: action for action in candidate["actions"]}
        self.assertEqual("GET", actions["open_existing"]["method"])
        self.assertEqual("POST", actions["link_existing"]["method"])

        decision = service.decide_duplicate(
            first["caseId"],
            second["caseId"],
            DuplicateDecisionRequest.model_validate(
                {
                    "expectedWorkflowVersion": scan["workflowVersion"],
                    "decision": "link_existing",
                    "rationale": "Synthetic analyst confirmed the case relation only.",
                    "attestation": {"attested": True},
                }
            ),
            idempotency_key="synthetic-link-existing-0001",
            actor=ACTOR,
            purpose_id=PURPOSE,
            candidate_authorized=True,
            path=f"/due-diligence/cases/{first['caseId']}/duplicate-candidates/{second['caseId']}/decisions",
        )
        self.assertFalse(decision["decisionEvent"]["mergePerformed"])
        self.assertEqual("linked_existing", decision["duplicateCandidates"][0]["state"])
        self.assertEqual(2, len(store.cases))

    def test_out_of_scope_link_is_generic_not_found(self):
        store = InMemoryWorkflowStore()
        service = make_service(store)
        first = create_case(service, key="synthetic-create-scope-a", identifier=None)
        second = create_case(service, key="synthetic-create-scope-b", identifier=None)
        scan = service.scan_duplicates(
            first["caseId"],
            DuplicateScanRequest.model_validate({"expectedWorkflowVersion": 1}),
            idempotency_key="synthetic-scan-scope-0001",
            actor=ACTOR,
            purpose_id=PURPOSE,
            path="/synthetic/scan",
        )
        with self.assertRaises(WorkflowDomainError) as raised:
            service.decide_duplicate(
                first["caseId"],
                second["caseId"],
                DuplicateDecisionRequest.model_validate(
                    {
                        "expectedWorkflowVersion": scan["workflowVersion"],
                        "decision": "link_existing",
                        "rationale": "Synthetic out-of-scope attempt.",
                        "attestation": {"attested": True},
                    }
                ),
                idempotency_key="synthetic-out-of-scope-0001",
                actor=ACTOR,
                purpose_id=PURPOSE,
                candidate_authorized=False,
                path="/synthetic/decision",
            )
        self.assertEqual(404, raised.exception.status_code)
        self.assertEqual("DD_DUPLICATE_CANDIDATE_NOT_FOUND", raised.exception.code)

    def test_list_and_queue_cursors_follow_stable_sort_and_queue_counts_pending_leads(self):
        store = InMemoryWorkflowStore()
        service = make_service(store)
        created = [
            create_case(service, key=f"synthetic-pagination-{index:04d}", identifier=None)
            for index in range(3)
        ]
        first_page = service.list_case_response(purpose_id=PURPOSE, limit=1)
        second_page = service.list_case_response(
            purpose_id=PURPOSE,
            limit=1,
            cursor=first_page["page"]["nextCursor"],
        )
        self.assertNotEqual(first_page["items"][0]["caseId"], second_page["items"][0]["caseId"])

        scan = service.scan_duplicates(
            created[0]["caseId"],
            DuplicateScanRequest.model_validate({"expectedWorkflowVersion": 1}),
            idempotency_key="synthetic-pagination-scan-0001",
            actor=ACTOR,
            purpose_id=PURPOSE,
            path="/synthetic/pagination/scan",
        )
        queue = service.queue_response(purpose_id=PURPOSE, limit=10)
        scanned_item = next(item for item in queue["items"] if item["caseId"] == scan["caseId"])
        self.assertEqual(2, scanned_item["unresolvedCandidateCount"])
        remaining = [item["caseId"] for item in queue["items"] if item["caseId"] != scan["caseId"]]
        self.assertEqual(sorted(remaining), remaining)


class FeatureBoundaryAndMigrationProjectionTests(unittest.TestCase):
    def request(self, *, principal=None, purpose=PURPOSE) -> Request:
        headers = [(b"x-fs-purpose-id", purpose.encode("ascii"))] if purpose else []
        request = Request({"type": "http", "method": "POST", "path": "/due-diligence/cases/case-1", "headers": headers})
        request.state.request_id = "request-synthetic"
        if principal is not None:
            request.state.principal = principal
        if purpose:
            request.state.purpose_id = purpose
        return request

    def test_feature_flag_defaults_off_and_legacy_block_is_flag_on_only(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FS_DD_WORKFLOW_V2_ENABLED", None)
            self.assertFalse(workflow_v2_enabled())
            self.assertIsNone(legacy_mutation_disabled_response(self.request(), "replacement"))
        with patch.dict(os.environ, {"FS_DD_WORKFLOW_V2_ENABLED": "1"}):
            response = legacy_mutation_disabled_response(self.request(), "replacement")
            self.assertEqual(409, response.status_code)
            self.assertEqual("DD_LEGACY_MUTATION_DISABLED", json.loads(response.body)["error"]["code"])

    def test_boundary_denies_missing_principal_role_case_and_purpose(self):
        with self.assertRaises(WorkflowDomainError) as missing:
            _context(self.request(principal=None), mutation=True)
        self.assertEqual(401, missing.exception.status_code)

        principal = {"principalId": "actor", "provider": "google", "roles": ["viewer"], "caseScopes": ["*"], "purposeScopes": ["*"]}
        with self.assertRaises(WorkflowDomainError) as role:
            _context(self.request(principal=principal), mutation=True)
        self.assertEqual("ROLE_FORBIDDEN", role.exception.code)

        principal["roles"] = ["investigator"]
        principal["caseScopes"] = ["case-other"]
        with self.assertRaises(WorkflowDomainError) as case:
            _context(self.request(principal=principal), case_id="case-1", mutation=True)
        self.assertEqual(404, case.exception.status_code)

        principal["caseScopes"] = ["*"]
        principal["purposeScopes"] = ["different-purpose"]
        with self.assertRaises(WorkflowDomainError) as purpose:
            _context(self.request(principal=principal), mutation=True)
        self.assertEqual("PURPOSE_FORBIDDEN", purpose.exception.code)

    def test_legacy_projection_is_conservative_and_marks_unknown(self):
        projection = initial_projection(
            {
                "caseId": "case-synthetic-legacy",
                "subjectGeorgian": "სატესტო მემკვიდრეობითი სუბიექტი",
                "subjectEnglish": "Synthetic Legacy Subject",
                "subjectType": "Person",
                "status": "Active",
                "owner": "",
                "createdAt": "2025-01-01T00:00:00+00:00",
                "updatedAt": "2025-01-02T00:00:00+00:00",
            },
            now=NOW.isoformat(),
        )
        self.assertTrue(projection["migrationNeedsReview"])
        self.assertEqual("sources", projection["stage"])
        self.assertEqual("unknown", projection["completion"]["intake"]["state"])
        self.assertEqual("legacy-unknown", projection["intake"]["processingPurposeId"])
        blockers = compute_blockers(projection, active_policy())
        self.assertIn("DD_PURPOSE_AUTHORIZATION_REQUIRED", {item["code"] for item in blockers})

    def test_flagged_routes_use_standard_disabled_error_and_no_store(self):
        app = FastAPI()
        app.include_router(workflow_router, prefix="/due-diligence")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FS_DD_WORKFLOW_V2_ENABLED", None)
            with patch("deliberation.api.app.dd_workflow_v2._service") as service_factory:
                response = TestClient(app).get("/due-diligence/workflow/schema")
                self.assertEqual(404, response.status_code)
                self.assertEqual("DD_WORKFLOW_V2_DISABLED", response.json()["error"]["code"])
                self.assertEqual("dd-workflow.v2", response.headers["X-FS-DD-Contract-Version"])
                self.assertEqual("no-store", response.headers["Cache-Control"])
                service_factory.assert_not_called()

    def test_enabled_route_server_issues_actor_and_replay_header(self):
        store = InMemoryWorkflowStore()
        service = make_service(store)
        app = FastAPI()

        @app.middleware("http")
        async def synthetic_principal(request, call_next):
            request.state.request_id = "request-synthetic-route"
            request.state.purpose_id = PURPOSE
            request.state.principal = {
                "principalId": ACTOR["actorId"],
                "provider": "google",
                "issuer": "https://synthetic.invalid",
                "roles": ["investigator"],
                "caseScopes": ["*"],
                "purposeScopes": [PURPOSE],
            }
            return await call_next(request)

        app.include_router(workflow_router, prefix="/due-diligence")
        body = create_payload().model_dump(by_alias=True, mode="json")
        with patch.dict(os.environ, {"FS_DD_WORKFLOW_V2_ENABLED": "1"}), patch(
            "deliberation.api.app.dd_workflow_v2._service", return_value=service
        ):
            client = TestClient(app)
            first = client.post(
                "/due-diligence/cases/v2",
                headers={"Idempotency-Key": "synthetic-route-create-0001", "X-FS-Purpose-Id": PURPOSE},
                json=body,
            )
            self.assertEqual(201, first.status_code)
            self.assertEqual("false", first.headers["Idempotent-Replay"])
            self.assertEqual(ACTOR["actorId"], first.json()["caseCreatedEvent"]["actor"]["actor"]["actorId"])
            replay = client.post(
                "/due-diligence/cases/v2",
                headers={"Idempotency-Key": "synthetic-route-create-0001", "X-FS-Purpose-Id": PURPOSE},
                json=body,
            )
            self.assertEqual(201, replay.status_code)
            self.assertEqual("true", replay.headers["Idempotent-Replay"])
            self.assertTrue(replay.json()["idempotentReplay"])

    def test_actor_spoof_route_error_is_standard_and_sanitized(self):
        app = FastAPI()
        app.include_router(workflow_router, prefix="/due-diligence")
        body = create_payload().model_dump(by_alias=True, mode="json")
        body["preparationAttestation"]["actorId"] = "SENSITIVE-SPOOF-VALUE"
        with patch.dict(os.environ, {"FS_DD_WORKFLOW_V2_ENABLED": "1"}):
            response = TestClient(app).post(
                "/due-diligence/cases/v2",
                headers={"Idempotency-Key": "synthetic-spoof-route-0001"},
                json=body,
            )
        self.assertEqual(422, response.status_code)
        self.assertEqual("DD_REQUEST_VALIDATION_FAILED", response.json()["error"]["code"])
        self.assertNotIn("SENSITIVE-SPOOF-VALUE", response.text)


if __name__ == "__main__":
    unittest.main()
