"""Tests for POST /due-diligence/cases/{case_id}/full-check.

The full check runs every due-diligence source in one call. The contract the
tests below defend:

* an unconfigured or permission-blocked source never raises and is never
  silently dropped from the response;
* the endpoint never fabricates demo entities carrying the subject's name;
* the consolidated summary aggregates per-source hit counts correctly.

No test touches the network: every external call is mocked.
"""

import os
import unittest
from unittest.mock import patch

from deliberation.api.app.core.config import get_settings
from deliberation.api.app.routes_due_diligence import (
    FULL_CHECK_SOURCE_LABELS,
    AssetDeclarationResult,
    DueDiligenceFullCheckRequest,
    NewsResult,
    OpenSanctionsResult,
    WikidataResult,
    WikipediaResult,
    run_due_diligence_full_check,
)

MODULE = "deliberation.api.app.routes_due_diligence"

CASE_ROW = {
    "caseId": "case-full-check",
    "subject": "Example Subject",
    "subjectGeorgian": "",
    "subjectEnglish": "Example Subject",
    "subjectType": "Person",
}

# Minimal environment: no OPENSANCTIONS_API_KEY, no APIFY_API_TOKEN, and no
# FS_COMPANYINFO_* flags, i.e. exactly the operator's default state.
UNCONFIGURED_ENV = {
    "FS_AUTH_ENABLED": "0",
    "FS_SESSION_SECRET": "s" * 48,
    "FS_COMPLIANCE_HASH_KEY": "c" * 48,
}


