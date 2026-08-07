import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from deliberation.api.app.investigation_ftm import (
    _fallback_resolution_evaluation,
    _projection_rows,
)
from deliberation.api.app.investigation_social import (
    APIFY_ACTOR_PUBLIC_URL,
    DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
    DEFAULT_APIFY_FACEBOOK_ACTOR_NAME,
    ApifyFacebookImportRequest,
    ApifyFacebookStartRequest,
    ApifyRetentionCleanupRequest,
    _fetch_apify_items,
    _fetch_dataset_items,
    _filter_actor_items,
    _require_succeeded_run,
    _resolve_actor,
    _start_apify_actor,
    build_apify_facebook_bundle,
    get_apify_facebook_connector_capabilities,
)


class TestInvestigationSocialImport(unittest.TestCase):
    def _items(self):
        return [
            {
                "id": "post-100",
                "url": "https://www.facebook.com/groups/group-77/posts/post-100",
                "inputUrl": "https://www.facebook.com/groups/group-77",
                "groupTitle": "City procurement watch",
                "time": "2026-08-01T12:00:00Z",
                "user": {"id": "profile-42", "name": "J. Example"},
                "text": "Photographs from the public meeting.",
                "likesCount": 5,
                "sharesCount": 2,
                "commentsCount": 1,
                "reactions": {"LIKE": 4, "WOW": 1},
                "topComments": [
                    {
                        "id": "comment-9",
                        "profileId": "profile-84",
                        "profileName": "Public Observer",
                        "profileUrl": "https://www.facebook.com/profile.php?id=profile-84",
                        "commentUrl": "https://www.facebook.com/groups/group-77/posts/post-100?comment_id=comment-9",
                        "date": "2026-08-01T13:00:00Z",
                        "text": "Can the contract be published?",
                        "likesCount": 3,
                    }
                ],
            },
            {
                "id": "post-101",
                "url": "https://www.facebook.com/groups/group-77/posts/post-101",
                "inputUrl": "https://www.facebook.com/groups/group-77",
                "groupTitle": "City procurement watch",
                "time": "2026-08-02T12:00:00Z",
                "user": {"id": "profile-42", "name": "Jane Example"},
                "text": "A second public post.",
            },
        ]

    def test_request_requires_one_input_and_investigative_basis(self):
        with self.assertRaises(ValidationError):
            ApifyFacebookImportRequest.model_validate(
                {
                    "items": [],
                    "datasetId": "dataset-1",
                    "lawfulBasis": "Public interest investigation",
                    "investigationPurpose": "Review public procurement links",
                }
            )

    def test_bundle_is_source_scoped_and_evidence_bearing(self):
        bundle, metrics = build_apify_facebook_bundle(
            case_id="case-1",
            root_entity_id="root-1",
            actor_id=DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
            items=self._items(),
            lawful_basis="Public interest anti-corruption investigation",
            investigation_purpose="Review public procurement relationships",
            retention_days=90,
            include_top_comments=True,
            promote_posts_to_graph=True,
            run_id="run-1",
            dataset_id="dataset-1",
        )
        entity_types = [row["entityType"] for row in bundle["entities"]]
        self.assertEqual(entity_types.count("Social group"), 1)
        self.assertEqual(entity_types.count("Social post"), 2)
        self.assertEqual(entity_types.count("Social comment"), 1)
        self.assertEqual(entity_types.count("Social profile"), 2)
        author = next(
            row
            for row in bundle["entities"]
            if row["entityType"] == "Social profile"
            and row["platformProfileId"] == "profile-42"
        )
        self.assertEqual(author["identityStatus"], "unresolved")
        self.assertEqual(author["ftmSchema"], "Person")
        self.assertEqual(author["sourceId"], metrics["sourceId"])
        self.assertEqual(set(author["aliases"]), {"J. Example", "Jane Example"})
        self.assertTrue(all(row.get("rawRecordChecksum") for row in bundle["evidence"]))
        self.assertTrue(all(row.get("retentionExpiresAt") for row in bundle["evidence"]))
        self.assertEqual(metrics["itemsAccepted"], 2)
        self.assertEqual(metrics["itemsRejected"], 0)
        self.assertEqual(
            bundle["sources"][0]["actorName"], DEFAULT_APIFY_FACEBOOK_ACTOR_NAME
        )
        self.assertEqual(bundle["sources"][0]["url"], APIFY_ACTOR_PUBLIC_URL)
        self.assertEqual(metrics["actor"]["schemaVersion"], "apify-facebook-public-groups-v2")

        statements, aliases = _projection_rows(bundle)
        social_aliases = [
            row for row in aliases if row["entityId"] == author["entityId"]
        ]
        self.assertTrue(social_aliases)
        self.assertTrue(
            all(row["aliasType"] == "social-display" for row in social_aliases)
        )
        self.assertTrue(
            any(row["predicate"] == "Person:idNumber" for row in statements)
        )

    def test_same_display_name_without_platform_id_is_not_cross_group_merged(self):
        items = [
            {
                "id": "post-a",
                "inputUrl": "https://www.facebook.com/groups/a",
                "groupTitle": "Group A",
                "user": {"name": "Shared Name"},
                "text": "One",
            },
            {
                "id": "post-b",
                "inputUrl": "https://www.facebook.com/groups/b",
                "groupTitle": "Group B",
                "user": {"name": "Shared Name"},
                "text": "Two",
            },
        ]
        bundle, _ = build_apify_facebook_bundle(
            case_id="case-1",
            root_entity_id="root-1",
            actor_id=DEFAULT_APIFY_FACEBOOK_ACTOR_ID,
            items=items,
            lawful_basis="Public interest investigation",
            investigation_purpose="Compare public source records",
            retention_days=30,
            include_top_comments=False,
            promote_posts_to_graph=True,
        )
        profiles = [
            row for row in bundle["entities"] if row["entityType"] == "Social profile"
        ]
        self.assertEqual(len(profiles), 2)
        self.assertNotEqual(profiles[0]["entityId"], profiles[1]["entityId"])

    def test_shared_identifier_is_a_candidate_signal_not_an_automatic_merge(self):
        score, signals, conflicts, engine = _fallback_resolution_evaluation(
            {"id": "person-1", "type": "Person", "properties": {}},
            {"id": "profile-1", "type": "Social profile", "properties": {}},
            set(),
            {"identifier": {"facebookprofile42"}},
        )
        self.assertGreaterEqual(score, 0.95)
        self.assertEqual(engine, "evidence-rule-v1")
        self.assertTrue(any(row["type"] == "shared-identifier" for row in signals))
        self.assertFalse(any(row["type"] == "schema-conflict" for row in conflicts))

    def test_actor_registry_defaults_to_official_and_blocks_unknown(self):
        actor = _resolve_actor(DEFAULT_APIFY_FACEBOOK_ACTOR_ID, for_start=True)
        self.assertEqual(actor["name"], "apify/facebook-groups-scraper")
        self.assertTrue(actor["startAllowed"])
        legacy = _resolve_actor("2chN8UQcH1CfxLRNE")
        self.assertFalse(legacy["startAllowed"])
        with self.assertRaises(HTTPException) as caught:
            _resolve_actor("untrusted/actor")
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail["code"], "APIFY_ACTOR_NOT_ALLOWLISTED")

    def test_only_succeeded_runs_are_importable(self):
        with self.assertRaises(HTTPException) as running:
            _require_succeeded_run({"status": "RUNNING"})
        self.assertEqual(running.exception.status_code, 409)
        self.assertEqual(running.exception.detail["code"], "APIFY_RUN_NOT_READY")
        self.assertTrue(running.exception.detail["retryable"])
        with self.assertRaises(HTTPException) as failed:
            _require_succeeded_run({"status": "FAILED"})
        self.assertEqual(failed.exception.detail["code"], "APIFY_RUN_NOT_IMPORTABLE")
        self.assertFalse(failed.exception.detail["retryable"])
        _require_succeeded_run({"status": "SUCCEEDED"})

    def test_schema_filter_rejects_diagnostics_and_invalid_nested_shapes(self):
        rows, reasons = _filter_actor_items(
            [
                {"id": "post-1", "text": "ok"},
                {"error": "blocked", "message": "diagnostic"},
                {"id": "post-2", "topComments": {"wrong": "shape"}},
                "not-an-object",
            ]
        )
        self.assertEqual([row["id"] for row in rows], ["post-1"])
        self.assertEqual(reasons["diagnostic-or-error-row"], 1)
        self.assertEqual(reasons["invalid-topComments-shape"], 1)
        self.assertEqual(reasons["non-object-row"], 1)

    @patch("deliberation.api.app.investigation_social._fetch_dataset_items")
    @patch("deliberation.api.app.investigation_social._fetch_dataset_data")
    @patch("deliberation.api.app.investigation_social._verify_actor_identity")
    @patch("deliberation.api.app.investigation_social._fetch_run_data")
    def test_run_import_captures_schema_rejections_and_truncation(
        self, fetch_run, verify_actor, fetch_dataset, fetch_items
    ):
        fetch_run.return_value = {
            "id": "run-1",
            "status": "SUCCEEDED",
            "actId": "resolved-actor",
            "defaultDatasetId": "dataset-1",
            "buildId": "build-1",
            "buildNumber": "1.2.3",
            "pricingInfo": {"pricingModel": "PAY_PER_EVENT"},
            "chargedEventCounts": {"data-extracted": 3},
            "usageTotalUsd": 0.12,
            "options": {"maxItems": 3, "maxTotalChargeUsd": 0.5},
        }
        verify_actor.return_value = {"resolvedActorId": "resolved-actor"}
        fetch_dataset.return_value = {
            "id": "dataset-1",
            "itemCount": 4,
            "cleanItemCount": 4,
        }
        fetch_items.return_value = (
            [
                {"id": "post-1", "text": "one"},
                {"error": "diagnostic"},
                {"id": "post-2", "text": "two"},
                {"id": "post-3", "text": "three"},
            ],
            {"fetchPageCount": 2, "rawItemsFetched": 4, "sourceTotalItems": 4},
        )
        payload = ApifyFacebookImportRequest.model_validate(
            {
                "runId": "run-1",
                "maxItems": 2,
                "lawfulBasis": "Public interest investigation",
                "investigationPurpose": "Review public procurement relationships",
            }
        )
        items, run_id, dataset_id, metadata = _fetch_apify_items(payload)
        self.assertEqual([row["id"] for row in items], ["post-1", "post-2"])
        self.assertEqual(run_id, "run-1")
        self.assertEqual(dataset_id, "dataset-1")
        self.assertEqual(metadata["schemaRejectedItems"], 1)
        self.assertTrue(metadata["truncated"])
        self.assertEqual(metadata["actorRun"]["chargedItemCount"], 3)
        self.assertEqual(metadata["actorRun"]["actorBuildNumber"], "1.2.3")

    @patch("deliberation.api.app.investigation_social._apify_get_json")
    def test_dataset_fetch_uses_offset_pagination(self, get_json):
        first_page = [{"id": f"post-{index}"} for index in range(250)]
        second_page = [{"id": f"post-{index}"} for index in range(250, 301)]
        get_json.side_effect = [
            (first_page, {"X-Apify-Pagination-Total": "400"}),
            (second_page, {"X-Apify-Pagination-Total": "400"}),
        ]
        rows, metadata = _fetch_dataset_items("dataset-1", max_items=300, source_total=400)
        self.assertEqual(len(rows), 301)
        self.assertEqual(metadata["fetchPageCount"], 2)
        self.assertEqual(get_json.call_args_list[1].kwargs["params"]["offset"], 250)

    def test_managed_start_accepts_only_public_group_urls(self):
        with self.assertRaises(ValidationError):
            ApifyFacebookStartRequest.model_validate(
                {
                    "groupUrls": ["https://www.facebook.com/profile.php?id=1"],
                    "lawfulBasis": "Public interest investigation",
                    "investigationPurpose": "Review public procurement relationships",
                }
            )
        payload = ApifyFacebookStartRequest.model_validate(
            {
                "groupUrls": ["https://facebook.com/groups/public-watch/posts/99"],
                "lawfulBasis": "Public interest investigation",
                "investigationPurpose": "Review public procurement relationships",
            }
        )
        self.assertEqual(
            payload.group_urls, ["https://www.facebook.com/groups/public-watch"]
        )

    @patch("deliberation.api.app.investigation_social.requests.post")
    @patch("deliberation.api.app.investigation_social._apify_headers")
    @patch("deliberation.api.app.investigation_social._actor_details")
    def test_managed_start_sends_both_item_and_charge_caps(
        self, actor_details, headers, post
    ):
        actor_details.return_value = {"resolvedActorId": "resolved-actor"}
        headers.return_value = {"Authorization": "Bearer secret"}
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": {
                "id": "run-1",
                "actId": "resolved-actor",
                "status": "RUNNING",
            }
        }
        post.return_value = response
        payload = ApifyFacebookStartRequest.model_validate(
            {
                "groupUrls": ["https://www.facebook.com/groups/public-watch"],
                "maxItems": 50,
                "maxTotalChargeUsd": 0.75,
                "lawfulBasis": "Public interest investigation",
                "investigationPurpose": "Review public procurement relationships",
            }
        )
        _start_apify_actor(_resolve_actor(DEFAULT_APIFY_FACEBOOK_ACTOR_ID), payload)
        request = post.call_args
        self.assertEqual(request.kwargs["params"]["maxItems"], 50)
        self.assertEqual(request.kwargs["params"]["maxTotalChargeUsd"], 0.75)
        self.assertEqual(request.kwargs["json"]["resultsLimit"], 50)
        self.assertEqual(
            request.kwargs["json"]["startUrls"],
            [{"url": "https://www.facebook.com/groups/public-watch"}],
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_capabilities_fail_closed_for_managed_starts(self):
        capabilities = get_apify_facebook_connector_capabilities()
        self.assertFalse(capabilities["managedRuns"]["enabled"])
        self.assertTrue(capabilities["managedRuns"]["disabledByDefault"])
        self.assertFalse(capabilities["startsPaidRuns"])
        self.assertEqual(capabilities["actor"]["actorId"], DEFAULT_APIFY_FACEBOOK_ACTOR_ID)

    def test_retention_cleanup_is_dry_run_by_default(self):
        payload = ApifyRetentionCleanupRequest.model_validate({})
        self.assertTrue(payload.dry_run)


if __name__ == "__main__":
    unittest.main()
