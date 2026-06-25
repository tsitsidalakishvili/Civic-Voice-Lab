import streamlit as st

import crm.db.neo4j as neo4j_db
from crm.clients.deliberation import delib_api_delete, delib_api_get
from crm.config import (
    DELIBERATION_API_FALLBACK_URL,
    DELIBERATION_API_URL,
    FEEDBACK_EMAIL_FROM,
    FEEDBACK_EMAIL_TO,
    PUBLIC_ONLY,
    SLACK_USERNAME,
    SLACK_WEBHOOK_URL,
    SUPPORTER_ACCESS_CODE,
    WHATSAPP_GROUP_WEBHOOK_URL,
)
from crm.data.events import delete_event, list_events
from crm.data.feedback_logs import list_feedback_entries
from crm.data.segments import delete_segment, list_segments
from crm.data.tasks import delete_task, list_tasks
from crm.data.whatsapp_groups import delete_whatsapp_group, list_whatsapp_groups
from crm.services.feedback import feedback_email_configured
from crm.services.slack import send_slack_message


def _render_delete_conversations():
    st.markdown("#### Deliberation conversations")
    conversations = delib_api_get("/conversations", show_error=False)
    if conversations is None:
        st.info("Deliberation API is offline. Conversation controls are unavailable.")
        return
    if not conversations:
        st.caption("No conversations found.")
        return

    rows = []
    options = {}
    for convo in conversations:
        convo_id = str(convo.get("id") or "").strip()
        topic = str(convo.get("topic") or "Untitled conversation").strip()
        if not convo_id:
            continue
        label = f"{topic} ({convo_id[:8]})"
        options[label] = convo_id
        rows.append(
            {
                "topic": topic,
                "conversationId": convo_id,
                "isOpen": bool(convo.get("is_open", True)),
                "createdAt": convo.get("created_at"),
            }
        )
    if not options:
        st.caption("No valid conversations available.")
        return
    st.dataframe(rows, use_container_width=True, height=220)

    selected_label = st.selectbox(
        "Select conversation to delete",
        options=list(options.keys()),
        key="admin_delete_conversation_select",
    )
    selected_id = options.get(selected_label)
    with st.form("admin_delete_conversation_form"):
        st.caption(f"Type `{selected_id}` to confirm permanent deletion.")
        confirmation = st.text_input(
            "Confirmation text",
            key="admin_delete_conversation_confirm",
        )
        submitted = st.form_submit_button("Delete conversation", type="primary")
    if submitted:
        if confirmation.strip() != selected_id:
            st.error("Confirmation text does not match conversation ID.")
        else:
            result = delib_api_delete(f"/conversations/{selected_id}")
            if result is not None and bool(result.get("deleted", False)):
                st.success("Conversation deleted.")
                st.rerun()
            else:
                st.error("Could not delete conversation.")


def _render_delete_events():
    st.markdown("#### Events")
    if neo4j_db.driver is None:
        st.info("Neo4j is not connected. Event controls are unavailable.")
        return
    events_df = list_events(limit=500)
    if events_df.empty:
        st.caption("No events found.")
        return
    st.dataframe(events_df, use_container_width=True, height=240)
    options = {}
    for row in events_df.itertuples(index=False):
        event_id = str(getattr(row, "eventId", "") or "").strip()
        name = str(getattr(row, "name", "") or "Untitled event").strip()
        start = str(getattr(row, "startDate", "") or "").strip()
        if not event_id:
            continue
        options[f"{name} ({start}) [{event_id[:8]}]"] = event_id
    if not options:
        st.caption("No valid events available.")
        return

    selected_label = st.selectbox(
        "Select event to delete",
        options=list(options.keys()),
        key="admin_delete_event_select",
    )
    selected_id = options.get(selected_label)
    with st.form("admin_delete_event_form"):
        st.caption(f"Type `{selected_id}` to confirm permanent deletion.")
        confirmation = st.text_input("Confirmation text", key="admin_delete_event_confirm")
        submitted = st.form_submit_button("Delete event", type="primary")
    if submitted:
        if confirmation.strip() != selected_id:
            st.error("Confirmation text does not match event ID.")
        elif delete_event(selected_id):
            st.success("Event deleted.")
            st.rerun()
        else:
            st.error("Could not delete event.")


