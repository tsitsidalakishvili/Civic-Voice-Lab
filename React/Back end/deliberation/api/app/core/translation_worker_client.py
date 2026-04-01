from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import requests

from .config import get_settings

_WORKER_PROCESS: subprocess.Popen | None = None
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _health_url() -> str:
    return f"{get_settings().translation_worker_url.rstrip('/')}/healthz"


def _translate_url() -> str:
    return f"{get_settings().translation_worker_url.rstrip('/')}/translate"


def _worker_is_healthy() -> bool:
    try:
        response = requests.get(_health_url(), timeout=2)
    except requests.RequestException:
        return False
    return response.ok


def ensure_translation_worker() -> None:
    global _WORKER_PROCESS
    if _worker_is_healthy():
        return
    if _WORKER_PROCESS is None or _WORKER_PROCESS.poll() is not None:
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "deliberation.api.app.translation_worker:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8011",
        ]
        _WORKER_PROCESS = subprocess.Popen(
            command,
            cwd=str(_BACKEND_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_WINDOWS_CREATION_FLAGS,
        )
    deadline = time.time() + 30
    while time.time() < deadline:
        if _worker_is_healthy():
            return
        time.sleep(0.5)
    raise RuntimeError("Translation worker failed to start.")


def translate_via_worker(payload: dict) -> dict:
    ensure_translation_worker()
    response = requests.post(_translate_url(), json=payload, timeout=300)
    if not response.ok:
        detail = ""
        try:
            detail = response.json().get("detail", "")
        except Exception:
            detail = response.text
        raise RuntimeError(detail or f"Translation worker request failed: {response.status_code}")
    return response.json()
