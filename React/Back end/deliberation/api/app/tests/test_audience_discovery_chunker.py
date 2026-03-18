import unittest

from deliberation.api.app.audience_discovery_chunker import build_chunks


class TestAudienceDiscoveryChunker(unittest.TestCase):
    def test_chunk_offsets_match_text(self):
        text = (
            "Heading One\n\n"
            "Paragraph one has some content.\n\n"
            "Paragraph two has more content and details.\n\n"
            "Paragraph three is here to ensure another chunk."
        )
        headings = ["Heading One"]
        normalized, chunks = build_chunks(text, headings, target_chars=120, min_chars=40)
        self.assertTrue(chunks)
        for chunk in chunks:
            start = chunk["start_offset"]
            end = chunk["end_offset"]
            snippet = normalized[start:end]
            self.assertEqual(snippet, chunk["text"])

    def test_no_empty_chunks(self):
        text = "Short paragraph.\n\nAnother short paragraph."
        headings = []
        _, chunks = build_chunks(text, headings, target_chars=120, min_chars=20)
        self.assertTrue(all(chunk["text"].strip() for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
