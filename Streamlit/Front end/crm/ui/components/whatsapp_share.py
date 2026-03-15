import streamlit as st

from crm.data.whatsapp_groups import list_whatsapp_groups
from crm.services.whatsapp import (
    send_whatsapp_group_message,
    whatsapp_group_connection_configured,
)


def render_whatsapp_group_link_sender(
    *,
    key_prefix: str,
    source: str,
    link: str = "",
    default_message: str = "",
    title: str = "Send to WhatsApp group",
    send_button_label: str = "Send to WhatsApp group",
    append_link_by_default: bool = False,
    allow_append_group_invite: bool = True,
    disabled: bool = False,
):
    st.markdown(f"##### {title}")

    if disabled:
        st.caption("Sending is currently disabled.")
        return {
            "sent": False,
            "selected_group": None,
            "final_message": "",
            "error": "disabled",
        }

    if not whatsapp_group_connection_configured():
        st.caption(
            "WhatsApp webhook is not configured. Set WHATSAPP_GROUP_WEBHOOK_URL "
            "(and optional WHATSAPP_GROUP_WEBHOOK_TOKEN)."
        )
        return {
            "sent": False,
            "selected_group": None,
            "final_message": "",
            "error": "not_configured",
        }

    groups_df = list_whatsapp_groups()
    if groups_df.empty:
        st.caption("No WhatsApp groups found. Add groups first in Outreach.")
        return {
            "sent": False,
            "selected_group": None,
            "final_message": "",
            "error": "no_groups",
        }

    if str(link or "").strip().startswith("<APP_URL>"):
        st.warning(
            "Link base URL is unresolved (<APP_URL>). Set APP_URL in secrets before sending."
        )
        return {
            "sent": False,
            "selected_group": None,
            "final_message": "",
            "error": "unresolved_link",
        }

    options = {}
    for row in groups_df.itertuples(index=False):
        group_id = str(getattr(row, "groupId", "") or "").strip()
        name = str(getattr(row, "name", "") or "Unnamed group").strip()
        invite = str(getattr(row, "inviteLink", "") or "").strip()
        if not name:
            continue
        label = name if name not in options else f"{name} [{group_id[:8]}]"
        options[label] = {"groupId": group_id, "name": name, "inviteLink": invite}

    if not options:
        st.caption("No valid WhatsApp groups available.")
        return {
            "sent": False,
            "selected_group": None,
            "final_message": "",
            "error": "no_valid_groups",
        }

    choice_cols = st.columns([2, 1, 1])
    with choice_cols[0]:
        selected_label = st.selectbox(
            "WhatsApp group",
            options=[""] + list(options.keys()),
            key=f"{key_prefix}_wa_group",
        )
    with choice_cols[1]:
        append_link = st.checkbox(
            "Append link",
            value=append_link_by_default,
            key=f"{key_prefix}_wa_append_link",
            disabled=not bool(str(link or "").strip()),
        )
    with choice_cols[2]:
        append_invite = st.checkbox(
            "Append invite",
            value=False,
            key=f"{key_prefix}_wa_append_invite",
            disabled=not allow_append_group_invite,
        )

    selected_group = options.get(selected_label)
    message = (default_message or "").strip()

    if st.button(send_button_label, key=f"{key_prefix}_wa_send_btn"):
        if not selected_group:
            st.warning("Select a WhatsApp group first.")
            return {
                "sent": False,
                "selected_group": None,
                "final_message": message,
                "error": "missing_group",
            }

        final_message = message
        clean_link = str(link or "").strip()
        if append_link and clean_link:
            final_message = (final_message + f"\n\n{clean_link}").strip()
        invite = str(selected_group.get("inviteLink") or "").strip()
        if append_invite and invite:
            final_message = (final_message + f"\n\nGroup link: {invite}").strip()

        ok, error = send_whatsapp_group_message(
            group=selected_group,
            message=final_message,
            source=source,
        )
        if ok:
            st.success("Message sent to WhatsApp connector.")
            return {
                "sent": True,
                "selected_group": selected_group,
                "final_message": final_message,
                "error": None,
            }

        st.error(f"Could not send message: {error}")
        return {
            "sent": False,
            "selected_group": selected_group,
            "final_message": final_message,
            "error": error,
        }

    return {
        "sent": False,
        "selected_group": selected_group,
        "final_message": message,
        "error": None,
    }
