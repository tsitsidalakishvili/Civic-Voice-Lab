"""
CRM support endpoints that are not yet domain-specific enough for the split
people/tasks/events/campaigns modules.
"""

import os
import smtplib
from email.message import EmailMessage
from typing import List, Optional, Tuple

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import db_health, get_driver
from .routes_crm_helpers import (
    ENABLE_PAYMENTS,
    ENABLE_PUBLIC_CAMPAIGNS,
    MAX_CONTRIBUTION_AMOUNT,
    _clean_text,
    _db_session,
    _execute_read,
    _execute_write,
    _query_df,
)

router = APIRouter()


class AdminStatusOut(BaseModel):
    neo4j_status: str
    deliberation_status: str
    api_urls: List[str] = []
    feedback_configured: bool
    feedback_from: Optional[str] = None
    feedback_to: Optional[str] = None
    whatsapp_configured: bool
    slack_configured: bool
    slack_username: Optional[str] = None


class ClearDbRequest(BaseModel):
    confirm: str = Field(min_length=1)


class WhatsAppGroupCreate(BaseModel):
    name: str
    inviteLink: str
    notes: Optional[str] = ""


class WhatsAppGroupOut(BaseModel):
    group_id: str = Field(alias="groupId")
    name: str
    invite_link: str = Field(alias="inviteLink")
    notes: str = ""
    updated_at: Optional[str] = Field(alias="updatedAt", default=None)


class WhatsAppMessage(BaseModel):
    message: str
    appendInvite: Optional[bool] = False
    source: Optional[str] = "outreach_page"


def _count_graph(session) -> Tuple[int, int]:
    nodes_rows = _execute_read(session, "MATCH (n) RETURN count(n) AS count")
    rels_rows = _execute_read(session, "MATCH ()-[r]-() RETURN count(r) AS count")
    nodes = int((nodes_rows[0].get("count") if nodes_rows else 0) or 0)
    rels = int((rels_rows[0].get("count") if rels_rows else 0) or 0)
    return nodes, rels


