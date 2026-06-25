import os

import streamlit as st
from dotenv import load_dotenv

try:
    from streamlit.errors import StreamlitSecretNotFoundError
except Exception:
    class StreamlitSecretNotFoundError(Exception):
        """Fallback for older Streamlit versions."""


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"), override=True)

def _get_secret_value(key):
    """
    Read a key from Streamlit secrets if available.
    Supports both top-level keys and one-level nested sections.
    """
    try:
        if key in st.secrets:
            return st.secrets.get(key)
        for section in st.secrets.values():
            if isinstance(section, dict) and key in section:
                return section.get(key)
    except (StreamlitSecretNotFoundError, FileNotFoundError, RuntimeError, Exception):
        return None
    return None


def get_config(key, default=None):
    secret_value = _get_secret_value(key)
    if secret_value is not None:
        return secret_value
    value = os.getenv(key)
    return value if value is not None else default


NEO4J_URI = get_config("NEO4J_URI")
NEO4J_USER = get_config("NEO4J_USER") or get_config("NEO4J_USERNAME") or "neo4j"
NEO4J_PASSWORD = get_config("NEO4J_PASSWORD")
NEO4J_DATABASE = get_config("NEO4J_DATABASE", "neo4j")
NEO4J_SANDBOX_URI = get_config("NEO4J_SANDBOX_URI")
NEO4J_SANDBOX_USER = (
    get_config("NEO4J_SANDBOX_USER") or get_config("NEO4J_SANDBOX_USERNAME") or "neo4j"
)
NEO4J_SANDBOX_PASSWORD = get_config("NEO4J_SANDBOX_PASSWORD")
NEO4J_SANDBOX_DATABASE = get_config("NEO4J_SANDBOX_DATABASE", "neo4j")
DELIBERATION_API_URL = (
    get_config("DELIBERATION_API_URL")
    or get_config("API_URL")
    or "http://localhost:8010"
)
DELIBERATION_API_FALLBACK_URL = get_config("DELIBERATION_API_FALLBACK_URL") or DELIBERATION_API_URL
SUPPORTER_ACCESS_CODE = get_config("SUPPORTER_ACCESS_CODE")
PUBLIC_ONLY = str(get_config("PUBLIC_ONLY", "false")).lower() in {"1", "true", "yes", "y"}

FEEDBACK_EMAIL_TO = get_config("FEEDBACK_EMAIL_TO")
FEEDBACK_EMAIL_FROM = get_config("FEEDBACK_EMAIL_FROM") or FEEDBACK_EMAIL_TO
SMTP_HOST = get_config("SMTP_HOST")
SMTP_PORT = get_config("SMTP_PORT", "587")
SMTP_USER = get_config("SMTP_USER")
SMTP_PASSWORD = get_config("SMTP_PASSWORD")
SMTP_USE_TLS = str(get_config("SMTP_USE_TLS", "true")).lower() in {"1", "true", "yes", "y"}
DELIBERATION_API_TIMEOUT_S = get_config("DELIBERATION_API_TIMEOUT_S", "20")
WHATSAPP_GROUP_WEBHOOK_URL = get_config("WHATSAPP_GROUP_WEBHOOK_URL")
WHATSAPP_GROUP_WEBHOOK_TOKEN = get_config("WHATSAPP_GROUP_WEBHOOK_TOKEN")
SLACK_WEBHOOK_URL = get_config("SLACK_WEBHOOK_URL")
SLACK_USERNAME = get_config("SLACK_USERNAME", "Freedom Square CRM")
