from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]


def load_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


SCHEMA = load_json("contract.schema.json")
MANIFEST = load_json("manifest.json")
OPENAPI = load_json("openapi.json")


def validator_for(schema_ref: str) -> Draft202012Validator:
    document = {
        "$schema": SCHEMA["$schema"],
        "$defs": SCHEMA["$defs"],
        "$ref": schema_ref,
    }
    return Draft202012Validator(document, format_checker=FormatChecker())


def assert_valid(test_case: unittest.TestCase, instance: object, schema_ref: str) -> None:
    errors = sorted(validator_for(schema_ref).iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        details = "\n".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
            for error in errors
        )
        test_case.fail(f"{schema_ref} validation failed:\n{details}")


def decoded_safe_relative_path(raw: str) -> bool:
    """Acceptance-test canonicalization; not a runtime route implementation."""
    if not isinstance(raw, str) or not raw:
        return False
    decoded = raw
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    else:
        return False

    if unquote(decoded) != decoded:
        return False
    if not decoded.startswith("/") or decoded.startswith("//"):
        return False
    if any(character in decoded for character in ("\\", "?", "#", "\r", "\n", "\x00")):
        return False
    if "://" in decoded or decoded.lower().startswith(("http:", "https:")):
        return False
    segments = decoded.split("/")
    return not any(segment in (".", "..") for segment in segments)


def walk(value: object):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


class SchemaAndFixtureTests(unittest.TestCase):
    def test_schema_is_draft_2020_12_valid(self) -> None:
        Draft202012Validator.check_schema(SCHEMA)
        self.assertEqual("dd-workflow.v2", SCHEMA["$defs"]["ContractVersion"]["const"])
        self.assertEqual("dd-workflow.v2-be0.4", SCHEMA["$defs"]["FixtureVersion"]["const"])

    def test_every_manifest_fixture_validates(self) -> None:
        for fixture in MANIFEST["fixtures"]:
            with self.subTest(path=fixture["path"], schema_ref=fixture["schemaRef"]):
                assert_valid(self, load_json(fixture["path"]), fixture["schemaRef"])

    def test_success_dictionary_envelopes_have_access_metadata(self) -> None:
        for fixture in MANIFEST["fixtures"]:
            if fixture["schemaRef"] == "#/$defs/StandardErrorResponse":
                continue
            value = load_json(fixture["path"])
            self.assertIn("_access", value, fixture["path"])
            self.assertEqual("deny-by-default", value["_access"]["policy"])

    def test_unit_interval_and_triage_boundaries(self) -> None:
        unit = validator_for("#/$defs/UnitInterval")
        for value in (None, 0, 0.5, 1):
            self.assertTrue(unit.is_valid(value), value)
        for value in (-0.0001, 1.0001, "0.5"):
            self.assertFalse(unit.is_valid(value), value)

        triage = validator_for("#/$defs/TriageScore")
        for value in (None, 0, 50, 100):
            self.assertTrue(triage.is_valid(value), value)
        for value in (-1, 101, 10.5):
            self.assertFalse(triage.is_valid(value), value)

    def test_masking_tristate_and_negative_combinations(self) -> None:
        identifier_validator = validator_for("#/$defs/IdentifierDisplay")
        identifiers = load_json("fixtures/case-detail.json")["case"]["intake"]["identifiers"]
        self.assertEqual({(False, False), (True, False), (False, True)}, {
            (identifier["masked"], identifier["omitted"]) for identifier in identifiers
        })
        for identifier in identifiers:
            self.assertTrue(identifier_validator.is_valid(identifier))

        contradictory = copy.deepcopy(identifiers[1])
        contradictory["omitted"] = True
        self.assertFalse(identifier_validator.is_valid(contradictory))

        queue_subject_validator = validator_for("#/$defs/QueueSubject")
        queue_subjects = [item["subject"] for item in load_json("fixtures/queue.json")["items"]]
        self.assertEqual({(False, False), (True, False), (False, True)}, {
            (subject["masked"], subject["omitted"]) for subject in queue_subjects
        })
        for subject in queue_subjects:
            self.assertTrue(queue_subject_validator.is_valid(subject))

    def test_georgian_and_latin_aliases_round_trip(self) -> None:
        aliases = load_json("fixtures/case-detail.json")["case"]["intake"]["aliases"]
        self.assertEqual("სატესტო ორგანიზაცია", aliases[0]["value"])
        self.assertEqual("Geor", aliases[0]["script"])
        self.assertEqual("Satesto Organizatsia", aliases[1]["value"])
        self.assertEqual("Latn", aliases[1]["script"])


class ConnectorSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runs = load_json("fixtures/connector-runs-list.json")["items"]
        self.by_status = {run["status"]: run for run in self.runs}

    def test_all_execution_states_and_result_count_semantics(self) -> None:
        self.assertEqual(
            {"complete", "partial", "zero_results", "unavailable", "permission_required", "error"},
            set(self.by_status),
        )
        self.assertGreater(self.by_status["complete"]["resultCount"], 0)
        self.assertEqual(0, self.by_status["zero_results"]["resultCount"])
        for status in ("unavailable", "permission_required", "error"):
            self.assertIsNone(self.by_status[status]["resultCount"])

    def test_zero_is_only_affirmative_zero_results(self) -> None:
        run_validator = validator_for("#/$defs/ConnectorRun")
        zero = self.by_status["zero_results"]
        self.assertTrue(run_validator.is_valid(zero))

        invalid_zero = copy.deepcopy(zero)
        invalid_zero["resultCount"] = None
        self.assertFalse(run_validator.is_valid(invalid_zero))

        invalid_complete = copy.deepcopy(self.by_status["complete"])
        invalid_complete["resultCount"] = 0
        self.assertFalse(run_validator.is_valid(invalid_complete))

        invalid_error = copy.deepcopy(self.by_status["error"])
        invalid_error["resultCount"] = 0
        self.assertFalse(run_validator.is_valid(invalid_error))

    def test_partial_and_freshness_are_independent(self) -> None:
        partial = self.by_status["partial"]
        self.assertEqual("stale", partial["freshness"]["state"])
        self.assertEqual("RESULT_LIMIT_REACHED", partial["partialReason"]["code"])
        self.assertIsNone(partial["failure"])

        invalid = copy.deepcopy(partial)
        invalid["partialReason"] = None
        self.assertFalse(validator_for("#/$defs/ConnectorRun").is_valid(invalid))

    def test_failure_is_error_only_and_required_for_terminal_failures(self) -> None:
        for status in ("complete", "zero_results"):
            self.assertIsNone(self.by_status[status]["failure"])
        for status in ("unavailable", "permission_required", "error"):
            self.assertIsNotNone(self.by_status[status]["failure"])

        invalid = copy.deepcopy(self.by_status["unavailable"])
        invalid["failure"] = None
        self.assertFalse(validator_for("#/$defs/ConnectorRun").is_valid(invalid))

    def test_never_run_invariants_and_coverage_denominator(self) -> None:
        states = load_json("fixtures/connectors-list.json")["items"]
        never_run = [state for state in states if state["neverRun"]]
        self.assertEqual(2, len(never_run))
        for state in never_run:
            for field in ("latestRunId", "latestExecutionStatus", "lastAttemptAt", "lastSuccessAt", "sourceUpdatedAt", "retryAction"):
                self.assertIsNone(state[field], (state["connectorId"], field))
            self.assertEqual("unknown", state["freshness"]["state"])
        selected_required = next(state for state in never_run if state["selected"])
        eligible_unselected = next(state for state in never_run if not state["selected"])
        self.assertTrue(selected_required["reducedCoverage"])
        self.assertTrue(selected_required["blocking"])
        self.assertEqual("start_connector", selected_required["availableActions"][0]["actionCode"])
        self.assertFalse(eligible_unselected["reducedCoverage"])
        self.assertFalse(eligible_unselected["blocking"])


class RouteAndActionTests(unittest.TestCase):
    def test_safe_route_schema_and_decoded_canonicalization(self) -> None:
        schema_validator = validator_for("#/$defs/SafeRelativePath")
        self.assertTrue(schema_validator.is_valid("/due-diligence/cases/synthetic"))
        for unsafe in ("//evil.example/path", "/path\\child", "/path?token=x", "/path#fragment", "https://evil.example"):
            self.assertFalse(schema_validator.is_valid(unsafe), unsafe)

        for unsafe_encoded in (
            "/%2f%2fevil.example/path",
            "/%252f%252fevil.example/path",
            "/safe/%2e%2e/private",
            "/safe/%252e%252e/private",
            "/safe%5cprivate",
            "/safe%0aprivate",
        ):
            self.assertFalse(decoded_safe_relative_path(unsafe_encoded), unsafe_encoded)

    def test_all_fixture_actions_use_safe_routes_and_security_flags(self) -> None:
        for fixture in MANIFEST["fixtures"]:
            value = load_json(fixture["path"])
            for candidate in walk(value):
                if not isinstance(candidate, dict) or "actionCode" not in candidate or "method" not in candidate:
                    continue
                route = candidate.get("route")
                if route is not None:
                    self.assertTrue(decoded_safe_relative_path(route), (fixture["path"], route))
                if candidate["method"] == "GET":
                    self.assertFalse(candidate["requiresCsrf"])
                    self.assertFalse(candidate["requiresIdempotency"])
                else:
                    self.assertIsNotNone(route)
                    self.assertTrue(candidate["requiresCsrf"])
                    self.assertTrue(candidate["requiresIdempotency"])


