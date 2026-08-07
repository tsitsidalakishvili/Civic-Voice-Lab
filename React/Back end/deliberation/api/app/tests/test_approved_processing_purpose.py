import unittest
from unittest.mock import MagicMock, patch

from deliberation.api.app import db


class ApprovedProcessingPurposeTests(unittest.TestCase):
    def test_owner_approved_due_diligence_purpose_is_seeded_idempotently(self):
        driver = MagicMock()
        session = driver.session.return_value.__enter__.return_value

        with patch.object(db, "get_driver", return_value=driver):
            db.init_approved_processing_purposes()

        transaction = session.execute_write.call_args.args[0]
        tx = MagicMock()
        transaction(tx)
        query, params = tx.run.call_args.args

        self.assertIn("MERGE (purpose:ProcessingPurpose", query)
        self.assertIn("MERGE (event:ComplianceAuditEvent", query)
        self.assertEqual(params["purposeId"], "dd-investigation")
        self.assertEqual(params["purposeVersionId"], "dd-investigation:v1")
        self.assertEqual(params["eventId"], "purpose-approval:dd-investigation:v1")


if __name__ == "__main__":
    unittest.main()
