import requests

from crm.config import WHATSAPP_GROUP_WEBHOOK_TOKEN, WHATSAPP_GROUP_WEBHOOK_URL
from crm.utils.text import clean_text


def whatsapp_group_connection_configured():
    return bool(clean_text(WHATSAPP_GROUP_WEBHOOK_URL))


def _parse_error_detail(response):
    try:
        data = response.json()
        if isinstance(data, dict):
            return data.get("detail") or data.get("error") or str(data)
        return str(data)
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def send_whatsapp_group_message(group, message, source="outreach"):
    webhook_url = clean_text(WHATSAPP_GROUP_WEBHOOK_URL)
    if not webhook_url:
        return False, "WhatsApp webhook is not configured."

    message = clean_text(message)
    if not message:
        return False, "Message is empty."

    group = group or {}
    payload = {
        "platform": "whatsapp",
        "channel": "group",
        "source": clean_text(source) or "outreach",
        "group": {
            "groupId": clean_text(group.get("groupId")),
            "name": clean_text(group.get("name")),
            "inviteLink": clean_text(group.get("inviteLink")),
        },
        "message": message,
    }
    headers = {"Content-Type": "application/json"}
    token = clean_text(WHATSAPP_GROUP_WEBHOOK_TOKEN)
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, str(exc)

    if response.status_code >= 400:
        detail = _parse_error_detail(response)
        return False, f"Webhook rejected request ({response.status_code}): {detail}"
    return True, None
