import streamlit as st
from datetime import date

from crm.data.events import (
    EVENT_REGISTRATION_STATUSES,
    EVENT_STATUSES,
    create_event_for_people,
)
from crm.data.people import search_people
from crm.data.segments import list_segments, run_saved_segment, run_segment
from crm.data.tasks import TASK_STATUSES, bulk_create_tasks
from crm.data.whatsapp_groups import (
    delete_whatsapp_group,
    list_whatsapp_groups,
    upsert_whatsapp_group,
)
from crm.services.whatsapp import (
    send_whatsapp_group_message,
    whatsapp_group_connection_configured,
)
from crm.ui.components.table_utils import render_table_with_export
from crm.ui.pages.segments import render_segments_tab


def _render_template(template, context):
    if not template:
        return ""
    try:
        return template.format(**context)
    except Exception:
        return template


def _split_full_name(full_name):
    parts = [p for p in str(full_name or "").strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _build_people_rows_from_df(target_df):
    rows = []
    if target_df is None or target_df.empty:
        return rows
    for _, row in target_df.iterrows():
        email = str(row.get("email") or "").strip()
        if not email:
            continue
        first_name = str(row.get("firstName") or "").strip()
        last_name = str(row.get("lastName") or "").strip()
        if (not first_name and not last_name) and row.get("fullName"):
            first_name, last_name = _split_full_name(row.get("fullName"))
        rows.append(
            {
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "phone": str(row.get("phone") or "").strip(),
                "group": str(row.get("group") or "").strip(),
            }
        )
    return rows


def _render_event_builder(target_df, prefix):
    st.markdown("### Create event")
    people_rows = _build_people_rows_from_df(target_df)
    if not people_rows:
        st.info("No valid people with email in this audience.")
        return
    st.caption(f"Audience size: {len(people_rows):,} people")

    with st.form(f"{prefix}_event_form"):
        form_cols = st.columns(2)
        with form_cols[0]:
            name = st.text_input("Event name *", key=f"{prefix}_event_name")
            set_start = st.checkbox("Set start date", value=False, key=f"{prefix}_event_set_start")
            start_date_val = st.date_input(
                "Start date",
                value=date.today(),
                key=f"{prefix}_event_start",
                disabled=not set_start,
            )
            set_end = st.checkbox("Set end date", value=False, key=f"{prefix}_event_set_end")
            end_date_val = st.date_input(
                "End date",
                value=date.today(),
                key=f"{prefix}_event_end",
                disabled=not set_end,
            )
            location = st.text_input("Location", key=f"{prefix}_event_location")
        with form_cols[1]:
            status = st.selectbox("Status", EVENT_STATUSES, key=f"{prefix}_event_status")
            registration_status = st.selectbox(
                "Default registration status",
                EVENT_REGISTRATION_STATUSES,
                index=0,
                key=f"{prefix}_event_registration_status",
            )
            capacity = st.number_input(
                "Capacity",
                min_value=0,
                value=max(0, len(people_rows)),
                step=10,
                key=f"{prefix}_event_capacity",
            )
            notes = st.text_area("Notes", key=f"{prefix}_event_notes", height=80)

        create_event_clicked = st.form_submit_button("Create event for audience")

    if create_event_clicked:
        payload = {
            "name": name,
            "startDate": start_date_val.isoformat() if set_start else "",
            "endDate": end_date_val.isoformat() if set_end else "",
            "location": location,
            "status": status,
            "capacity": capacity,
            "notes": notes,
        }
        event_id = create_event_for_people(
            payload,
            people_rows,
            registration_status=registration_status,
        )
        if event_id:
            st.success(
                f"Event created and {len(people_rows):,} people registered. "
                f"Event ID: {event_id}"
            )
        else:
            st.error("Could not create event. Event name is required.")


def _render_task_builder(target_df, prefix):
    st.markdown("### Create tasks")
    presets = {
        "Call": "Call {fullName}",
        "Text": "Text {fullName}",
        "Email": "Email {fullName}",
        "Follow-up": "Follow up with {fullName}",
        "Custom": "",
    }
    preset_choice = st.selectbox(
        "Task preset",
        list(presets.keys()),
        index=0,
        key=f"{prefix}_task_preset",
        help="Pick a preset or use Custom and write your own template.",
    )
    title_key = f"{prefix}_task_title_template"
    if title_key not in st.session_state:
        st.session_state[title_key] = presets[preset_choice]
    if st.button(
        "Apply preset",
        key=f"{prefix}_apply_preset",
        help="Fill the task title template with the selected preset.",
    ):
        st.session_state[title_key] = presets[preset_choice]
    title_template = st.text_input(
        "Task title template",
        key=title_key,
        help="Use placeholders like {fullName}, {email}, {group}.",
    )
    desc_template = st.text_area(
        "Task notes (optional)",
        value="",
        key=f"{prefix}_task_desc_template",
        help="Optional notes. Same placeholders are supported.",
    )
    set_due = st.checkbox("Set due date", value=False, key=f"{prefix}_task_set_due")
    due_date_value = st.date_input(
        "Due date",
        value=date.today(),
        key=f"{prefix}_task_due",
        disabled=not set_due,
    )
    status = st.selectbox(
        "Task status",
        TASK_STATUSES,
        index=0,
        key=f"{prefix}_task_status",
    )
    if st.button(
        "Create tasks",
        key=f"{prefix}_create_tasks",
        help="Create tasks for everyone in the selected target list.",
    ):
        rows = []
        for _, row in target_df.iterrows():
            context = {key: row.get(key, "") for key in target_df.columns}
            rows.append(
                {
                    "email": row.get("email"),
                    "title": _render_template(title_template, context),
                    "description": _render_template(desc_template, context),
                    "dueDate": due_date_value.isoformat() if set_due else "",
                    "status": status,
                }
            )
        created = bulk_create_tasks(rows, default_status=status)
        if created:
            st.success(f"Created {created} tasks.")
        else:
            st.error("No tasks created (missing emails or titles).")


def _render_segment_outreach():
    st.markdown("### Segment outreach")
    st.caption("Step 1: create/manage segments. Step 2: use a segment for outreach.")
    st.markdown("#### Create / manage segments")
    render_segments_tab()

    st.markdown("---")
    st.markdown("#### Use segment for outreach")
    st.caption("Choose a saved segment and create outreach tasks in bulk.")
    segments_df = list_segments()
    if segments_df.empty:
        st.info("No saved segments yet. Create one above first.")
        return

    names = (
        segments_df["name"].dropna().tolist()
        if "name" in segments_df.columns
        else []
    )
    sel = st.selectbox(
        "Select segment",
        options=[""] + names,
        key="outreach_segment_select",
        help="Choose a segment to build an outreach list.",
    )
    if not sel:
        st.caption("Pick a segment to preview and create tasks.")
        return

    seg_rows = segments_df[segments_df["name"] == sel]
    seg_id = (
        seg_rows["segmentId"].iloc[0]
        if not seg_rows.empty and "segmentId" in seg_rows.columns
        else None
    )
    if not seg_id:
        st.error("Could not resolve segment.")
        return

    limit = st.number_input(
        "Preview limit",
        min_value=10,
        max_value=2000,
        value=200,
        step=50,
        key="outreach_preview_limit",
        help="Max number of people to preview + target for tasks.",
    )
    with st.spinner("Loading segment preview..."):
        rdf = run_saved_segment(seg_id, limit=limit)
    if rdf.empty:
        st.info("No matches for this segment.")
        return

    st.markdown("### Segment preview")
    st.caption(f"{len(rdf):,} people in this preview.")
    render_table_with_export(
        rdf,
        key_prefix="outreach_segment_preview",
        filename=f"segment_{seg_id}_preview.csv",
    )
    _render_task_builder(rdf, prefix="outreach_segment")

    st.markdown("---")
    st.markdown("### Events for outreach audiences")
    event_scope = st.radio(
        "Event audience",
        ["Selected segment", "All people"],
        horizontal=True,
        key="outreach_event_scope",
        help="Create an event and register either this segment or everyone.",
    )
    if event_scope == "Selected segment":
        event_target_df = rdf
    else:
        all_limit = st.number_input(
            "All-people preview limit",
            min_value=50,
            max_value=5000,
            value=500,
            step=50,
            key="outreach_all_people_limit",
            help="Safety limit for creating event registrations for all people.",
        )
        with st.spinner("Loading all people audience..."):
            event_target_df = run_segment({}, limit=all_limit)
        if event_target_df.empty:
            st.info("No people found for all-people audience.")
            return
        st.caption(f"All-people preview loaded: {len(event_target_df):,}")

    _render_event_builder(event_target_df, prefix="outreach_segment")


def _render_individual_outreach():
    st.markdown("### Individual outreach")
    st.caption("Select specific people and create outreach tasks.")
    with st.form("outreach_individual_search_form"):
        query = st.text_input(
            "Search people by name or email",
            key="outreach_individual_search",
            help="Find people to include in this outreach batch.",
        )
        search_clicked = st.form_submit_button("Search people")
    if search_clicked:
        query_clean = (query or "").strip()
        if len(query_clean) < 2:
            st.warning("Enter at least 2 characters to search.")
            st.session_state["outreach_individual_search_committed"] = ""
        else:
            st.session_state["outreach_individual_search_committed"] = query_clean
    committed_query = st.session_state.get("outreach_individual_search_committed", "")
    if not committed_query:
        st.info("Search to find people for individual outreach.")
        return

    with st.spinner("Searching people..."):
        matches = search_people(committed_query, limit=200)
    if matches.empty:
        st.info("No people found for that search.")
        return
    if "email" not in matches.columns:
        st.error("Search results missing email field.")
        return

    matches = matches.dropna(subset=["email"]).copy()
    if matches.empty:
        st.info("No people with valid email found.")
        return
    if "fullName" not in matches.columns:
        matches["fullName"] = matches["email"]
    if "group" not in matches.columns:
        matches["group"] = "Supporter"

    matches["label"] = (
        matches["fullName"].astype(str)
        + " — "
        + matches["email"].astype(str)
        + " ("
        + matches["group"].astype(str)
        + ")"
    )
    selected_labels = st.multiselect(
        "Choose people",
        options=matches["label"].tolist(),
        default=[],
        key="outreach_individual_selected",
        help="Select one or more people for this outreach task batch.",
    )
    if not selected_labels:
        st.caption("Select people to continue.")
        return

    target_df = matches[matches["label"].isin(selected_labels)].copy()
    if target_df.empty:
        st.info("No valid people selected.")
        return

    preview_cols = [
        col
        for col in ["fullName", "email", "group", "timeAvailability"]
        if col in target_df.columns
    ]
    st.markdown("### Selected people")
    st.caption(f"{len(target_df):,} people selected.")
    render_table_with_export(
        target_df[preview_cols] if preview_cols else target_df,
        key_prefix="outreach_individual_preview",
        filename="outreach_individual_preview.csv",
    )
    _render_task_builder(target_df, prefix="outreach_individual")


def _render_whatsapp_group_chats():
    st.markdown("### WhatsApp group chats")
    connected = whatsapp_group_connection_configured()
    st.write(f"**Connection**: {'Configured' if connected else 'Not configured'}")
    if not connected:
        st.caption(
            "Set `WHATSAPP_GROUP_WEBHOOK_URL` (and optional `WHATSAPP_GROUP_WEBHOOK_TOKEN`) "
            "in `.env` or Streamlit secrets."
        )

    with st.expander("Add / update WhatsApp group", expanded=False):
        with st.form("outreach_whatsapp_group_form", clear_on_submit=True):
            name = st.text_input("Group name")
            invite_link = st.text_input("Group invite link")
            notes = st.text_area("Notes (optional)")
            save_group = st.form_submit_button("Save group")
        if save_group:
            if not (name or "").strip() or not (invite_link or "").strip():
                st.warning("Group name and invite link are required.")
            elif upsert_whatsapp_group(name, invite_link, notes):
                st.success("WhatsApp group saved.")
            else:
                st.error("Could not save WhatsApp group.")

    groups_df = list_whatsapp_groups()
    if groups_df.empty:
        st.info("No WhatsApp groups yet. Add one to start campaigns.")
        return

    preview_cols = [c for c in ["name", "inviteLink", "notes", "updatedAt"] if c in groups_df.columns]
    render_table_with_export(
        groups_df[preview_cols] if preview_cols else groups_df,
        key_prefix="outreach_whatsapp_groups",
        filename="whatsapp_groups.csv",
    )

    group_names = groups_df["name"].dropna().tolist() if "name" in groups_df.columns else []
    selected_name = st.selectbox(
        "Select group chat",
        options=[""] + group_names,
        key="outreach_whatsapp_group_selected",
    )
    if not selected_name:
        st.caption("Select a group chat to send a message.")
        return

    selected_row_df = groups_df[groups_df["name"] == selected_name]
    if selected_row_df.empty:
        st.error("Selected group could not be loaded.")
        return
    selected_row = selected_row_df.iloc[0]
    group_payload = {
        "groupId": selected_row.get("groupId"),
        "name": selected_row.get("name"),
        "inviteLink": selected_row.get("inviteLink"),
    }

    message = st.text_area(
        "Campaign message",
        key="outreach_whatsapp_message",
        help="This message is sent to your webhook connector for WhatsApp group delivery.",
    )
    append_invite = st.checkbox(
        "Append invite link to message",
        value=False,
        key="outreach_whatsapp_append_invite",
    )
    if st.button("Send to WhatsApp group", key="outreach_whatsapp_send"):
        final_message = (message or "").strip()
        invite = (group_payload.get("inviteLink") or "").strip()
        if append_invite and invite:
            final_message = (final_message + f"\n\nGroup link: {invite}").strip()
        ok, error = send_whatsapp_group_message(
            group=group_payload,
            message=final_message,
            source="outreach_page",
        )
        if ok:
            st.success("Message sent to WhatsApp connector.")
        else:
            st.error(f"Could not send message: {error}")

    with st.expander("Delete selected group", expanded=False):
        if st.button("Delete group", key="outreach_whatsapp_delete"):
            group_id = selected_row.get("groupId")
            if delete_whatsapp_group(group_id):
                st.success("Group deleted.")
            else:
                st.error("Could not delete group.")


def render_outreach_page():
    st.subheader("Outreach")
    target_mode = st.radio(
        "Outreach target",
        ["Segments", "Individuals"],
        horizontal=True,
        key="outreach_target_mode",
        help="Use saved segments for bulk outreach or pick specific individuals.",
    )
    if target_mode == "Segments":
        _render_segment_outreach()
    else:
        _render_individual_outreach()

    _render_whatsapp_group_chats()