def _render_delete_tasks():
    st.markdown("#### Tasks")
    if neo4j_db.driver is None:
        st.info("Neo4j is not connected. Task controls are unavailable.")
        return
    tasks_df = list_tasks(limit=500)
    if tasks_df.empty:
        st.caption("No tasks found.")
        return
    st.dataframe(tasks_df, use_container_width=True, height=240)
    options = {}
    for row in tasks_df.itertuples(index=False):
        task_id = str(getattr(row, "taskId", "") or "").strip()
        title = str(getattr(row, "title", "") or "Untitled task").strip()
        email = str(getattr(row, "email", "") or "").strip()
        if not task_id:
            continue
        options[f"{title} ({email}) [{task_id[:8]}]"] = task_id
    if not options:
        st.caption("No valid tasks available.")
        return

    selected_label = st.selectbox(
        "Select task to delete",
        options=list(options.keys()),
        key="admin_delete_task_select",
    )
    selected_id = options.get(selected_label)
    with st.form("admin_delete_task_form"):
        st.caption(f"Type `{selected_id}` to confirm permanent deletion.")
        confirmation = st.text_input("Confirmation text", key="admin_delete_task_confirm")
        submitted = st.form_submit_button("Delete task", type="primary")
    if submitted:
        if confirmation.strip() != selected_id:
            st.error("Confirmation text does not match task ID.")
        elif delete_task(selected_id):
            st.success("Task deleted.")
            st.rerun()
        else:
            st.error("Could not delete task.")


def _render_delete_segments():
    st.markdown("#### Segments")
    if neo4j_db.driver is None:
        st.info("Neo4j is not connected. Segment controls are unavailable.")
        return
    segments_df = list_segments()
    if segments_df.empty:
        st.caption("No segments found.")
        return
    st.dataframe(segments_df, use_container_width=True, height=220)
    options = {}
    for row in segments_df.itertuples(index=False):
        segment_id = str(getattr(row, "segmentId", "") or "").strip()
        name = str(getattr(row, "name", "") or "Unnamed segment").strip()
        if not segment_id:
            continue
        options[f"{name} [{segment_id[:8]}]"] = segment_id
    if not options:
        st.caption("No valid segments available.")
        return

    selected_label = st.selectbox(
        "Select segment to delete",
        options=list(options.keys()),
        key="admin_delete_segment_select",
    )
    selected_id = options.get(selected_label)
    with st.form("admin_delete_segment_form"):
        st.caption(f"Type `{selected_id}` to confirm permanent deletion.")
        confirmation = st.text_input("Confirmation text", key="admin_delete_segment_confirm")
        submitted = st.form_submit_button("Delete segment", type="primary")
    if submitted:
        if confirmation.strip() != selected_id:
            st.error("Confirmation text does not match segment ID.")
        elif delete_segment(selected_id):
            st.success("Segment deleted.")
            st.rerun()
        else:
            st.error("Could not delete segment.")


def _render_delete_whatsapp_groups():
    st.markdown("#### WhatsApp groups")
    if neo4j_db.driver is None:
        st.info("Neo4j is not connected. WhatsApp controls are unavailable.")
        return
    groups_df = list_whatsapp_groups()
    if groups_df.empty:
        st.caption("No WhatsApp groups found.")
        return
    st.dataframe(groups_df, use_container_width=True, height=220)
    options = {}
    for row in groups_df.itertuples(index=False):
        group_id = str(getattr(row, "groupId", "") or "").strip()
        name = str(getattr(row, "name", "") or "Unnamed group").strip()
        if not group_id:
            continue
        options[f"{name} [{group_id[:8]}]"] = group_id
    if not options:
        st.caption("No valid WhatsApp groups available.")
        return

    selected_label = st.selectbox(
        "Select WhatsApp group to delete",
        options=list(options.keys()),
        key="admin_delete_whatsapp_group_select",
    )
    selected_id = options.get(selected_label)
    with st.form("admin_delete_whatsapp_group_form"):
        st.caption(f"Type `{selected_id}` to confirm permanent deletion.")
        confirmation = st.text_input(
            "Confirmation text",
            key="admin_delete_whatsapp_group_confirm",
        )
        submitted = st.form_submit_button("Delete WhatsApp group", type="primary")
    if submitted:
        if confirmation.strip() != selected_id:
            st.error("Confirmation text does not match group ID.")
        elif delete_whatsapp_group(selected_id):
            st.success("WhatsApp group deleted.")
            st.rerun()
        else:
            st.error("Could not delete WhatsApp group.")


