from typing import Dict, List


def verify_evidence(segments: List[Dict[str, object]], chunks: List[Dict[str, object]]):
    chunk_lookup = {chunk["chunkId"]: chunk for chunk in chunks}
    for segment in segments:
        page_id = segment.get("pageId")
        verified = []
        rejected = []
        for quote in segment.get("candidateEvidenceQuotes", []):
            quote_text = (quote or "").strip()
            if not quote_text:
                continue
            for chunk in chunks:
                if page_id and chunk.get("pageId") != page_id:
                    continue
                idx = chunk["text"].find(quote_text)
                if idx >= 0:
                    verified.append(
                        {
                            "quote": quote_text,
                            "url": chunk["url"],
                            "chunkId": chunk["chunkId"],
                            "startOffset": idx,
                            "endOffset": idx + len(quote_text),
                            "isSample": False,
                        }
                    )
                    break
            else:
                rejected.append(quote_text)
        segment["evidence"] = verified
        segment["verified"] = len(verified) >= 2
        segment["rejectedEvidence"] = rejected
    return segments
