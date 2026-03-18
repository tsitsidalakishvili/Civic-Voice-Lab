import re
import uuid
from typing import Dict, List
from urllib.parse import urlparse


FREEDOM_SQUARE_DOMAINS = {"freedomsquare.ge", "www.freedomsquare.ge"}


def _sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _find_quotes(text: str, keywords: List[str], limit: int = 2) -> List[str]:
    sentences = _sentences(text)
    matches = []
    for sentence in sentences:
        lower = sentence.lower()
        if any(keyword in lower for keyword in keywords):
            matches.append(sentence)
        if len(matches) >= limit:
            break
    return matches


def _is_freedom_square(url: str, text: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host in FREEDOM_SQUARE_DOMAINS:
        return True
    return "freedom square" in (text or "").lower()


def augment_segments_for_domain(
    url: str,
    text: str,
    segments: List[Dict[str, object]],
    page_id: str,
    page_url: str,
) -> List[Dict[str, object]]:
    if not _is_freedom_square(url, text):
        return segments

    existing = {segment.get("name", "").lower() for segment in segments}
    templates = [
        {
            "name": "Civic engagement supporters",
            "rationale": "Content emphasizes civic engagement and public participation.",
            "keywords": ["civic", "participation", "democracy", "public", "rights"],
        },
        {
            "name": "Volunteer organizers",
            "rationale": "Mentions of volunteers, organizing, and local action.",
            "keywords": ["volunteer", "organize", "community", "campaign", "join"],
        },
        {
            "name": "Donors and patrons",
            "rationale": "Signals related to donations, support, and funding.",
            "keywords": ["donate", "donation", "support", "contribute", "fund"],
        },
        {
            "name": "Policy advocacy partners",
            "rationale": "References to policy, reform, and advocacy work.",
            "keywords": ["policy", "reform", "advocacy", "rights", "governance"],
        },
        {
            "name": "Program participants",
            "rationale": "Program or initiative language suggests participant audiences.",
            "keywords": ["program", "initiative", "training", "workshop", "project"],
        },
    ]

    for template in templates:
        if template["name"].lower() in existing:
            continue
        quotes = _find_quotes(text, template["keywords"], limit=2)
        if not quotes:
            continue
        segments.append(
            {
                "segmentId": str(uuid.uuid4()),
                "name": template["name"],
                "rationale": template["rationale"],
                "candidateEvidenceQuotes": quotes,
                "confidence": 0.72,
                "pageId": page_id,
                "pageUrl": page_url,
            }
        )
        existing.add(template["name"].lower())

    return segments
