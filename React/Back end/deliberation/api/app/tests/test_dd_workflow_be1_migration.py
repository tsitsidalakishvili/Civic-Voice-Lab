from __future__ import annotations

import copy
import os
import unittest
from unittest.mock import patch

from deliberation.api.app.dd_workflow_be1_migration import (
    MIGRATION_CONFIRMATION,
    MIGRATION_WRITE_FLAG,
    MUTATION_CONTRACT_VERSION,
    apply_projection_plan_to_database,
    apply_projection_plan_to_memory,
    plan_projection_migration,
    rollback_projection_plan_in_memory,
    safe_migration_report,
)


def synthetic_rows():
    return [
        {
            "caseId": "case-synthetic-legacy-active",
            "subject": "Synthetic Legacy Organization",
            "subjectGeorgian": "სატესტო ძველი ორგანიზაცია",
            "subjectEnglish": "Synthetic Legacy Organization",
            "subjectType": "Organization",
            "status": "Active",
            "owner": "Synthetic Owner",
            "createdAt": "2025-01-01T00:00:00+00:00",
            "updatedAt": "2025-01-02T00:00:00+00:00",
            "ddWorkflowVersion": None,
            "ddWorkflowSchemaVersion": None,
            "projectionJson": None,
        },
        {
            "caseId": "case-synthetic-legacy-review",
            "subject": "Synthetic Review Subject",
            "subjectGeorgian": "სატესტო განხილვის სუბიექტი",
            "subjectEnglish": "Synthetic Review Subject",
            "subjectType": "Person",
            "status": "Review",
            "owner": "",
            "createdAt": "2025-02-01T00:00:00+00:00",
            "updatedAt": "2025-02-02T00:00:00+00:00",
            "ddWorkflowVersion": None,
            "ddWorkflowSchemaVersion": None,
            "projectionJson": None,
        },
    ]


class Be1MigrationTests(unittest.TestCase):
    def test_dry_run_counts_and_safe_report(self):
        plan = plan_projection_migration(synthetic_rows())
        self.assertTrue(plan["dryRun"])
        self.assertEqual(2, plan["plannedCount"])
        self.assertEqual(0, plan["errorCount"])
        self.assertEqual({"review": 1, "sources": 1}, plan["stageCounts"])
        self.assertEqual(2, plan["migrationNeedsReviewCount"])
        report = safe_migration_report(plan)
        self.assertNotIn("projections", report)
        self.assertNotIn("Synthetic Legacy Organization", str(report))

    def test_apply_is_idempotent_and_rollback_removes_new_projection_only(self):
        source = synthetic_rows()
        plan = plan_projection_migration(source)
        applied_once = apply_projection_plan_to_memory(source, plan)
        second_plan = plan_projection_migration(applied_once)
        self.assertEqual(0, second_plan["plannedCount"])
        self.assertEqual(2, second_plan["skippedCount"])
        applied_twice = apply_projection_plan_to_memory(applied_once, second_plan)
        self.assertEqual(applied_once, applied_twice)

        rolled_back = rollback_projection_plan_in_memory(applied_once)
        for before, after in zip(source, rolled_back):
            self.assertEqual(before["caseId"], after["caseId"])
            self.assertEqual(before["subjectGeorgian"], after["subjectGeorgian"])
            self.assertNotIn("projectionJson", after)
            self.assertNotIn("ddWorkflowSchemaVersion", after)
        self.assertEqual(copy.deepcopy(source)[0]["subject"], rolled_back[0]["subject"])

    def test_database_apply_is_fail_closed_without_flag_and_confirmation(self):
        plan = plan_projection_migration(synthetic_rows())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(MIGRATION_WRITE_FLAG, None)
            with self.assertRaises(RuntimeError):
                apply_projection_plan_to_database(plan, confirmation=MIGRATION_CONFIRMATION)
        with patch.dict(os.environ, {MIGRATION_WRITE_FLAG: "1"}):
            with self.assertRaises(RuntimeError):
                apply_projection_plan_to_database(plan, confirmation="wrong")

    def test_existing_be1_projection_is_never_rewritten(self):
        rows = synthetic_rows()
        rows[0]["ddWorkflowSchemaVersion"] = MUTATION_CONTRACT_VERSION
        rows[0]["projectionJson"] = "{\"preserved\":true}"
        plan = plan_projection_migration(rows)
        self.assertEqual(1, plan["plannedCount"])
        self.assertEqual(1, plan["skippedCount"])


if __name__ == "__main__":
    unittest.main()
