import unittest

from deliberation.api.app.audience_discovery_segments import validate_segments


class TestAudienceDiscoverySegments(unittest.TestCase):
    def test_validate_repairs_payload(self):
        raw = {
            "segments": [
                {
                    "segment_name": "Test segment",
                    "candidate_evidence_quotes": ["Quote one."],
                }
            ]
        }
        result = validate_segments(raw)
        self.assertEqual(result.segments[0].segment_name, "Test segment")
        self.assertEqual(result.segments[0].candidate_evidence_quotes, ["Quote one."])


if __name__ == "__main__":
    unittest.main()
