from __future__ import annotations

import json
from typing import Any

from ..db import get_active_database, get_driver
from .config import get_settings


OMIT_BY_DEFAULT = {
    "personalid",
    "personal_id",
    "nationalid",
    "national_id",
    "idnumber",
    "id_number",
    "dateofbirth",
    "birthdate",
    "fulldob",
    "exactaddress",
    "socialmedia",
    "social_media",
    "politicalviews",
    "political_views",
    "partydetails",
    "party_details",
    "waspartymember",
    "was_party_member",
    "formermembership",
    "former_membership",
    "topicsofinterest",
    "topics_of_interest",
    "interests",
}
MASK_BY_DEFAULT = {"email", "phone", "phonenumber", "phone_number", "address"}


def _mask_contact(field: str, value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    lowered = field.casefold()
    if "email" in lowered and "@" in text:
        _, domain = text.rsplit("@", 1)
        return f"***@{domain}"
    if "phone" in lowered:
        digits = "".join(char for char in text if char.isdigit())
        return f"***{digits[-4:]}" if digits else "***"
    if "address" in lowered:
        return "[masked address]"
    return "***"


def _load_policies(purpose_id: str) -> dict[str, dict]:
    if not purpose_id:
        return {}
    try:
        with get_driver().session(database=get_active_database()) as session:
            rows = session.run(
                """
                MATCH (purpose:ProcessingPurpose {purposeId: $purposeId, status: 'active'})
                WITH purpose ORDER BY purpose.version DESC LIMIT 1
                OPTIONAL MATCH (purpose)-[:HAS_FIELD_POLICY]->(policy:DataFieldPolicy)
                RETURN policy.field AS field, policy.classification AS classification,
                       policy.collection AS collection,
                       coalesce(policy.allowedRoles, []) AS allowedRoles,
                       coalesce(policy.masked, true) AS masked,
                       coalesce(policy.exportAllowed, false) AS exportAllowed,
                       coalesce(policy.counselDecision, 'pending') AS counselDecision
                """,
                {"purposeId": purpose_id},
            )
            return {
                str(row["field"]).casefold(): row.data()
                for row in rows
                if row.get("field")
            }
    except Exception:
        # Policy storage failure must never result in a more permissive response.
        return {}


def mask_response_payload(
    value: Any,
    *,
    roles: set[str],
    purpose_id: str,
    is_export: bool,
    policies: dict[str, dict] | None = None,
) -> tuple[Any, dict[str, list[str]]]:
    policy_map = policies if policies is not None else _load_policies(purpose_id)
    omitted: set[str] = set()
    masked: set[str] = set()

    def transform(item: Any, path: str = "") -> Any:
        if isinstance(item, list):
            return [transform(child, f"{path}[]") for child in item]
        if not isinstance(item, dict):
            return item
        result: dict[str, Any] = {}
        for key, child in item.items():
            key_text = str(key)
            normalized = key_text.casefold()
            child_path = f"{path}.{key_text}" if path else key_text
            policy = policy_map.get(normalized) or policy_map.get(child_path.casefold())
            allowed = False
            force_mask = False
            if policy and policy.get("counselDecision") == "approved":
                allowed_roles = set(policy.get("allowedRoles") or [])
                allowed = bool(roles.intersection(allowed_roles))
                if is_export and not policy.get("exportAllowed"):
                    allowed = False
                force_mask = bool(policy.get("masked"))
            if normalized in OMIT_BY_DEFAULT:
                if not allowed:
                    omitted.add(child_path)
                    continue
                if force_mask:
                    result[key_text] = _mask_contact(normalized, child)
                    masked.add(child_path)
                    continue
            if normalized in MASK_BY_DEFAULT:
                if not allowed or force_mask:
                    result[key_text] = _mask_contact(normalized, child)
                    masked.add(child_path)
                    continue
            result[key_text] = transform(child, child_path)
        return result

    return transform(value), {"omittedFields": sorted(omitted), "maskedFields": sorted(masked)}


class FieldMaskingMiddleware:
    """Last-mile JSON field authorization for route, cache, and error responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        settings = get_settings()
        if scope.get("type") != "http" or not settings.field_masking_enabled:
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        if path.startswith(("/auth", "/health", "/docs", "/openapi.json")) or path == "/":
            await self.app(scope, receive, send)
            return

        start_message = None
        body_parts: list[bytes] = []

        async def capture(message):
            nonlocal start_message
            if message["type"] == "http.response.start":
                start_message = message
                return
            if message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                assert start_message is not None
                headers = list(start_message.get("headers", []))
                content_type = next(
                    (value.decode("latin1") for name, value in headers if name.lower() == b"content-type"),
                    "",
                )
                body = b"".join(body_parts)
                if "application/json" in content_type and len(body) <= 4_000_000:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        state = scope.get("state") or {}
                        principal = state.get("principal") or {}
                        roles = set(principal.get("roles") or [])
                        purpose_id = str(state.get("purpose_id") or "")
                        transformed, access = mask_response_payload(
                            payload,
                            roles=roles,
                            purpose_id=purpose_id,
                            is_export=("export" in path.casefold() or path.casefold().endswith("/pdf")),
                        )
                        metadata = {
                            "purposeId": purpose_id or None,
                            "policy": "deny-by-default",
                            **access,
                        }
                        if isinstance(transformed, dict) and "_access" not in transformed:
                            transformed["_access"] = metadata
                        elif any(access.values()):
                            headers.append((b"x-fs-access-metadata", json.dumps(metadata, separators=(",", ":")).encode("latin1")))
                        body = json.dumps(transformed, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                        headers = [(name, value) for name, value in headers if name.lower() != b"content-length"]
                        headers.append((b"content-length", str(len(body)).encode("ascii")))
                    except (ValueError, UnicodeError, TypeError):
                        pass
                start_message["headers"] = headers
                await send(start_message)
                await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, capture)