def render_admin_page():
    st.subheader("Admin")

    st.markdown("### System status")
    db_status = "Connected" if neo4j_db.driver is not None else "Not connected"
    st.write(f"**Neo4j**: {db_status}")

    delib_health = delib_api_get("/healthz", show_error=False) or {}
    delib_ok = delib_api_get("/conversations", show_error=False)
    health_status = str(delib_health.get("status") or "").strip().lower()
    if delib_ok is not None:
        delib_status = "Online"
    elif health_status in {"degraded", "error"}:
        delib_status = "Reachable but degraded"
    else:
        delib_status = "Offline / not configured"
    st.write(f"**Deliberation API**: {delib_status}")
    effective_urls = [str(DELIBERATION_API_URL or "").strip()]
    fallback_url = str(DELIBERATION_API_FALLBACK_URL or "").strip()
    if fallback_url and fallback_url not in effective_urls:
        effective_urls.append(fallback_url)
    st.caption(f"API URL(s): {', '.join([u for u in effective_urls if u]) or 'Not set'}")
    if delib_health:
        st.caption(
            "Health: "
            f"status={delib_health.get('status')} "
            f"db_ok={delib_health.get('db_ok')} "
            f"target={delib_health.get('target_source') or 'n/a'}"
        )

    st.markdown("### Access mode")
    st.write(f"**Public only**: {'Yes' if PUBLIC_ONLY else 'No'}")
    st.write(f"**Supporter access code set**: {'Yes' if SUPPORTER_ACCESS_CODE else 'No'}")

    st.markdown("### Feedback email")
    st.write(f"**Configured**: {'Yes' if feedback_email_configured() else 'No'}")
    st.write(f"**From**: {FEEDBACK_EMAIL_FROM or 'Not set'}")
    st.write(f"**To**: {FEEDBACK_EMAIL_TO or 'Not set'}")
    feedback_df = list_feedback_entries(limit=250)
    st.write(f"**Stored feedback entries (Neo4j)**: {len(feedback_df):,}")
    with st.expander("View feedback log", expanded=False):
        if feedback_df.empty:
            st.caption("No feedback entries stored yet.")
        else:
            st.dataframe(feedback_df, use_container_width=True, height=260)

    st.markdown("### WhatsApp")
    st.write(f"**Group webhook configured**: {'Yes' if WHATSAPP_GROUP_WEBHOOK_URL else 'No'}")

    st.markdown("### Slack")
    slack_configured = bool(SLACK_WEBHOOK_URL)
    st.write(f"**Webhook configured**: {'Yes' if slack_configured else 'No'}")
    st.write(f"**Username**: {SLACK_USERNAME or 'Not set'}")
    with st.form("admin_slack_test_form"):
        test_message = st.text_area(
            "Test Slack message",
            value="Freedom Square CRM is connected to Slack.",
            height=90,
        )
        send_test = st.form_submit_button("Send test message to Slack")
    if send_test:
        ok, error = send_slack_message(test_message, source="admin_page_test")
        if ok:
            st.success("Test message sent to Slack.")
        else:
            st.error(f"Could not send Slack test message: {error}")

    st.markdown("---")
    st.markdown("### Admin controls (delete records)")
    st.warning("Danger zone: deletions are permanent and cannot be undone.")
    convo_tab, event_tab, task_tab, segment_tab, whatsapp_tab = st.tabs(
        ["Conversations", "Events", "Tasks", "Segments", "WhatsApp groups"]
    )

    with convo_tab:
        _render_delete_conversations()
    with event_tab:
        _render_delete_events()
    with task_tab:
        _render_delete_tasks()
    with segment_tab:
        _render_delete_segments()
    with whatsapp_tab:
        _render_delete_whatsapp_groups()
