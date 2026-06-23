import re
import unicodedata
from dataclasses import dataclass
from typing import Any


POSITIVE_TERMS = {
    "agree",
    "support",
    "good",
    "great",
    "excellent",
    "right",
    "needed",
    "necessary",
    "important",
    "useful",
    "clear",
    "fair",
    "positive",
    "like",
    "approve",
    "yes",
    "ვეთანხმები",
    "მომწონს",
    "კარგია",
    "სწორია",
    "აუცილებელია",
    "მნიშვნელოვანია",
    "საჭიროა",
    "მხარს",
    "ვუჭერ",
    "კარგი",
    "დადებითი",
}

NEGATIVE_TERMS = {
    "disagree",
    "oppose",
    "bad",
    "wrong",
    "unclear",
    "unfair",
    "risky",
    "risk",
    "problem",
    "issue",
    "negative",
    "concern",
    "concerns",
    "reject",
    "horrible",
    "terrible",
    "awful",
    "poor",
    "worse",
    "worst",
    "no",
    "არ",
    "ვერ",
    "არასწორია",
    "ცუდია",
    "ცუდი",
    "საშინელია",
    "საშინელი",
    "პრობლემაა",
    "პრობლემა",
    "უსამართლოა",
    "ბუნდოვანია",
    "რისკია",
    "უარყოფითი",
    "წინააღმდეგი",
}

POSITIVE_PHRASES = {
    "i agree": 2.0,
    "strongly agree": 2.0,
    "good decision": 2.0,
    "great decision": 2.0,
    "კარგი გადაწყვეტილებაა": 2.0,
    "სწორი გადაწყვეტილებაა": 2.0,
}

NEGATIVE_PHRASES = {
    "do not agree": 2.5,
    "not agree": 2.5,
    "i do not agree": 2.5,
    "dont agree": 2.5,
    "don't agree": 2.5,
    "disagree": 2.0,
    "horrible decision": 2.5,
    "terrible decision": 2.5,
    "awful decision": 2.5,
    "bad decision": 2.0,
    "wrong decision": 2.0,
    "არ ვეთანხმები": 2.5,
    "არ მომწონს": 2.0,
    "ცუდი გადაწყვეტილებაა": 2.5,
    "ცუდი გადაწყვეტილება": 2.5,
    "არასწორი გადაწყვეტილებაა": 2.5,
    "საშინელი გადაწყვეტილებაა": 2.5,
}

NEGATORS = {
    "not",
    "no",
    "never",
    "without",
    "dont",
    "don't",
    "არ",
    "ვერ",
}


@dataclass(frozen=True)
class SentimentResult:
    score: float
    label: str


def _plain(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"\b(don't|dont)\b", "do not", text)
    text = re.sub(r"\b(can't|cant)\b", "can not", text)
    text = re.sub(r"\b(won't|wont)\b", "will not", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u10a0-\u10ff']+", text, flags=re.UNICODE)


def _phrase_score(normalized: str, phrases: dict[str, float]) -> float:
    return sum(weight for phrase, weight in phrases.items() if phrase in normalized)


def score_sentiment(text: Any) -> SentimentResult:
    normalized = _plain(text)
    if not normalized:
        return SentimentResult(score=0.0, label="neutral")

    positive = _phrase_score(normalized, POSITIVE_PHRASES)
    negative = _phrase_score(normalized, NEGATIVE_PHRASES)

    words = _tokens(normalized)
    for index, word in enumerate(words):
        previous = set(words[max(0, index - 3) : index])
        is_negated = bool(previous & NEGATORS)
        if word in POSITIVE_TERMS:
            if is_negated:
                negative += 1.25
            else:
                positive += 1.0
        if word in NEGATIVE_TERMS:
            if is_negated and word not in NEGATORS:
                positive += 0.5
            else:
                negative += 1.0

    raw_score = positive - negative
    total = positive + negative
    if total == 0:
        score = 0.0
    else:
        score = max(-1.0, min(1.0, raw_score / max(total, 1.0)))

    if score <= -0.25:
        label = "negative"
    elif score >= 0.25:
        label = "positive"
    else:
        label = "neutral"
    return SentimentResult(score=round(score, 3), label=label)

