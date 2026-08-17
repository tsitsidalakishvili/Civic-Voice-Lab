from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[1]
BE0_ROOT = ROOT.parent / "be0.4"


def load_json(root: Path, relative_path: str):
    return json.loads((root / relative_path).read_text(encoding="utf-8"))


SCHEMA = load_json(ROOT, "mutation.schema.json")
BE0_SCHEMA = load_json(BE0_ROOT, "contract.schema.json")
MANIFEST = load_json(ROOT, "manifest.json")
OPENAPI = load_json(ROOT, "openapi.json")
REGISTRY = (
    Registry()
    .with_resource(SCHEMA["$id"], Resource.from_contents(SCHEMA))
    .with_resource(BE0_SCHEMA["$id"], Resource.from_contents(BE0_SCHEMA))
)


def validator_for(definition: str) -> Draft202012Validator:
    return Draft202012Validator(
        {"$ref": f"{SCHEMA['$id']}#/$defs/{definition}"},
        registry=REGISTRY,
        format_checker=FormatChecker(),
    )


def assert_valid(test_case: unittest.TestCase, instance, definition: str) -> None:
    errors = sorted(validator_for(definition).iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        details = "\n".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        test_case.fail(f"{definition} validation failed:\n{details}")


def aggregate_hash(root: Path, files: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        file_hash = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def resolve_json_pointer(document, fragment: str):
    current = document
    if fragment in {"", "#"}:
        return current
    if not fragment.startswith("#/"):
        raise AssertionError(f"Unsupported JSON pointer: {fragment}")
    for raw in fragment[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


class MutationFixtureTests(unittest.TestCase):
    def test_request_fixtures_validate(self):
        cases = {
            "fixtures/create-case-request.json": "CreateCaseRequest",
            "fixtures/replace-intake-request.json": "IntakeReplaceRequest",
            "fixtures/duplicate-scan-request.json": "DuplicateScanRequest",
            "fixtures/duplicate-decision-request.json": "DuplicateDecisionRequest",
            "fixtures/transition-multi-waiver-request.json": "TransitionRequest",
        }
        for path, definition in cases.items():
            with self.subTest(path=path):
                assert_valid(self, load_json(ROOT, path), definition)

    def test_event_fixtures_validate(self):
        for path in (
            "fixtures/case-created-event.json",
            "fixtures/duplicate-scan-event.json",
            "fixtures/duplicate-decision-event.json",
        ):
            with self.subTest(path=path):
                assert_valid(self, load_json(ROOT, path), "OperationEvent")
        event = load_json(ROOT, "fixtures/transition-event.json")
        assert_valid(self, event, "OperationEvent")
        for waiver in event["waivers"]:
            assert_valid(self, waiver, "WaiverEvent")

    def test_error_fixtures_reuse_frozen_compliance_envelope(self):
        paths = [
            item["path"]
            for item in MANIFEST["fixtures"]
            if item.get("schemaDef") == "StandardErrorResponse"
        ]
        self.assertGreaterEqual(len(paths), 16)
        for path in paths:
            with self.subTest(path=path):
                assert_valid(self, load_json(ROOT, path), "StandardErrorResponse")

    def test_full_mutation_responses_validate_and_versions_are_coherent(self):
        fixtures = {
            "fixtures/create-case-response.json": "CreateCaseResponse",
            "fixtures/intake-changed-response.json": "IntakeMutationResponse",
            "fixtures/intake-noop-response.json": "IntakeMutationResponse",
            "fixtures/duplicate-scan-changed-response.json": "DuplicateScanResponse",
            "fixtures/duplicate-scan-unchanged-response.json": "DuplicateScanResponse",
            "fixtures/duplicate-decision-response.json": "DuplicateDecisionResponse",
            "fixtures/transition-response.json": "TransitionResponse",
            "fixtures/idempotent-replay-response.json": "TransitionResponse",
        }
        for path, definition in fixtures.items():
            with self.subTest(path=path):
                response = load_json(ROOT, path)
                assert_valid(self, response, definition)
                event_key = next(key for key in response if key.endswith("Event"))
                self.assertEqual(response["workflowVersion"], response[event_key]["workflowVersion"])
                self.assertEqual(response["workflowVersion"], response["case"]["workflowVersion"])
                self.assertEqual(response["workflowVersion"], response["workflow"]["workflowVersion"])

        self.assertTrue(load_json(ROOT, "fixtures/intake-changed-response.json")["intakeEvent"]["payload"]["changed"])
        noop = load_json(ROOT, "fixtures/intake-noop-response.json")
        self.assertFalse(noop["intakeEvent"]["payload"]["changed"])
        unchanged = load_json(ROOT, "fixtures/duplicate-scan-unchanged-response.json")
        self.assertFalse(unchanged["scanEvent"]["changed"])
        replay = load_json(ROOT, "fixtures/idempotent-replay-response.json")
        proof = load_json(ROOT, "fixtures/idempotency-replay-proof.json")
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(proof["replayedWorkflowVersion"], replay["workflowVersion"])
        self.assertGreater(proof["advancedWorkflowVersion"], replay["workflowVersion"])

    def test_operation_events_are_closed_and_discriminated(self):
        event = load_json(ROOT, "fixtures/case-created-event.json")
        event["rawSensitivePayload"] = "must-not-be-accepted"
        self.assertTrue(list(validator_for("OperationEvent").iter_errors(event)))
        event = load_json(ROOT, "fixtures/duplicate-scan-event.json")
        event["payload"]["unexpected"] = "must-not-be-accepted"
        self.assertTrue(list(validator_for("OperationEvent").iter_errors(event)))

    def test_conflict_details_are_required_only_for_declared_conflict(self):
        request = load_json(ROOT, "fixtures/create-case-request.json")
        request["intake"]["conflictDeclaration"] = {
            "status": "declared_conflict",
            "details": None,
            "attestation": {"attested": True},
        }
        self.assertTrue(list(validator_for("CreateCaseRequest").iter_errors(request)))

    def test_unicode_aliases_are_exact_utf8(self):
        request = load_json(ROOT, "fixtures/create-case-request.json")
        self.assertEqual("სატესტო ორგანიზაცია", request["intake"]["aliases"][0]["value"])
        self.assertEqual("Satesto Organizatsia", request["intake"]["aliases"][1]["value"])

    def test_person_identifier_and_actor_spoof_are_schema_invalid(self):
        request = load_json(ROOT, "fixtures/create-case-request.json")
        personal = copy.deepcopy(request)
        personal["intake"]["identifiers"][0]["type"] = "national_personal_id"
        self.assertTrue(list(validator_for("CreateCaseRequest").iter_errors(personal)))

        spoofed = copy.deepcopy(request)
        spoofed["preparationAttestation"]["actorId"] = "spoofed"
        self.assertTrue(list(validator_for("CreateCaseRequest").iter_errors(spoofed)))

        nested = load_json(ROOT, "fixtures/transition-multi-waiver-request.json")
        nested["waivers"][0]["attestation"]["method"] = "spoofed"
        self.assertTrue(list(validator_for("TransitionRequest").iter_errors(nested)))

    def test_full_replacement_and_attestation_keys_are_required(self):
        request = load_json(ROOT, "fixtures/replace-intake-request.json")
        del request["intake"]["deadline"]
        self.assertTrue(list(validator_for("IntakeReplaceRequest").iter_errors(request)))
        transition = load_json(ROOT, "fixtures/transition-multi-waiver-request.json")
        transition["attestations"]["preparedBy"] = {"attested": False}
        self.assertTrue(list(validator_for("TransitionRequest").iter_errors(transition)))

    def test_waiver_codes_are_unique_and_expiry_is_future(self):
        request = load_json(ROOT, "fixtures/transition-multi-waiver-request.json")
        codes = [item["blockerCode"] for item in request["waivers"]]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(2, len(request["waivers"]))
        duplicate = copy.deepcopy(request)
        duplicate["waivers"][1]["blockerCode"] = duplicate["waivers"][0]["blockerCode"]
        self.assertNotEqual(len({item["blockerCode"] for item in duplicate["waivers"]}), len(duplicate["waivers"]))
        self.assertEqual("DD_REQUEST_VALIDATION_FAILED", load_json(ROOT, "fixtures/duplicate-waiver-validation.json")["error"]["code"])
        self.assertEqual("DD_WAIVER_EXPIRY_INVALID", load_json(ROOT, "fixtures/waiver-expired.json")["error"]["code"])

    def test_stable_error_inventory_covers_each_remediation_branch(self):
        actual = {
            load_json(ROOT, item["path"])["error"]["code"]
            for item in MANIFEST["fixtures"]
            if item.get("schemaDef") == "StandardErrorResponse"
        }
        required = {
            "DD_WORKFLOW_V2_DISABLED", "DD_PURPOSE_MISMATCH", "DD_PURPOSE_CHANGE_NOT_SUPPORTED",
            "DD_TRANSITION_OUT_OF_ORDER", "DD_TRANSITION_BLOCKED", "DD_WAIVER_NOT_REQUIRED",
            "DD_BLOCKER_NON_WAIVABLE", "DD_ATTESTATION_REQUIRED", "DD_DUPLICATE_CANDIDATE_NOT_FOUND",
            "DD_LEGACY_MUTATION_DISABLED", "DD_REQUEST_VALIDATION_FAILED", "DD_WAIVER_EXPIRY_INVALID",
            "DD_WORKFLOW_VERSION_CONFLICT", "DD_IDEMPOTENCY_KEY_REUSED", "DD_IDENTIFIER_TYPE_PROHIBITED",
        }
        self.assertTrue(required.issubset(actual), required - actual)


class OpenApiBoundaryTests(unittest.TestCase):
    def test_every_pack_relative_ref_and_external_example_resolves(self):
        documents = {ROOT / "openapi.json": OPENAPI, ROOT / "mutation.schema.json": SCHEMA}
        for source_path, document in documents.items():
            for item in walk(document):
                if not isinstance(item, dict):
                    continue
                if "$ref" in item and not item["$ref"].startswith(("#", "https://")):
                    raw_path, separator, fragment = item["$ref"].partition("#")
                    target = (source_path.parent / raw_path).resolve()
                    self.assertTrue(target.is_file(), item["$ref"])
                    target_document = json.loads(target.read_text(encoding="utf-8"))
                    if separator:
                        resolve_json_pointer(target_document, f"#{fragment}")
                if "externalValue" in item:
                    target = (source_path.parent / item["externalValue"]).resolve()
                    self.assertTrue(target.is_file(), item["externalValue"])
                    json.loads(target.read_text(encoding="utf-8"))

    def test_only_be1_mutations_are_executable(self):
        executable = []
        drafts = []
        for path, path_item in OPENAPI["paths"].items():
            for method, operation in path_item.items():
                if method not in {"post", "put", "patch", "delete"} or not isinstance(operation, dict):
                    continue
                if operation.get("x-executable") is True:
                    executable.append((method.upper(), path))
                if str(operation.get("x-contract-status", "")).startswith("draft-be"):
                    drafts.append(operation)
        self.assertEqual(
            {
                ("POST", "/due-diligence/cases/v2"),
                ("PUT", "/due-diligence/cases/{caseId}/intake"),
                ("POST", "/due-diligence/cases/{caseId}/duplicate-candidates/scan"),
                ("POST", "/due-diligence/cases/{caseId}/duplicate-candidates/{candidateCaseId}/decisions"),
                ("POST", "/due-diligence/cases/{caseId}/transitions"),
            },
            set(executable),
        )
        self.assertTrue(drafts)
        self.assertTrue(all(item["x-executable"] is False for item in drafts))

    def test_every_be1_mutation_requires_purpose_and_idempotency(self):
        for path, path_item in OPENAPI["paths"].items():
            for method in ("post", "put"):
                operation = path_item.get(method) if isinstance(path_item, dict) else None
                if not isinstance(operation, dict) or operation.get("x-executable") is not True:
                    continue
                refs = {item.get("$ref") for item in operation.get("parameters", [])}
                self.assertIn("#/components/parameters/PurposeId", refs, (method, path))
                self.assertIn("#/components/parameters/IdempotencyKey", refs, (method, path))
                self.assertIn("#/components/parameters/CsrfToken", refs, (method, path))
                self.assertEqual("be1-mutation-contract-frozen", operation["x-contract-status"])

    def test_security_and_replay_semantics_are_explicit(self):
        boundary = OPENAPI["x-security-boundary"]
        self.assertIn("replay is evaluated before workflow version", boundary["idempotency"])
        self.assertIn("server-issued", boundary["attestations"])
        self.assertFalse(OPENAPI["x-feature-flag"]["default"])
        self.assertEqual("FS_DD_WORKFLOW_V2_ENABLED", OPENAPI["x-feature-flag"]["name"])
        self.assertEqual([{"fsSession": []}], OPENAPI["security"])
        self.assertEqual("cookie", OPENAPI["components"]["securitySchemes"]["fsSession"]["in"])
        self.assertEqual(12, OPENAPI["components"]["parameters"]["IdempotencyKey"]["schema"]["minLength"])

    def test_legacy_writes_are_declared_disabled(self):
        legacy = {}
        for path, path_item in OPENAPI["paths"].items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if isinstance(operation, dict) and operation.get("x-legacy-write"):
                    legacy[(method.upper(), path)] = operation
        self.assertEqual(
            {
                ("POST", "/due-diligence/cases"),
                ("PATCH", "/due-diligence/cases/{caseId}"),
                ("DELETE", "/due-diligence/cases/{caseId}"),
                ("POST", "/due-diligence/cases/{caseId}/decision"),
                ("POST", "/due-diligence/cases/{caseId}/archive"),
            },
            set(legacy),
        )
        self.assertTrue(all(item["x-disabled-when-v2-enabled"] is True for item in legacy.values()))

    def test_frozen_read_inventory_is_complete_and_later_reads_are_explicitly_unavailable(self):
        be0_openapi = load_json(BE0_ROOT, "openapi.json")
        expected = set(be0_openapi["paths"])
        self.assertTrue(expected.issubset(OPENAPI["paths"]), expected - set(OPENAPI["paths"]))
        unavailable = {
            "/due-diligence/cases/{caseId}/connectors",
            "/due-diligence/cases/{caseId}/connectors/{connectorId}",
            "/due-diligence/cases/{caseId}/connector-runs",
            "/due-diligence/cases/{caseId}/connector-runs/{connectorRunId}",
            "/due-diligence/cases/{caseId}/assessment",
            "/due-diligence/cases/{caseId}/reports",
            "/due-diligence/cases/{caseId}/reports/{snapshotId}",
        }
        for path in unavailable:
            operation = OPENAPI["paths"][path]["get"]
            self.assertEqual("unavailable-be1", operation["x-runtime-status"])
            self.assertTrue(operation["x-frozen-read-contract-ref"].startswith("../be0.4/openapi.json#"))
            self.assertIn("501", operation["responses"])

    def test_every_unique_v2_route_declares_disabled_404(self):
        unique = {
            ("GET", "/due-diligence/workflow/schema"),
            ("GET", "/due-diligence/cases/queue"),
            ("POST", "/due-diligence/cases/v2"),
            ("GET", "/due-diligence/cases/{caseId}/workflow"),
            ("PUT", "/due-diligence/cases/{caseId}/intake"),
            ("POST", "/due-diligence/cases/{caseId}/duplicate-candidates/scan"),
            ("POST", "/due-diligence/cases/{caseId}/duplicate-candidates/{candidateCaseId}/decisions"),
            ("POST", "/due-diligence/cases/{caseId}/transitions"),
        }
        for method, path in unique:
            self.assertIn("404", OPENAPI["paths"][path][method.lower()]["responses"], (method, path))

    def test_every_executable_response_has_security_headers_and_examples(self):
        responses = OPENAPI["components"]["responses"]
        for name in ("CreateCase", "IntakeMutation", "DuplicateScan", "DuplicateDecision", "Transition"):
            response = responses[name]
            self.assertEqual({"Idempotent-Replay", "X-FS-DD-Contract-Version", "Cache-Control"}, set(response["headers"]))
            self.assertTrue(response["content"]["application/json"]["examples"])
        self.assertEqual({"X-FS-DD-Contract-Version", "Cache-Control"}, set(responses["StandardError"]["headers"]))
        self.assertGreaterEqual(len(responses["StandardError"]["content"]["application/json"]["examples"]), 16)


class FreezeAndPrivacyTests(unittest.TestCase):
    def test_manifest_and_freeze_hash(self):
        self.assertEqual("dd-workflow.v2-be1.0", MANIFEST["mutationContractVersion"])
        self.assertEqual("dd-workflow.v2-be1.0", MANIFEST["artifactVersion"])
        self.assertEqual("mutation_contract_frozen", MANIFEST["schemaStatus"])
        expected = (ROOT / "FREEZE.sha256").read_text(encoding="ascii").strip()
        self.assertRegex(expected, r"^[0-9a-f]{64}$")
        self.assertEqual(expected, aggregate_hash(ROOT, MANIFEST["freezeFiles"]))

    def test_be0_bytes_remain_at_approved_hash(self):
        be0_manifest = load_json(BE0_ROOT, "manifest.json")
        expected = (BE0_ROOT / "FREEZE.sha256").read_text(encoding="ascii").strip()
        self.assertEqual("ffcee73310c0016c5a18fe8ac59490db63dc6c3243445567785b6ed01c8fcc21", expected)
        self.assertEqual(expected, aggregate_hash(BE0_ROOT, be0_manifest["freezeFiles"]))

    def test_fixtures_contain_no_email_token_or_secret(self):
        forbidden = re.compile(r"(?i)(bearer\s+|api[_-]?key|client[_-]?secret|password|[\w.+-]+@[\w.-]+)")
        for path in (ROOT / "fixtures").glob("*.json"):
            self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), path.name)

    def test_full_outputs_never_contain_raw_identifier_or_unrestricted_event_payload(self):
        output_paths = [
            item["path"]
            for item in MANIFEST["fixtures"]
            if item.get("schemaDef") in {
                "CreateCaseResponse", "IntakeMutationResponse", "DuplicateScanResponse",
                "DuplicateDecisionResponse", "TransitionResponse", "OperationEvent", "StandardErrorResponse",
            }
        ]
        for path in output_paths:
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertNotIn("SYNTHETIC-0001", text, path)
            self.assertNotIn("rawSensitivePayload", text, path)

    def test_migration_fixture_and_report_are_synthetic_and_safe(self):
        rows = load_json(ROOT, "fixtures/migration-legacy-cases.json")
        report = load_json(ROOT, "fixtures/migration-dry-run-report.json")
        self.assertEqual(2, len(rows))
        self.assertEqual(2, report["plannedCount"])
        self.assertTrue(report["dryRun"])
        self.assertNotIn("projections", report)
        self.assertTrue(all("synthetic" in row["caseId"] for row in rows))


if __name__ == "__main__":
    unittest.main()
