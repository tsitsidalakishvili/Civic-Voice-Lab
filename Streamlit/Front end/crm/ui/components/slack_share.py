import streamlit as st

from crm.services.slack import send_slack_message, slack_connection_configured


def render_slack_link_sender(
    *,
    key_prefix: str,
    source: str,
    link: str = "",
    default_message: str = "",
    title: str = "Send to Slack",
    send_button_label: str = "Send to Slack",
    append_link_by_default: bool = False,
    disabled: bool = False,
):
    st.markdown(f"##### {title}")

    if disabled:
        st.caption("Sending is currently disabled.")
        return {"sent": False, "final_message": "", "error": "disabled"}

    if not slack_connection_configured():
        st.caption("Slack is not configured. Set SLACK_WEBHOOK_URL in secrets or .env.")
        return {"sent": False, "final_message": "", "error": "not_configured"}

    if str(link or "").strip().startswith("<APP_URL>"):
        st.warning(
            "Link base URL is unresolved (<APP_URL>). Set APP_URL in secrets before sending."
        )
        return {"sent": False, "final_message": "", "error": "unresolved_link"}

    append_link = st.checkbox(
        "Append link",
        value=append_link_by_default,
        key=f"{key_prefix}_slack_append_link",
        disabled=not bool(str(link or "").strip()),
    )
    message = (default_message or "").strip()

    if st.button(send_button_label, key=f"{key_prefix}_slack_send_btn"):
        final_message = message
        clean_link = str(link or "").strip()
        if append_link and clean_link:
            final_message = (final_message + f"\n\n{clean_link}").strip()

        ok, error = send_slack_message(
            final_message,
            source=source,
        )
        if ok:
            st.success("Message sent to Slack.")
            return {"sent": True, "final_message": final_message, "error": None}

        st.error(f"Could not send message: {error}")
        return {"sent": False, "final_message": final_message, "error": error}

    return {"sent": False, "final_message": message, "error": None}
