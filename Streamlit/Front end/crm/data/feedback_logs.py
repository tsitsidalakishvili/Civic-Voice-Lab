import streamlit as st

from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text


def create_feedback_entry(
    *,
    name,
    email,
    page,
    message,
    channel="sidebar_feedback",
    email_status="not_configured",
    email_error="",
):
    message_text = clean_text(message)
    if not message_text:
        return False
    result = run_write(
        """
        CREATE (f:FeedbackEntry {
          feedbackId: randomUUID(),
          name: coalesce($name, ""),
          email: coalesce($email, ""),
          page: coalesce($page, ""),
          message: $message,
          channel: coalesce($channel, "sidebar_feedback"),
          emailStatus: coalesce($emailStatus, "not_configured"),
          emailError: coalesce($emailError, ""),
          createdAt: datetime()
        })
        """,
        {
            "name": clean_text(name) or "",
            "email": clean_text(email) or "",
            "page": clean_text(page) or "",
            "message": message_text,
            "channel": clean_text(channel) or "sidebar_feedback",
            "emailStatus": clean_text(email_status) or "not_configured",
            "emailError": clean_text(email_error) or "",
        },
    )
    if result:
        list_feedback_entries.clear()
    return result


@st.cache_data(ttl=30, show_spinner=False)
def list_feedback_entries(limit=300):
    return run_query(
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
        {"limit": max(1, int(limit or 300))},
        silent=True,
    )
