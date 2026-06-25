import requests

from crm.config import SLACK_USERNAME, SLACK_WEBHOOK_URL
from crm.utils.text import clean_text


def slack_connection_configured():
    return bool(clean_text(SLACK_WEBHOOK_URL))


def _parse_error_detail(response):
    try:
        data = response.json()
        if isinstance(data, dict):
            return data.get("detail") or data.get("error") or str(data)
        return str(data)
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def send_slack_message(message, source="crm", username=None):
    webhook_url = clean_text(SLACK_WEBHOOK_URL)
    if not webhook_url:
        return False, "Slack webhook is not configured."

    message = clean_text(message)
    if not message:
        return False, "Message is empty."

    sender = clean_text(username) or clean_text(SLACK_USERNAME)
    payload = {"text": message}
    if sender:
        payload["username"] = sender
    if clean_text(source):
        payload["icon_emoji"] = ":speech_balloon:"

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
    except requests.RequestException as exc:
        return False, str(exc)

    if response.status_code >= 400:
        detail = _parse_error_detail(response)
        return False, f"Webhook rejected request ({response.status_code}): {detail}"
    return True, None
