from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .core.config import get_settings
from .core.translation import SUPPORTED_TRANSLATION_LANGUAGES, TranslationItem
from .core.translation_worker_client import translate_via_worker

router = APIRouter()


class TranslationBatchIn(BaseModel):
    texts: List[str] = Field(default_factory=list, min_items=1)
    target_language: str = Field(alias="targetLanguage")
    source_language: str = Field(default="", alias="sourceLanguage")


class TranslationItemOut(BaseModel):
    text: str
    translated_text: str = Field(alias="translatedText")
    source_language: str = Field(alias="sourceLanguage")
    target_language: str = Field(alias="targetLanguage")
    changed: bool
    skipped: bool
    reason: str = ""


class TranslationBatchOut(BaseModel):
    enabled: bool
    supported_languages: List[str] = Field(alias="supportedLanguages")
    model_by_direction: dict[str, str] = Field(alias="modelByDirection")
    items: List[TranslationItemOut]


def _to_out(item: TranslationItem) -> TranslationItemOut:
    return TranslationItemOut(
        text=item.text,
        translatedText=item.translated_text,
        sourceLanguage=item.source_language,
        targetLanguage=item.target_language,
        changed=item.changed,
        skipped=item.skipped,
        reason=item.reason,
    )


@router.post("/platform/translate", response_model=TranslationBatchOut, tags=["platform"])
def translate_platform_text(payload: TranslationBatchIn):
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
        items = [
            TranslationItemOut(
                text=str(text or "").strip(),
                translatedText=str(text or "").strip(),
                sourceLanguage=source_language,
                targetLanguage=target_language,
                changed=False,
                skipped=True,
                reason="disabled",
            )
            for text in payload.texts
        ]
        return TranslationBatchOut(
            enabled=False,
            supportedLanguages=sorted(SUPPORTED_TRANSLATION_LANGUAGES),
            modelByDirection={
                "en-ka": settings.translation_en_ka_model,
                "ka-en": settings.translation_ka_en_model,
            },
            items=items,
        )

    try:
        response = translate_via_worker(
            {
                "texts": payload.texts,
                "targetLanguage": target_language,
                "sourceLanguage": source_language,
            }
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc) or "Translation worker unavailable.") from exc

    raw_items = response.get("items") if isinstance(response, dict) else []
    items = [
        TranslationItem(
            text=str(item.get("text") or ""),
            translated_text=str(item.get("translatedText") or item.get("text") or ""),
            source_language=str(item.get("sourceLanguage") or ""),
            target_language=str(item.get("targetLanguage") or target_language),
            changed=bool(item.get("changed")),
            skipped=bool(item.get("skipped")),
            reason=str(item.get("reason") or ""),
        )
        for item in (raw_items or [])
        if isinstance(item, dict)
    ]

    return TranslationBatchOut(
        enabled=bool(response.get("enabled", True)) if isinstance(response, dict) else True,
        supportedLanguages=sorted(SUPPORTED_TRANSLATION_LANGUAGES),
        modelByDirection={
            "en-ka": settings.translation_en_ka_model,
            "ka-en": settings.translation_ka_en_model,
        },
        items=[_to_out(item) for item in items],
    )