class FullCheckTestBase(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    def _run(
        self,
        env=None,
        *,
        wikidata=None,
        wikipedia=None,
        opensanctions=None,
        news=None,
        declarations=None,
        media=None,
        identification_codes=None,
        facebook_snapshot=None,
        payload=None,
        extra_patches=None,
    ):
        """Call the handler with every external dependency mocked out."""
        environment = dict(UNCONFIGURED_ENV)
        environment.update(env or {})

        opensanctions_return = (
            (list(opensanctions), None)
            if opensanctions is not None
            else None  # fall through to the real, unconfigured code path
        )

        patches = [
            patch(f"{MODULE}._case_and_report_for_graph", return_value=(dict(CASE_ROW), {})),
            patch(f"{MODULE}._wikidata_search", return_value=(list(wikidata or []), None)),
            patch(f"{MODULE}._wikipedia_search", return_value=(list(wikipedia or []), None)),
            patch(f"{MODULE}._gdelt_news_search", return_value=(list(news or []), None)),
            patch(f"{MODULE}._local_media_news_search", return_value=([], [])),
            patch(
                f"{MODULE}._asset_declaration_search",
                return_value=(list(declarations or []), None),
            ),
            patch(f"{MODULE}._run_media_monitor", return_value=media or {"mentions": [], "sources": []}),
            patch(f"{MODULE}._prepare_dd_ai_report", return_value=None),
            patch(f"{MODULE}._store_dd_report", return_value=(None, None)),
            patch(
                f"{MODULE}._full_check_identification_codes",
                return_value=list(identification_codes or []),
            ),
            patch(
                f"{MODULE}._full_check_facebook_snapshot",
                return_value=facebook_snapshot
                or {"entityCount": 0, "evidenceCount": 0},
            ),
        ]
        if opensanctions_return is not None:
            patches.append(
                patch(f"{MODULE}._opensanctions_search", return_value=opensanctions_return)
            )
        patches.extend(extra_patches or [])

        with patch.dict(os.environ, environment, clear=True):
            get_settings.cache_clear()
            with self._nested(patches):
                return run_due_diligence_full_check(CASE_ROW["caseId"], payload)

    class _Nested:
        def __init__(self, patches):
            self.patches = patches

        def __enter__(self):
            self.started = [item.start() for item in self.patches]
            return self.started

        def __exit__(self, *exc_info):
            for item in reversed(self.patches):
                item.stop()
            return False

    def _nested(self, patches):
        return self._Nested(patches)

    @staticmethod
    def _by_id(response):
        return {row["id"]: row for row in response["sources"]}


class UnconfiguredSourcesTests(FullCheckTestBase):
    def test_unconfigured_sources_do_not_raise_and_are_never_omitted(self):
        response = self._run()

        by_id = self._by_id(response)
        self.assertEqual(
            sorted(by_id), sorted(FULL_CHECK_SOURCE_LABELS)
        )  # every source is present, none silently dropped
        for source_id, row in by_id.items():
            self.assertIn(
                row["status"],
                {"ok", "no-data", "not-configured", "blocked", "error"},
                msg=source_id,
            )
            self.assertTrue(row["detail"].strip(), msg=source_id)
            self.assertIsInstance(row["hitCount"], int, msg=source_id)
            self.assertIsInstance(row["requiresConfiguration"], bool, msg=source_id)
            self.assertTrue(row["label"].strip(), msg=source_id)

    def test_missing_opensanctions_key_is_reported_as_not_configured(self):
        row = self._by_id(self._run())["opensanctions"]
        self.assertEqual(row["status"], "not-configured")
        self.assertTrue(row["requiresConfiguration"])
        self.assertIn("OPENSANCTIONS_API_KEY", row["detail"])

    def test_company_registry_permission_gate_is_reported_as_blocked(self):
        row = self._by_id(self._run())["company-registry"]
        self.assertEqual(row["status"], "blocked")
        self.assertTrue(row["requiresConfiguration"])
        self.assertIn("FS_COMPANYINFO_ENABLED", row["detail"])
        self.assertIn("FS_COMPANYINFO_PERMISSION_ACKNOWLEDGED", row["detail"])

    def test_missing_apify_token_is_reported_as_not_configured(self):
        row = self._by_id(self._run())["facebook"]
        self.assertEqual(row["status"], "not-configured")
        self.assertTrue(row["requiresConfiguration"])
        self.assertIn("APIFY_API_TOKEN", row["detail"])

    def test_company_registry_without_identification_code_is_no_data(self):
        """Permission granted, but the case has no identification code."""
        with patch(
            "deliberation.api.app.investigation_companyinfo.enrich_company_from_companyinfo"
        ) as enrich:
            response = self._run(
                env={
                    "FS_COMPANYINFO_ENABLED": "1",
                    "FS_COMPANYINFO_PERMISSION_ACKNOWLEDGED": "1",
                },
                identification_codes=[],
            )
        row = self._by_id(response)["company-registry"]
        self.assertEqual(row["status"], "no-data")
        self.assertEqual(row["hitCount"], 0)
        self.assertIn("identification code", row["detail"].casefold())
        enrich.assert_not_called()  # no code was invented to force a lookup

    def test_empty_result_notice_is_no_data_not_error(self):
        """"Nothing matched" is data, not a failure."""
        quiet = patch(
            f"{MODULE}._local_media_news_search",
            return_value=(
                [],
                ["Interpressnews search returned no extractable matches for the subject."],
            ),
        )
        row = self._by_id(self._run(extra_patches=[quiet]))["georgian-media"]
        self.assertEqual(row["status"], "no-data")
        self.assertEqual(row["hitCount"], 0)

    def test_upstream_failure_notice_is_reported_as_error(self):
        rate_limited = patch(
            f"{MODULE}._gdelt_news_search",
            return_value=([], "GDELT is temporarily rate-limiting requests (429)."),
        )
        row = self._by_id(self._run(extra_patches=[rate_limited]))["news"]
        self.assertEqual(row["status"], "error")
        self.assertIn("GDELT", row["detail"])

    def test_core_analysis_failure_does_not_fail_the_call(self):
        boom = patch(f"{MODULE}._wikidata_search", side_effect=RuntimeError("upstream down"))
        response = self._run(extra_patches=[boom])
        by_id = self._by_id(response)
        self.assertEqual(sorted(by_id), sorted(FULL_CHECK_SOURCE_LABELS))
        self.assertEqual(by_id["wikidata"]["status"], "error")
        # Sources that do not depend on the failed analysis still report honestly.
        self.assertEqual(by_id["facebook"]["status"], "not-configured")


class NoFabricatedDataTests(FullCheckTestBase):
    def test_demo_generator_is_never_invoked(self):
        guard = patch(
            f"{MODULE}._demo_results",
            side_effect=AssertionError("full-check must never fabricate demo entities"),
        )
        response = self._run(extra_patches=[guard])
        self.assertFalse(response["demo"])
        self.assertFalse(response["summary"]["demo"])
        self.assertEqual(response["results"]["opensanctions"], [])
        self.assertEqual(response["results"]["wikidata"], [])
        self.assertEqual(response["results"]["news"], [])

    def test_request_model_has_no_demo_switch(self):
        self.assertNotIn("demo", DueDiligenceFullCheckRequest.model_fields)
        # A client sending demo=true cannot turn fabrication on.
        request = DueDiligenceFullCheckRequest(**{"demo": True})
        self.assertFalse(getattr(request, "demo", False))

    def test_stored_report_is_not_flagged_as_demo(self):
        store = patch(f"{MODULE}._store_dd_report", return_value=("report-1", "2026-08-09T00:00:00Z"))
        guard = patch(
            f"{MODULE}._demo_results",
            side_effect=AssertionError("full-check must never fabricate demo entities"),
        )
        graph = patch(f"{MODULE}._build_investigation_graph_bundle", return_value={})
        persist = patch(f"{MODULE}._persist_investigation_graph_bundle", return_value=None)
        with patch.dict(os.environ, dict(UNCONFIGURED_ENV), clear=True):
            get_settings.cache_clear()
            with self._nested(
                [
                    patch(f"{MODULE}._case_and_report_for_graph", return_value=(dict(CASE_ROW), {})),
                    patch(f"{MODULE}._wikidata_search", return_value=([], None)),
                    patch(f"{MODULE}._wikipedia_search", return_value=([], None)),
                    patch(f"{MODULE}._gdelt_news_search", return_value=([], None)),
                    patch(f"{MODULE}._local_media_news_search", return_value=([], [])),
                    patch(f"{MODULE}._asset_declaration_search", return_value=([], None)),
                    patch(f"{MODULE}._run_media_monitor", return_value={"mentions": [], "sources": []}),
                    patch(f"{MODULE}._prepare_dd_ai_report", return_value=None),
                    patch(f"{MODULE}._full_check_identification_codes", return_value=[]),
                    patch(f"{MODULE}._full_check_facebook_snapshot", return_value={"entityCount": 0, "evidenceCount": 0}),
                    store,
                    guard,
                    graph,
                    persist,
                ]
            ) as started:
                response = run_due_diligence_full_check(CASE_ROW["caseId"], None)
        store_mock = started[-4]
        self.assertEqual(response["reportId"], "report-1")
        self.assertIs(store_mock.call_args.kwargs["is_demo"], False)


class NoPaidApifyRunTests(FullCheckTestBase):
    def test_full_check_never_starts_a_managed_apify_run(self):
        starter = patch("deliberation.api.app.investigation_social._start_apify_actor")
        headers = patch(
            "deliberation.api.app.investigation_social._apify_headers",
            side_effect=AssertionError("full-check must not call Apify"),
        )
        with self._nested([starter, headers]) as started:
            response = self._run()
        started[0].assert_not_called()
        facebook = response["results"]["facebook"]
        self.assertIs(facebook["startedPaidRun"], False)
        self.assertEqual(facebook["mode"], "read-only")
        self.assertFalse(facebook["managedStartsEnabled"])


class SummaryAggregationTests(FullCheckTestBase):
    def test_summary_aggregates_hit_counts_across_every_source(self):
        response = self._run(
            env={"APIFY_API_TOKEN": "token-not-used-offline"},
            wikidata=[
                WikidataResult(id="Q1", label="A"),
                WikidataResult(id="Q2", label="B"),
            ],
            wikipedia=[WikipediaResult(title="A", url="https://example.invalid/a")],
            opensanctions=[
                OpenSanctionsResult(id="e1", name="A", topics=["role.pep"]),
                OpenSanctionsResult(id="e2", name="B", topics=[]),
                OpenSanctionsResult(id="e3", name="C", topics=[]),
            ],
            news=[
                NewsResult(title=f"N{index}", url=f"https://example.invalid/{index}")
                for index in range(4)
            ],
            declarations=[AssetDeclarationResult(id="d1", name="A")],
            media={"mentions": [{"title": f"M{index}"} for index in range(5)], "sources": []},
            facebook_snapshot={"entityCount": 2, "evidenceCount": 3},
        )

        summary = response["summary"]
        self.assertEqual(
            summary["sourceHitCounts"],
            {
                "wikidata": 2,
                "wikipedia": 1,
                "opensanctions": 3,
                "news": 4,
                "declarations": 1,
                "georgian-media": 5,
                "company-registry": 0,
                "facebook": 5,
            },
        )
        # Grand total across all eight sources.
        self.assertEqual(summary["totalHits"], 21)
        # The six sources driven by /analyze.
        self.assertEqual(summary["coreTotalHits"], 16)
        self.assertEqual(summary["coreTotalHits"], summary["total_hits"])
        self.assertEqual(summary["sourcesChecked"], len(FULL_CHECK_SOURCE_LABELS))
        self.assertEqual(summary["totalHits"], sum(row["hitCount"] for row in response["sources"]))

        by_id = self._by_id(response)
        self.assertEqual(by_id["facebook"]["status"], "ok")
        self.assertEqual(by_id["facebook"]["hitCount"], 5)
        self.assertEqual(by_id["opensanctions"]["status"], "ok")
        self.assertEqual(by_id["company-registry"]["status"], "blocked")

        self.assertEqual(summary["sourceStatusCounts"]["ok"], 7)
        self.assertEqual(summary["sourceStatusCounts"]["blocked"], 1)
        self.assertEqual(summary["sourceStatusCounts"]["no-data"], 0)
        self.assertEqual(summary["sourcesWithData"], 7)
        self.assertEqual(summary["sourcesRequiringConfiguration"], 1)
        self.assertIn(summary["riskLevel"], {"Unknown", "Low", "Medium", "High"})
        self.assertIsInstance(summary["riskScore"], int)

    def test_status_counts_sum_to_the_number_of_sources(self):
        response = self._run()
        summary = response["summary"]
        self.assertEqual(
            sum(summary["sourceStatusCounts"].values()), len(response["sources"])
        )
        self.assertEqual(len(response["sources"]), len(FULL_CHECK_SOURCE_LABELS))


if __name__ == "__main__":
    unittest.main()