class OrderingAndReportTests(unittest.TestCase):
    def test_queue_case_id_is_stable_tie_breaker(self) -> None:
        items = load_json("fixtures/queue.json")["items"]
        tied = [item for item in items if item["lastActivityAt"] == "2026-08-07T10:00:00+04:00"]
        self.assertEqual(sorted(item["caseId"] for item in tied), [item["caseId"] for item in tied])

    def test_legacy_null_report_sorts_last_without_fabricated_attestation(self) -> None:
        items = load_json("fixtures/reports-list.json")["items"]
        self.assertIsNotNone(items[0]["createdAt"])
        self.assertIsNone(items[-1]["createdAt"])
        self.assertIsNone(items[-1]["createdBy"])
        self.assertEqual("v1_legacy", items[-1]["schemaOrigin"])

    def test_report_fixture_covers_every_enum_and_deep_link(self) -> None:
        points = load_json("fixtures/report-detail.json")["snapshot"]["summaryPoints"]
        expected_natures = set(SCHEMA["$defs"]["SummaryPoint"]["properties"]["nature"]["enum"])
        expected_verification = set(SCHEMA["$defs"]["SummaryPoint"]["properties"]["verificationState"]["enum"])
        expected_targets = set(SCHEMA["$defs"]["DeepLinkTarget"]["properties"]["type"]["enum"])
        self.assertEqual(expected_natures, {point["nature"] for point in points})
        self.assertEqual(expected_verification, {point["verificationState"] for point in points})
        self.assertEqual(expected_targets, {point["target"]["type"] for point in points if point["target"]})


class OpenApiAndFreezeTests(unittest.TestCase):
    def test_openapi_is_read_only_except_explicit_non_executable_draft(self) -> None:
        self.assertEqual("3.1.0", OPENAPI["openapi"])
        self.assertFalse(OPENAPI["x-runtime-behavior-changed"])
        for path, path_item in OPENAPI["paths"].items():
            for method, operation in path_item.items():
                if method == "parameters":
                    continue
                with self.subTest(path=path, method=method):
                    if method == "post":
                        self.assertEqual("draft-be1+", operation["x-contract-status"])
                        self.assertFalse(operation["x-executable"])
                        self.assertNotIn("requestBody", operation)
                    else:
                        self.assertEqual("get", method)

    def test_all_openapi_external_examples_exist_and_are_manifested(self) -> None:
        manifest_paths = {fixture["path"] for fixture in MANIFEST["fixtures"]}
        external_values = []
        for candidate in walk(OPENAPI):
            if isinstance(candidate, dict) and "externalValue" in candidate:
                external_values.append(candidate["externalValue"].removeprefix("./"))
        self.assertTrue(external_values)
        self.assertEqual(set(external_values), manifest_paths)
        for path in external_values:
            self.assertTrue((ROOT / path).is_file(), path)

    def test_pack_contains_only_synthetic_fixture_identity_data(self) -> None:
        fixture_text = "\n".join(
            (ROOT / fixture["path"]).read_text(encoding="utf-8") for fixture in MANIFEST["fixtures"]
        )
        self.assertNotIn("@", fixture_text)
        self.assertNotRegex(fixture_text, re.compile(r"\bBearer\s+[A-Za-z0-9._-]+", re.IGNORECASE))
        self.assertNotRegex(fixture_text, re.compile(r"\b(?:sk|ghp)_[A-Za-z0-9]{10,}"))
        self.assertNotIn("client_secret", fixture_text.lower())

    def test_freeze_hash(self) -> None:
        aggregate = hashlib.sha256()
        for relative_path in sorted(MANIFEST["freezeFiles"]):
            file_path = ROOT / relative_path
            self.assertTrue(file_path.is_file(), relative_path)
            file_digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            aggregate.update(relative_path.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(file_digest.encode("ascii"))
            aggregate.update(b"\n")
        expected = (ROOT / "FREEZE.sha256").read_text(encoding="ascii").strip()
        self.assertEqual(expected, aggregate.hexdigest())


if __name__ == "__main__":
    unittest.main()
