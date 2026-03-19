import json
import os
import time
from typing import Dict, List, Optional

import requests

from .audience_discovery_examples import FEW_SHOT_EXAMPLES
from .audience_discovery_keywords import keyword_segments


def _format_locale(locale: Optional[str]) -> str:
    if not locale:
        return ""
    normalized = locale.strip().lower()
    if normalized in {"en", "en-us", "en-gb"}:
        return "English"
    if normalized in {"ka", "ka-ge"}:
        return "Georgian"
    return normalized


def _build_prompt(description: str, text: str, locale: Optional[str]) -> str:
    examples = [
        FEW_SHOT_EXAMPLES["orchestra"],
        FEW_SHOT_EXAMPLES["saas"],
        FEW_SHOT_EXAMPLES["ecommerce"],
    ]
    language_hint = _format_locale(locale)
    language_instruction = (
        f"\nLanguage hint: {language_hint}. "
        "Write segment names and rationales in that language.\n"
        if language_hint
        else ""
    )
    parts = [
        "You are an audience segmentation assistant. ",
        "Return JSON only. Schema:\n",
        "{\n",
        '  "segments": [\n',
        "    {\n",
        '      "segmentName": "string",\n',
        '      "rationale": "string",\n',
        '      "candidateEvidenceQuotes": ["string", "string"],\n',
        '      "confidence": 0.0\n',
        "    }\n",
        "  ]\n",
        "}\n\n",
        "Rules:\n",
        "- Use only evidence from the provided text.\n",
        "- Avoid unsupported claims.\n",
        "- Provide 2-5 segments.\n",
        "- Keep quotes verbatim from the text.\n\n",
        language_instruction,
        f"Website description: {description}\n\n",
        "Examples:\n",
        "\n".join(json.dumps(example, ensure_ascii=False) for example in examples),
        "\n\n",
        "Text:\n",
        f"{text}\n",
    ]
    return "".join(parts)


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
    return json.loads(content)


def generate_segments_llm(
    text: str, description: str, locale: Optional[str] = None
) -> Dict[str, object]:
    api_url = os.getenv("LLM_API_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    if not api_url or not api_key:
        segments = keyword_segments(f"{description}\n{text}".strip())
        return {"raw": json.dumps({"segments": segments}), "parsed": {"segments": segments}}

    prompt = _build_prompt(description, text, locale)
    last_error = ""
    for attempt in range(3):
        try:
            payload = _call_llm(prompt, api_url, api_key, model)
            return {"raw": json.dumps(payload, ensure_ascii=False), "parsed": payload}
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1 + attempt)

    segments = keyword_segments(f"{description}\n{text}".strip())
    return {
        "raw": json.dumps({"segments": segments}),
        "parsed": {"segments": segments},
        "error": last_error,
    }
