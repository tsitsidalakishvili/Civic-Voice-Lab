import json
import os
import platform
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import requests


ENGLISH_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "i",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "our",
    "she",
    "that",
    "the",
    "their",
    "this",
    "to",
    "we",
    "with",
    "you",
}

def _ka(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


GEORGIAN_STOP_WORDS = {
    _ka(0x10d3, 0x10d0),
    _ka(0x10d0, 0x10dc),
    _ka(0x10d0, 0x10e0, 0x10d8, 0x10e1),
    _ka(0x10d8, 0x10e7, 0x10dd),
    _ka(0x10d4, 0x10e1),
    _ka(0x10d8, 0x10e1),
    _ka(0x10e0, 0x10dd, 0x10db),
    _ka(0x10d7, 0x10e3),
    _ka(0x10db, 0x10d4),
    _ka(0x10e9, 0x10d5, 0x10d4, 0x10dc),
    _ka(0x10d7, 0x10e5, 0x10d5, 0x10d4, 0x10dc),
    _ka(0x10db, 0x10d0, 0x10d7),
    _ka(0x10db, 0x10d8, 0x10e1, 0x10d8),
    _ka(0x10db, 0x10d0, 0x10d7, 0x10d8),
    _ka(0x10d0, 0x10db),
    _ka(0x10d8, 0x10db),
    _ka(0x10d6, 0x10d4),
    _ka(0x10e8, 0x10d8),
    _ka(0x10d7, 0x10d0, 0x10dc),
    _ka(0x10d7, 0x10d5, 0x10d8, 0x10e1),
}

VALID_LABELS = {"negative", "neutral", "positive"}
_LAST_TRANSFORMER_ERROR = ""


@dataclass(frozen=True)
class SentimentResult:
    score: float
    label: str
    confidence: float = 0.0
    provider: str = "unavailable"
    processed_text: str = ""


def _plain(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = text.replace("\u2019", "'").replace("`", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u10a0-\u10ff']+", text, flags=re.UNICODE)


def _remove_stop_words(text: str) -> str:
    words = _tokens(text)
    filtered = [
        word
        for word in words
        if word not in ENGLISH_STOP_WORDS and word not in GEORGIAN_STOP_WORDS
    ]
    return " ".join(filtered) or text


def _detect_language(text: str) -> str:
    if re.search(r"[\u10a0-\u10ff]", text):
        return "ka"
    if re.search(r"[a-z]", text):
        return "en"
    return "unknown"


def preprocess_text(text: Any) -> dict[str, str]:
    normalized = _plain(text)
    return {
        "normalized": normalized,
        "processed": _remove_stop_words(normalized) if normalized else "",
        "language": _detect_language(normalized),
    }


def _label_from_score(score: float) -> str:
    if score <= -0.25:
        return "negative"
    if score >= 0.25:
        return "positive"
    return "neutral"


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return round(max(-1.0, min(1.0, score)), 3)


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _normalize_ai_payload(payload: dict[str, Any], processed_text: str, provider: str) -> SentimentResult:
    label = str(payload.get("label") or payload.get("sentiment") or "").strip().lower()
    score = _coerce_score(payload.get("score"))
    if label not in VALID_LABELS:
        label = _label_from_score(score)
    if score == 0.0 and label == "positive":
        score = 0.75
    elif score == 0.0 and label == "negative":
        score = -0.75
    confidence = max(0.0, min(1.0, float(payload.get("confidence") or 0.0)))
    return SentimentResult(
        score=score,
        label=label,
        confidence=round(confidence, 3),
        provider=provider,
        processed_text=processed_text,
    )


def _build_llm_prompt(original: str, processed: str, language: str) -> str:
    return """
Analyze the sentiment of a civic deliberation comment.
Return JSON only with this schema:
{{"label":"positive|neutral|negative","score":-1.0,"confidence":0.0}}

Rules:
- Understand Georgian and English.
- Judge the author's attitude toward the statement or decision being discussed.
- Negative means criticism, rejection, disagreement, concern, or harmful evaluation.
- Positive means support, approval, agreement, or favorable evaluation.
- Neutral means unclear, mixed, descriptive, reflective, or insufficient sentiment.
- Do not rely on keyword matching. Use semantic meaning.
- score must be between -1.0 and 1.0.
- confidence must be between 0.0 and 1.0.

Language: {language}
Original comment: {original}
Stop-word-filtered comment: {processed}
""".strip().format(language=language, original=original, processed=processed)


def _call_chat_completions(prompt: str, api_url: str, api_key: str, model: str) -> dict[str, Any]:
    response = requests.post(
        api_url,
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a multilingual sentiment analysis engine. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=float(os.getenv("SENTIMENT_LLM_TIMEOUT", "12")),
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _extract_json(content)


def _score_with_llm(original: str, processed: str, language: str) -> SentimentResult | None:
    api_url = (
        os.getenv("SENTIMENT_LLM_API_URL", "").strip()
        or os.getenv("LLM_API_URL", "").strip()
    )
    api_key = (
        os.getenv("SENTIMENT_LLM_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
    )
    model = (
        os.getenv("SENTIMENT_LLM_MODEL", "").strip()
        or os.getenv("LLM_MODEL", "").strip()
        or "gpt-4.1-mini"
    )
    if not api_url or not api_key:
        return None
    prompt = _build_llm_prompt(original, processed, language)
    payload = _call_chat_completions(prompt, api_url, api_key, model)
    if not payload:
        return None
    return _normalize_ai_payload(payload, processed, f"llm:{model}")


DEFAULT_TRANSFORMER_MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"


@lru_cache(maxsize=1)
def _local_pipeline():
    global _LAST_TRANSFORMER_ERROR
    _LAST_TRANSFORMER_ERROR = ""
    model_name = os.getenv("SENTIMENT_TRANSFORMER_MODEL", DEFAULT_TRANSFORMER_MODEL).strip()
    if not model_name:
        _LAST_TRANSFORMER_ERROR = "model-not-configured"
        return None
    local_files_only = os.getenv("SENTIMENT_TRANSFORMER_LOCAL_FILES_ONLY", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    allow_windows = os.getenv("SENTIMENT_ALLOW_WINDOWS_TRANSFORMER", "0").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if platform.system().lower() == "windows" and not allow_windows:
        _LAST_TRANSFORMER_ERROR = "transformer-disabled-on-windows"
        return None
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("TRANSFORMERS_NO_FLAX", "1")
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    try:
        import torch  # noqa: F401
    except Exception as exc:
        _LAST_TRANSFORMER_ERROR = f"transformer-load-failed:{type(exc).__name__}"
        return None
    try:
        from transformers import pipeline

        return pipeline(
            "text-classification",
            model=model_name,
            tokenizer=model_name,
            local_files_only=local_files_only,
        )
    except Exception as exc:
        _LAST_TRANSFORMER_ERROR = f"transformer-load-failed:{type(exc).__name__}"
        return None


def _score_with_local_transformer(original: str, processed: str) -> SentimentResult | None:
    classifier = _local_pipeline()
    if classifier is None:
        return None
    try:
        output = classifier(original or processed, truncation=True)[0]
    except Exception:
        return None
    raw_label = str(output.get("label") or "").lower()
    confidence = float(output.get("score") or 0.0)
    if "neg" in raw_label or raw_label in {"1 star", "label_0"}:
        label = "negative"
        score = -confidence
    elif "pos" in raw_label or raw_label in {"5 stars", "label_2"}:
        label = "positive"
        score = confidence
    else:
        label = "neutral"
        score = 0.0
    model_name = os.getenv("SENTIMENT_TRANSFORMER_MODEL", DEFAULT_TRANSFORMER_MODEL).strip()
    return SentimentResult(
        score=round(max(-1.0, min(1.0, score)), 3),
        label=label,
        confidence=round(max(0.0, min(1.0, confidence)), 3),
        provider=f"transformer:{model_name}",
        processed_text=processed,
    )


def score_sentiment(text: Any) -> SentimentResult:
    prepared = preprocess_text(text)
    original = prepared["normalized"]
    processed = prepared["processed"]
    language = prepared["language"]
    if not original:
        return SentimentResult(score=0.0, label="neutral", processed_text="")

    provider = os.getenv("SENTIMENT_PROVIDER", "transformer").strip().lower()
    if provider in {"transformer", "local", "auto"}:
        result = _score_with_local_transformer(original, processed)
        if result is not None:
            return result
    if provider in {"llm", "ai", "auto"}:
        result = _score_with_llm(original, processed, language)
        if result is not None:
            return result

    provider_reason = _LAST_TRANSFORMER_ERROR or "unavailable"
    return SentimentResult(
        score=0.0,
        label="neutral",
        confidence=0.0,
        provider=provider_reason,
        processed_text=processed,
    )
