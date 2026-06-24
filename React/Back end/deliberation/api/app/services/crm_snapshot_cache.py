from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

_MEMORY_SNAPSHOT: dict[str, Any] = {"mtime": None, "payload": None}

BACKEND_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CACHE_DIR = BACKEND_ROOT / "runtime" / "cache"
CACHE_DIR = Path(os.getenv("CRM_SNAPSHOT_CACHE_DIR", DEFAULT_CACHE_DIR)).resolve()
SNAPSHOT_PATH = CACHE_DIR / "crm_snapshot.json"
META_PATH = CACHE_DIR / "crm_snapshot_meta.json"
DEFAULT_FRESH_HOURS = int(os.getenv("CRM_SNAPSHOT_FRESH_HOURS", "24") or "24")
DEFAULT_DELETE_HOURS = int(os.getenv("CRM_SNAPSHOT_DELETE_HOURS", "72") or "72")
CACHE_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def ensure_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_json(path: Path, payload: Any) -> None:
    ensure_cache_dir()
    with NamedTemporaryFile("w", encoding="utf-8", dir=CACHE_DIR, delete=False) as tmp:
        json.dump(payload, tmp, ensure_ascii=False, indent=2, default=str)
        tmp.write("\n")
        temp_name = tmp.name
    Path(temp_name).replace(path)


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_snapshot_payload() -> dict | None:
    if not SNAPSHOT_PATH.exists():
        _MEMORY_SNAPSHOT["mtime"] = None
        _MEMORY_SNAPSHOT["payload"] = None
        return None
    try:
        mtime = SNAPSHOT_PATH.stat().st_mtime_ns
    except OSError:
        return None
    if _MEMORY_SNAPSHOT.get("mtime") == mtime:
        payload = _MEMORY_SNAPSHOT.get("payload")
        return payload if isinstance(payload, dict) else None
    payload = _read_json(SNAPSHOT_PATH)
    if isinstance(payload, dict):
        _MEMORY_SNAPSHOT["mtime"] = mtime
        _MEMORY_SNAPSHOT["payload"] = payload
        return payload
    _MEMORY_SNAPSHOT["mtime"] = None
    _MEMORY_SNAPSHOT["payload"] = None
    return None


def get_snapshot_token() -> str:
    meta = get_snapshot_meta()
    if not meta.get("exists"):
        return "missing"
    return str(meta.get("lastFetchedAt") or meta.get("snapshotBytes") or "snapshot")


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _base_meta() -> dict:
    now = utc_now()
    return {
        "cacheVersion": CACHE_VERSION,
        "status": "missing",
        "isFresh": False,
        "exists": SNAPSHOT_PATH.exists(),
        "lastFetchedAt": None,
        "expiresAt": None,
        "deleteAfter": None,
        "peopleCount": 0,
        "snapshotBytes": _file_size(SNAPSHOT_PATH),
        "freshHours": DEFAULT_FRESH_HOURS,
        "deleteHours": DEFAULT_DELETE_HOURS,
        "checkedAt": isoformat(now),
        "cacheDir": str(CACHE_DIR),
    }


def cleanup_expired_snapshot() -> bool:
    meta = _read_json(META_PATH) or {}
    delete_after = parse_dt(meta.get("deleteAfter"))
    if delete_after and utc_now() >= delete_after:
        for path in (SNAPSHOT_PATH, META_PATH):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        _MEMORY_SNAPSHOT["mtime"] = None
        _MEMORY_SNAPSHOT["payload"] = None
        return True
    return False


def get_snapshot_meta(changes_since_fetch: int | None = None) -> dict:
    cleanup_expired_snapshot()
    meta = _base_meta()
    saved = _read_json(META_PATH) or {}
    if not SNAPSHOT_PATH.exists() or not saved:
        meta["changesSinceFetch"] = changes_since_fetch
        return meta

    meta.update(saved)
    meta["exists"] = True
    meta["snapshotBytes"] = _file_size(SNAPSHOT_PATH)
    meta["cacheDir"] = str(CACHE_DIR)
    meta["checkedAt"] = isoformat(utc_now())
    expires_at = parse_dt(meta.get("expiresAt"))
    if expires_at and utc_now() < expires_at:
        meta["status"] = "fresh"
        meta["isFresh"] = True
    else:
        meta["status"] = "expired"
        meta["isFresh"] = False
    meta["changesSinceFetch"] = changes_since_fetch
    return meta


def read_snapshot_people(allow_expired: bool = True) -> list[dict] | None:
    meta = get_snapshot_meta()
    if not meta.get("exists"):
        return None
    if not allow_expired and not meta.get("isFresh"):
        return None
    payload = _read_snapshot_payload()
    if not isinstance(payload, dict):
        return None
    people = payload.get("people")
    return people if isinstance(people, list) else None


def write_snapshot(people: list[dict], source: str = "manual") -> dict:
    now = utc_now()
    expires_at = now + timedelta(hours=DEFAULT_FRESH_HOURS)
    delete_after = now + timedelta(hours=DEFAULT_DELETE_HOURS)
    meta = {
        "cacheVersion": CACHE_VERSION,
        "status": "fresh",
        "isFresh": True,
        "exists": True,
        "source": source,
        "lastFetchedAt": isoformat(now),
        "expiresAt": isoformat(expires_at),
        "deleteAfter": isoformat(delete_after),
        "peopleCount": len(people),
        "freshHours": DEFAULT_FRESH_HOURS,
        "deleteHours": DEFAULT_DELETE_HOURS,
    }
    _atomic_write_json(
        SNAPSHOT_PATH,
        {
            "meta": meta,
            "people": people,
        },
    )
    meta["snapshotBytes"] = _file_size(SNAPSHOT_PATH)
    _MEMORY_SNAPSHOT["mtime"] = None
    _MEMORY_SNAPSHOT["payload"] = None
    _atomic_write_json(META_PATH, meta)
    return get_snapshot_meta(changes_since_fetch=0)


def delete_snapshot() -> dict:
    for path in (SNAPSHOT_PATH, META_PATH):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    _MEMORY_SNAPSHOT["mtime"] = None
    _MEMORY_SNAPSHOT["payload"] = None
    return get_snapshot_meta(changes_since_fetch=None)
