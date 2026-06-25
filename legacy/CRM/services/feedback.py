import smtplib
from email.message import EmailMessage

import streamlit as st

from crm.config import (
    FEEDBACK_EMAIL_FROM,
    FEEDBACK_EMAIL_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)
from crm.data.feedback_logs import create_feedback_entry


def _parse_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def feedback_email_configured():
    return bool(FEEDBACK_EMAIL_TO and SMTP_HOST)


def send_feedback_email(name, email, message, page=None):
    if not feedback_email_configured():
        return False, "Email feedback is not configured."
    from_email = FEEDBACK_EMAIL_FROM or FEEDBACK_EMAIL_TO
    msg = EmailMessage()
    msg["Subject"] = f"Feedback ({page or 'app'})"
    msg["From"] = from_email
    msg["To"] = FEEDBACK_EMAIL_TO
    if email:
        msg["Reply-To"] = email

    body_lines = [
        f"Name: {name or 'Anonymous'}",
        f"Email: {email or 'Not provided'}",
        f"Page: {page or 'Unknown'}",
        "",
        message,
    ]
    msg.set_content("\n".join(body_lines))

    port = _parse_int(SMTP_PORT, 587)
    try:
        with smtplib.SMTP(SMTP_HOST, port, timeout=20) as server:
            server.ehlo()
            if SMTP_USE_TLS:
                server.starttls()
                server.ehlo()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD or "")
            server.send_message(msg)
        return True, None
    except Exception as exc:
        return False, str(exc)


def render_feedback_widget(page_label="App", key_prefix: str = ""):
    normalized_prefix = str(key_prefix or page_label or "app").strip().lower().replace(" ", "_")
    form_key = f"{normalized_prefix}_feedback_form"
    name_key = f"{normalized_prefix}_feedback_name"
    email_key = f"{normalized_prefix}_feedback_email"
    message_key = f"{normalized_prefix}_feedback_message"
    with st.sidebar.expander("Feedback", expanded=False):
        st.caption("Send feedback to the team. Feedback is stored in Neo4j for documentation.")
        email_ready = feedback_email_configured()
        st.caption(
            f"Email delivery: {'enabled' if email_ready else 'not configured'} "
            "(storage in Neo4j remains active)."
        )
        with st.form(form_key, clear_on_submit=True):
            name = st.text_input("Name (optional)", key=name_key)
            email = st.text_input("Email (optional)", key=email_key)
            message = st.text_area("Your feedback", key=message_key)
            submitted = st.form_submit_button("Send feedback")
        if submitted:
            if not message.strip():
                st.warning("Please enter a message.")
            else:
                email_ok = False
                email_error = None
                email_status = "not_configured"
                if email_ready:
                    email_ok, email_error = send_feedback_email(
                        name.strip(),
                        email.strip(),
                        message.strip(),
                        page=page_label,
                    )
                    email_status = "sent" if email_ok else "failed"
                save_ok = create_feedback_entry(
                    name=name.strip(),
                    email=email.strip(),
                    page=page_label,
                    message=message.strip(),
                    email_status=email_status,
                    email_error=email_error or "",
                )
                if save_ok and email_status == "sent":
                    st.success("Thanks! Feedback saved and emailed.")
                elif save_ok and email_status == "failed":
                    st.warning(
                        "Feedback saved in Neo4j, but email delivery failed. "
                        f"Error: {email_error}"
                    )
                elif save_ok:
                    st.success("Thanks! Feedback saved in Neo4j.")
                else:
                    if email_status == "sent":
                        st.warning(
                            "Feedback email was sent, but saving to Neo4j failed. "
                            "Check database connection."
                        )
                    else:
                        st.error("Could not save feedback. Check Neo4j connection.")
