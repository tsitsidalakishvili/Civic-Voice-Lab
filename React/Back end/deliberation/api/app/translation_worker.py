from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .core.config import get_settings
from .core.translation import (
    SUPPORTED_TRANSLATION_LANGUAGES,
    TranslationServiceError,
    get_translation_service,
)

app = FastAPI(title="Civic Voice Lab Translation Worker")


class TranslationBatchIn(BaseModel):
    texts: List[str] = Field(default_factory=list, min_items=1)
    target_language: str = Field(alias="targetLanguage")
    source_language: str = Field(default="", alias="sourceLanguage")


@app.get("/healthz")
def healthz():
    settings = get_settings()
    return {
        "status": "ok",
        "enabled": settings.translation_enabled,
        "worker": "translation",
    }


@app.post("/translate")
def translate(payload: TranslationBatchIn):
    settings = get_settings()
    target_language = str(payload.target_language or "").strip().lower()
    source_language = str(payload.source_language or "").strip().lower()
    if target_language not in SUPPORTED_TRANSLATION_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target language. Use one of: {', '.join(sorted(SUPPORTED_TRANSLATION_LANGUAGES))}.",
        )
    if source_language and source_language not in SUPPORTED_TRANSLATION_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source language. Use one of: {', '.join(sorted(SUPPORTED_TRANSLATION_LANGUAGES))}.",
        )
    if not settings.translation_enabled:
        return {
            "enabled": False,
            "supportedLanguages": sorted(SUPPORTED_TRANSLATION_LANGUAGES),
            "modelByDirection": {
                "en-ka": settings.translation_en_ka_model,
                "ka-en": settings.translation_ka_en_model,
            },
            "items": [
                {
                    "text": str(text or "").strip(),
                    "translatedText": str(text or "").strip(),
                    "sourceLanguage": source_language,
                    "targetLanguage": target_language,
                    "changed": False,
                    "skipped": True,
                    "reason": "disabled",
                }
                for text in payload.texts
            ],
        }
    try:
        items = get_translation_service().translate(
            payload.texts,
            target_language=target_language,
            source_language=source_language,
        )
    except TranslationServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "enabled": True,
        "supportedLanguages": sorted(SUPPORTED_TRANSLATION_LANGUAGES),
        "modelByDirection": {
            "en-ka": settings.translation_en_ka_model,
            "ka-en": settings.translation_ka_en_model,
        },
        "items": [
            {
                "text": item.text,
                "translatedText": item.translated_text,
                "sourceLanguage": item.source_language,
                "targetLanguage": item.target_language,
                "changed": item.changed,
                "skipped": item.skipped,
                "reason": item.reason,
            }
            for item in items
        ],
    }
