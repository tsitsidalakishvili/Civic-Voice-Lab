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
    "no",
    "არ",
    "ვერ",
    "არასწორია",
    "ცუდია",
    "პრობლემაა",
    "პრობლემა",
    "უსამართლოა",
    "ბუნდოვანია",
    "რისკია",
    "უარყოფითი",
    "წინააღმდეგი",
    "არ ვეთანხმები",
}

NEGATORS = {"not", "no", "never", "არ", "ვერ", "without"}


@dataclass(frozen=True)
class SentimentResult:
    score: float
    label: str


def _plain(value: Any) -> str:
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().lower()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u10a0-\u10ff]+", text, flags=re.UNICODE)


def score_sentiment(text: Any) -> SentimentResult:
    normalized = _plain(text)
    if not normalized:
        return SentimentResult(score=0.0, label="neutral")

    positive = 0.0
    negative = 0.0
    for phrase in POSITIVE_TERMS:
        if " " in phrase and phrase in normalized:
            positive += 1.5
    for phrase in NEGATIVE_TERMS:
        if " " in phrase and phrase in normalized:
            negative += 1.5

    words = _tokens(normalized)
    for index, word in enumerate(words):
        previous = set(words[max(0, index - 2) : index])
        is_negated = bool(previous & NEGATORS)
        if word in POSITIVE_TERMS:
            if is_negated:
                negative += 1.0
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