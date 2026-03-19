import re
from collections import Counter
from typing import Iterable, List

STOPWORDS = {
    "The",
    "A",
    "An",
    "And",
    "Or",
    "But",
    "If",
    "Then",
    "Else",
    "For",
    "Of",
    "In",
    "On",
    "At",
    "To",
    "From",
    "By",
    "With",
    "Without",
    "Over",
    "Under",
    "Into",
    "Across",
    "About",
    "After",
    "Before",
    "Between",
    "Within",
    "This",
    "That",
    "These",
    "Those",
    "Our",
    "Your",
    "Their",
    "Its",
    "Page",
    "Section",
    "Chapter",
    "Overview",
}


def _clean_candidate(candidate: str) -> str:
    return re.sub(r"[^\w\s&.-]", "", candidate).strip()


def extract_entities(text: str, max_entities: int = 6) -> List[str]:
    if not text:
        return []
    proper_nouns = re.findall(
        r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", text
    )
    acronyms = re.findall(r"\b[A-Z]{2,}\b", text)
    candidates = [_clean_candidate(item) for item in proper_nouns + acronyms]
    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        if not candidate or candidate in STOPWORDS:
            continue
        if candidate.isdigit():
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
        if len(deduped) >= max_entities:
            break
    return deduped


def top_entities(entities: Iterable[str], limit: int = 2) -> List[str]:
    counts = Counter([item for item in entities if item])
    return [item for item, _ in counts.most_common(limit)]