def _parse_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def _feedback_email_configured():
    feedback_to = str(os.getenv("FEEDBACK_EMAIL_TO") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    return bool(feedback_to and smtp_host)


def _send_feedback_email(name: str, email: str, message: str, page: str):
    if not _feedback_email_configured():
        return False, "not_configured", None
    feedback_from = str(os.getenv("FEEDBACK_EMAIL_FROM") or "").strip()
    feedback_to = str(os.getenv("FEEDBACK_EMAIL_TO") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    smtp_user = str(os.getenv("SMTP_USER") or "").strip()
    smtp_password = str(os.getenv("SMTP_PASSWORD") or "").strip()
    smtp_port = _parse_int(os.getenv("SMTP_PORT"), 587)
    smtp_use_tls = str(os.getenv("SMTP_USE_TLS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    from_email = feedback_from or feedback_to

    msg = EmailMessage()
    msg["Subject"] = f"Feedback ({page or 'app'})"
    msg["From"] = from_email
    msg["To"] = feedback_to
    if email:
        msg["Reply-To"] = email
    msg.set_content(
        "\n".join(
            [
                f"Name: {name or 'Anonymous'}",
                f"Email: {email or 'Not provided'}",
                f"Page: {page or 'Unknown'}",
                "",
                message,
            ]
        )
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            if smtp_use_tls:
                server.starttls()
                server.ehlo()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, "sent", None
    except Exception as exc:
        return False, "failed", str(exc)


def _create_feedback_entry(
    *,
    name: str,
    email: str,
    page: str,
    message: str,
    channel: str,
    email_status: str,
    email_error: str,
):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            """
            CREATE (f:FeedbackEntry {
              feedbackId: randomUUID(),
              name: $name,
              email: $email,
              page: $page,
              message: $message,
              channel: $channel,
              emailStatus: $emailStatus,
              emailError: $emailError,
              createdAt: datetime()
            })
            """,
            {
                "name": name,
                "email": email,
                "page": page,
                "message": message,
                "channel": channel,
                "emailStatus": email_status,
                "emailError": email_error,
            },
        )


def _send_slack_message(
    *,
    message: str,
    username: str = "",
    channel: str = "",
    source: str = "",
):
    webhook_url = str(os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Slack webhook is not configured.")
    body = {"text": message}
    resolved_username = _clean_text(username) or _clean_text(os.getenv("SLACK_USERNAME"))
    if resolved_username:
        body["username"] = resolved_username
    resolved_channel = _clean_text(channel) or _clean_text(os.getenv("SLACK_CHANNEL"))
    if resolved_channel:
        body["channel"] = resolved_channel
    if _clean_text(source):
        body["icon_emoji"] = ":speech_balloon:"
    try:
        response = requests.post(
            webhook_url,
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Webhook rejected request ({response.status_code}): {response.text}",
        )


def _send_whatsapp_group_message(group: dict, message: str, source: str):
    webhook_url = str(os.getenv("WHATSAPP_GROUP_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=400, detail="WhatsApp webhook not configured.")
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message is empty.")
    payload = {
        "platform": "whatsapp",
        "channel": "group",
        "source": source or "outreach_page",
        "group": {
            "groupId": group.get("groupId"),
            "name": group.get("name"),
            "inviteLink": group.get("inviteLink"),
        },
        "message": message,
    }
    headers = {"Content-Type": "application/json"}
    token = str(os.getenv("WHATSAPP_GROUP_WEBHOOK_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.post(webhook_url, json=payload, headers=headers, timeout=20)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Webhook rejected request ({response.status_code}): {response.text}",
        )
    return {"ok": True}


@router.get("/whatsapp-groups", response_model=List[WhatsAppGroupOut])
def list_whatsapp_groups():
    driver = get_driver()
    query = """
    MATCH (g:WhatsAppGroup)
    RETURN
      g.groupId AS groupId,
      g.name AS name,
      coalesce(g.inviteLink, '') AS inviteLink,
      coalesce(g.notes, '') AS notes,
      toString(g.updatedAt) AS updatedAt
    ORDER BY g.updatedAt DESC
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query)
    return [record.data() for record in records]


@router.post("/whatsapp-groups", response_model=WhatsAppGroupOut)
def upsert_whatsapp_group(payload: WhatsAppGroupCreate):
    if not payload.name.strip() or not payload.inviteLink.strip():
        raise HTTPException(status_code=400, detail="Name and inviteLink are required")
    driver = get_driver()
    query = """
    MERGE (g:WhatsAppGroup {name: $name})
    ON CREATE SET g.groupId = randomUUID(), g.createdAt = datetime()
    SET g.inviteLink = $inviteLink,
        g.notes = $notes,
        g.updatedAt = datetime()
    RETURN
      g.groupId AS groupId,
      g.name AS name,
      coalesce(g.inviteLink, '') AS inviteLink,
      coalesce(g.notes, '') AS notes,
      toString(g.updatedAt) AS updatedAt
    """
    with _db_session(driver) as session:
        records = _execute_write(
            session,
            query,
            {
                "name": payload.name.strip(),
                "inviteLink": payload.inviteLink.strip(),
                "notes": payload.notes or "",
            },
        )
    if not records:
        raise HTTPException(status_code=500, detail="WhatsApp group could not be saved")
    return records[0].data()


@router.delete("/whatsapp-groups/{group_id}")
def delete_whatsapp_group(group_id: str):
    driver = get_driver()
    with _db_session(driver) as session:
        _execute_write(
            session,
            "MATCH (g:WhatsAppGroup {groupId: $groupId}) DETACH DELETE g",
            {"groupId": group_id},
        )
    return {"deleted": True, "group_id": group_id}


@router.post("/whatsapp-groups/{group_id}/send")
def send_whatsapp_group_message(group_id: str, payload: WhatsAppMessage):
    driver = get_driver()
    query = """
    MATCH (g:WhatsAppGroup {groupId: $groupId})
    RETURN g.groupId AS groupId, g.name AS name, g.inviteLink AS inviteLink
    """
    with _db_session(driver) as session:
        records = _execute_read(session, query, {"groupId": group_id})
    if not records:
        raise HTTPException(status_code=404, detail="WhatsApp group not found")
    group = records[0].data()
    message = payload.message.strip()
    if payload.appendInvite and group.get("inviteLink"):
        message = f"{message}\n\nGroup link: {group.get('inviteLink')}".strip()
    return _send_whatsapp_group_message(group, message, payload.source or "outreach_page")


@router.get("/admin/status", response_model=AdminStatusOut)
def admin_status():
    health = db_health()
    neo4j_status = "Connected" if health.get("ok") else "Not connected"
    deliberation_status = "Online" if health.get("ok") else "Reachable but degraded"
    api_urls = [str(os.getenv("DELIBERATION_API_URL") or "").strip()]
    fallback = str(os.getenv("DELIBERATION_API_FALLBACK_URL") or "").strip()
    if fallback and fallback not in api_urls:
        api_urls.append(fallback)
    feedback_to = str(os.getenv("FEEDBACK_EMAIL_TO") or "").strip()
    smtp_host = str(os.getenv("SMTP_HOST") or "").strip()
    return {
        "neo4j_status": neo4j_status,
        "deliberation_status": deliberation_status,
        "api_urls": [u for u in api_urls if u],
        "feedback_configured": bool(feedback_to and smtp_host),
        "feedback_from": str(os.getenv("FEEDBACK_EMAIL_FROM") or "").strip() or None,
        "feedback_to": feedback_to or None,
        "whatsapp_configured": bool(str(os.getenv("WHATSAPP_GROUP_WEBHOOK_URL") or "").strip()),
        "slack_configured": bool(str(os.getenv("SLACK_WEBHOOK_URL") or "").strip()),
        "slack_username": str(os.getenv("SLACK_USERNAME") or "").strip() or None,
    }


@router.get("/admin/feature-flags")
def admin_feature_flags():
    return {
        "enable_public_campaigns": ENABLE_PUBLIC_CAMPAIGNS,
        "enable_payments": ENABLE_PAYMENTS,
        "max_contribution_amount": MAX_CONTRIBUTION_AMOUNT,
    }


@router.get("/admin/feedback")
def list_feedback_entries(limit: int = Query(300, ge=1, le=2000)):
    df = _query_df(
        """
        MATCH (f:FeedbackEntry)
        RETURN
          f.feedbackId AS feedbackId,
          coalesce(f.page, '') AS page,
          coalesce(f.name, '') AS name,
          coalesce(f.email, '') AS email,
          coalesce(f.channel, '') AS channel,
          coalesce(f.emailStatus, '') AS emailStatus,
          coalesce(f.emailError, '') AS emailError,
          coalesce(f.message, '') AS message,
          toString(f.createdAt) AS createdAt
        ORDER BY f.createdAt DESC
        LIMIT $limit
        """,
        {"limit": int(limit)},
    )
    return df.to_dict(orient="records") if not df.empty else []


@router.post("/admin/clear-db")
def clear_aura_db(payload: ClearDbRequest):
    confirm = _clean_text(payload.confirm)
    if confirm != "CLEAR AURA DB":
        raise HTTPException(
            status_code=400, detail="Confirmation text must be 'CLEAR AURA DB'."
        )
    driver = get_driver()
    with _db_session(driver) as session:
        nodes, rels = _count_graph(session)
        _execute_write(session, "MATCH (n) DETACH DELETE n")
    return {
        "ok": True,
        "deleted_nodes": nodes,
        "deleted_relationships": rels,
    }


@router.post("/feedback")
def create_feedback(payload: dict):
    message = _clean_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    name = _clean_text(payload.get("name"))
    email = _clean_text(payload.get("email"))
    page = _clean_text(payload.get("page")) or "App"
    channel = _clean_text(payload.get("channel")) or "sidebar_feedback"

    _, email_status, email_error = _send_feedback_email(name, email, message, page)
    _create_feedback_entry(
        name=name or "",
        email=email or "",
        page=page,
        message=message,
        channel=channel,
        email_status=email_status,
        email_error=email_error or "",
    )
    return {
        "ok": True,
        "email_status": email_status,
        "email_error": email_error,
    }


@router.post("/admin/slack-test")
def send_slack_test(payload: dict):
    message = _clean_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    _send_slack_message(
        message=message,
        username=_clean_text(payload.get("username")),
        channel=_clean_text(payload.get("channel")),
        source=_clean_text(payload.get("source")) or "admin_test",
    )
    return {"ok": True}


@router.post("/slack/send")
def send_slack_message(payload: dict):
    message = _clean_text(payload.get("message"))
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    _send_slack_message(
        message=message,
        username=_clean_text(payload.get("username")),
        channel=_clean_text(payload.get("channel")),
        source=_clean_text(payload.get("source")) or "frontend_share",
    )
    return {"ok": True}
