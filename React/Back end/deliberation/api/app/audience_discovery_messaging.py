import json
import os
import re
import time
from typing import Dict, List, Optional

import requests


def _clean_json(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _call_llm(prompt: str, api_url: str, api_key: str, model: Optional[str]) -> Dict[str, object]:
    payload = {
        "model": model or "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": "You return only JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    response = requests.post(
        api_url,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return json.loads(_clean_json(content))


def _evidence_quotes(segment: Dict[str, object], limit: int = 3) -> List[str]:
    quotes = [item.get("quote", "") for item in segment.get("evidence") or [] if item.get("quote")]
    if quotes:
        return quotes[:limit]
    candidates = [
        quote for quote in segment.get("candidateEvidenceQuotes", []) if quote
    ]
    return candidates[:limit]


def _fallback_message(segment: Dict[str, object], brand: str, locale: str) -> Dict[str, object]:
    locale_note = f" ({locale})" if locale else ""
    name = segment.get("name", "Audience segment")
    topic = name.replace("audience", "").strip().lower() or "audience"
    proof = _evidence_quotes(segment, limit=1)
    proof_note = proof[0] if proof else segment.get("rationale", "")
    prefix = f"{brand}: " if brand else ""
    return {
        "segmentId": segment["segmentId"],
        "name": name,
        "headlines": [
            f"{prefix}{topic.title()} outcomes backed by evidence{locale_note}",
            f"{prefix}Priorities that matter to {topic}",
            f"{prefix}Trusted results for {topic}",
        ],
        "tone": f"Evidence-led, confident, and benefit-focused. {proof_note}".strip(),
        "ctas": [
            "Explore the evidence",
            "See the plan",
            "Talk to the team",
        ],
    }


def _build_prompt(segments: List[Dict[str, object]], brand: str, locale: str) -> str:
    locale_note = f"Locale: {locale}" if locale else "Locale: auto"
    description = f"Brand: {brand}" if brand else "Brand: (not provided)"
    serialized = []
    for segment in segments:
        serialized.append(
            {
                "segmentId": segment.get("segmentId"),
                "name": segment.get("name"),
                "rationale": segment.get("rationale"),
                "evidenceQuotes": _evidence_quotes(segment),
            }
        )
    return (
        "You are a messaging strategist. Return JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "messaging": [\n'
        "    {\n"
        '      "segmentId": "string",\n'
        '      "name": "string",\n'
        '      "headlines": ["string", "string", "string"],\n'
        '      "tone": "string",\n'
        '      "ctas": ["string", "string", "string"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Use the evidence quotes to ground the recommendations.\n"
        "- Provide exactly 3 headlines and 3 CTAs per segment.\n"
        "- Keep language concise and confident.\n"
        f"- {description}\n"
        f"- {locale_note}\n\n"
        "Segments:\n"
        f"{json.dumps(serialized, ensure_ascii=False)}\n"
    )


def _normalize_message(
    segment: Dict[str, object], message: Dict[str, object], brand: str, locale: str
) -> Dict[str, object]:
    fallback = _fallback_message(segment, brand, locale)
    headlines = message.get("headlines") or fallback["headlines"]
    ctas = message.get("ctas") or fallback["ctas"]
    return {
        "segmentId": segment["segmentId"],
        "name": message.get("name") or fallback["name"],
        "headlines": list(headlines)[:3],
        "tone": message.get("tone") or fallback["tone"],
        "ctas": list(ctas)[:3],
    }


def generate_messaging(segments: List[Dict[str, object]], brand: str, locale: str):
    confirmed = [segment for segment in segments if segment.get("confirmed")]
    if not confirmed:
        return []

    api_url = os.getenv("LLM_API_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()

    if api_url and api_key:
        prompt = _build_prompt(confirmed, brand, locale)
        last_error = ""
        for attempt in range(3):
            try:
                payload = _call_llm(prompt, api_url, api_key, model)
                items = payload.get("messaging", [])
                by_id = {item.get("segmentId"): item for item in items if item.get("segmentId")}
                return [
                    _normalize_message(segment, by_id.get(segment["segmentId"], {}), brand, locale)
                    for segment in confirmed
                ]
            except Exception as exc:
                last_error = str(exc)
                time.sleep(1 + attempt)
        # Fall back to templated messaging if LLM failed.
        _ = last_error

    return [_fallback_message(segment, brand, locale) for segment in confirmed]
