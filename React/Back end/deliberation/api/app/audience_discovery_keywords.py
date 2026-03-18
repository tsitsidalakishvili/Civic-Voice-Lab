import re
from typing import Dict, List


def _find_quotes(keyword: str, text: str, limit: int = 3) -> List[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    matches = [sentence.strip() for sentence in sentences if keyword in sentence.lower()]
    if matches:
        return matches[:limit]
    return [sentence.strip() for sentence in sentences[:limit] if sentence.strip()]


def keyword_segments(text: str, limit: int = 4) -> List[Dict[str, object]]:
    tokens = re.findall(r"[^\W\d_]{4,}", text.lower(), flags=re.UNICODE)
    stopwords = {
        "this",
        "that",
        "with",
        "from",
        "your",
        "have",
        "will",
        "about",
        "more",
        "their",
        "them",
        "they",
        "into",
        "what",
        "when",
        "where",
        "which",
        "while",
        "been",
        "also",
        "over",
        "such",
        "than",
        "then",
        "these",
        "those",
        "here",
        "there",
        "make",
        "made",
        "most",
        "just",
        "like",
        "some",
        "our",
        "ours",
    }
    tokens = [token for token in tokens if token not in stopwords]
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    keywords = sorted(counts.keys(), key=lambda k: counts[k], reverse=True)[:limit]
    segments = []
    for keyword in keywords:
        pretty = keyword.replace("-", " ").title()
        segments.append(
            {
                "segmentName": f"{pretty} audience",
                "rationale": f"Frequent mentions of {pretty.lower()} themes.",
                "candidateEvidenceQuotes": _find_quotes(keyword, text),
                "confidence": 0.62 + min(0.3, counts[keyword] * 0.02),
            }
        )
    return segments
