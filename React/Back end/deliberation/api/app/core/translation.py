from __future__ import annotations

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from .config import get_settings

SUPPORTED_TRANSLATION_LANGUAGES = {"en", "ka"}
_GEORGIAN_RE = re.compile(r"[\u10A0-\u10FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_WHITESPACE_RE = re.compile(r"\s+")
_CACHE_LIMIT = 2048


def normalize_translation_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text)


def detect_translation_language(text: str) -> str:
    normalized = normalize_translation_text(text)
    if not normalized:
        return ""
    if _GEORGIAN_RE.search(normalized):
        return "ka"
    if _LATIN_RE.search(normalized):
        return "en"
    return ""


class TranslationServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranslationItem:
    text: str
    translated_text: str
    source_language: str
    target_language: str
    changed: bool
    skipped: bool
    reason: str = ""


class TranslationService:
    def __init__(self) -> None:
        self._pipelines: dict[tuple[str, str], object] = {}
        self._cache: OrderedDict[tuple[str, str, str], str] = OrderedDict()
        self._lock = threading.Lock()

    def _model_name(self, source_language: str, target_language: str) -> str:
        settings = get_settings()
        if source_language == "en" and target_language == "ka":
            return settings.translation_en_ka_model
        if source_language == "ka" and target_language == "en":
            return settings.translation_ka_en_model
        raise TranslationServiceError(
            f"Unsupported translation direction: {source_language}->{target_language}"
        )

    def _get_pipeline(self, source_language: str, target_language: str):
        key = (source_language, target_language)
        with self._lock:
            existing = self._pipelines.get(key)
            if existing is not None:
                return existing
            try:
                from transformers import pipeline
            except Exception as exc:
                raise TranslationServiceError(
                    "Translation runtime is unavailable. Check transformers, torch, and sentencepiece installation."
                ) from exc
            model_name = self._model_name(source_language, target_language)
            translator = pipeline(
                "translation",
                model=model_name,
                tokenizer=model_name,
                device=-1,
            )
            self._pipelines[key] = translator
            return translator

    def _cache_get(self, source_language: str, target_language: str, text: str) -> str | None:
        cache_key = (source_language, target_language, text)
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached is None:
                return None
            self._cache.move_to_end(cache_key)
            return cached

    def _cache_set(
        self, source_language: str, target_language: str, text: str, translated_text: str
    ) -> None:
        cache_key = (source_language, target_language, text)
        with self._lock:
            self._cache[cache_key] = translated_text
            self._cache.move_to_end(cache_key)
            while len(self._cache) > _CACHE_LIMIT:
                self._cache.popitem(last=False)

    def translate(
        self,
        texts: Iterable[object],
        *,
        target_language: str,
        source_language: str = "",
    ) -> list[TranslationItem]:
        settings = get_settings()
        target = str(target_language or "").strip().lower()
        source_hint = str(source_language or "").strip().lower()
        if target not in SUPPORTED_TRANSLATION_LANGUAGES:
            raise TranslationServiceError(f"Unsupported target language: {target_language}")
        if source_hint and source_hint not in SUPPORTED_TRANSLATION_LANGUAGES:
            raise TranslationServiceError(f"Unsupported source language: {source_language}")

        normalized_texts = [normalize_translation_text(value) for value in texts]
        if len(normalized_texts) > settings.translation_max_texts:
            raise TranslationServiceError(
                f"Too many texts requested. Max supported per request is {settings.translation_max_texts}."
            )

        results: list[TranslationItem | None] = [None] * len(normalized_texts)
        batches: dict[tuple[str, str], list[tuple[int, str]]] = {}

        for index, text in enumerate(normalized_texts):
            if not text:
                results[index] = TranslationItem(
                    text="",
                    translated_text="",
                    source_language=source_hint or "",
                    target_language=target,
                    changed=False,
                    skipped=True,
                    reason="empty",
                )
                continue
            if len(text) > settings.translation_max_chars:
                results[index] = TranslationItem(
                    text=text,
                    translated_text=text,
                    source_language=source_hint or detect_translation_language(text),
                    target_language=target,
                    changed=False,
                    skipped=True,
                    reason="too_long",
                )
                continue
            source = source_hint or detect_translation_language(text)
            if source not in SUPPORTED_TRANSLATION_LANGUAGES:
                results[index] = TranslationItem(
                    text=text,
                    translated_text=text,
                    source_language=source,
                    target_language=target,
                    changed=False,
                    skipped=True,
                    reason="unsupported_or_unknown_source",
                )
                continue
            if source == target:
                results[index] = TranslationItem(
                    text=text,
                    translated_text=text,
                    source_language=source,
                    target_language=target,
                    changed=False,
                    skipped=True,
                    reason="same_language",
                )
                continue
            batches.setdefault((source, target), []).append((index, text))

        for (source, target_language_code), items in batches.items():
            translator = self._get_pipeline(source, target_language_code)
            pending_indexes: list[int] = []
            pending_texts: list[str] = []
            for index, text in items:
                cached = self._cache_get(source, target_language_code, text)
                if cached is not None:
                    results[index] = TranslationItem(
                        text=text,
                        translated_text=cached,
                        source_language=source,
                        target_language=target_language_code,
                        changed=cached != text,
                        skipped=False,
                        reason="cache",
                    )
                    continue
                pending_indexes.append(index)
                pending_texts.append(text)
            if not pending_texts:
                continue
            try:
                outputs = translator(
                    pending_texts,
                    batch_size=min(8, len(pending_texts)),
                    max_length=512,
                    clean_up_tokenization_spaces=True,
                )
            except Exception as exc:
                raise TranslationServiceError(f"Translation failed: {exc}") from exc
            for index, text, output in zip(pending_indexes, pending_texts, outputs):
                translated_text = normalize_translation_text(
                    output.get("translation_text") if isinstance(output, dict) else text
                )
                if not translated_text:
                    translated_text = text
                self._cache_set(source, target_language_code, text, translated_text)
                results[index] = TranslationItem(
                    text=text,
                    translated_text=translated_text,
                    source_language=source,
                    target_language=target_language_code,
                    changed=translated_text != text,
                    skipped=False,
                    reason="translated",
                )

        return [
            item
            if item is not None
            else TranslationItem(
                text="",
                translated_text="",
                source_language=source_hint or "",
                target_language=target,
                changed=False,
                skipped=True,
                reason="empty",
            )
            for item in results
        ]


@lru_cache(maxsize=1)
def get_translation_service() -> TranslationService:
    return TranslationService()
