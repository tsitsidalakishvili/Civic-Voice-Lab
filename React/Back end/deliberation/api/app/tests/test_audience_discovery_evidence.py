import unittest

from deliberation.api.app.audience_discovery_evidence import verify_evidence


class TestAudienceDiscoveryEvidence(unittest.TestCase):
    def test_verifies_quotes(self):
        chunks = [
            {
                "chunkId": "page-1-1",
                "url": "https://example.com/page",
                "text": "This is a sample sentence about community impact.",
            }
        ]
        segments = [
            {
                "segmentId": "seg-1",
                "candidateEvidenceQuotes": [
                    "sample sentence about community impact",
                    "This is a sample sentence about community impact.",
                ],
            }
        ]
        verified = verify_evidence(segments, chunks)
        self.assertEqual(len(verified[0]["evidence"]), 2)
        self.assertTrue(verified[0]["verified"])


if __name__ == "__main__":
    unittest.main()
