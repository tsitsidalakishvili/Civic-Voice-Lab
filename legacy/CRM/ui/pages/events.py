import streamlit as st
import pandas as pd
import altair as alt
from datetime import date
from urllib.parse import urlencode
import os

from crm.data.events import (
    EVENT_REGISTRATION_STATUSES,
    EVENT_STATUSES,
    create_event,
    get_event,
    list_registration_status_counts,
    list_event_registrations,
    list_events,
    register_person_to_event,
)
from crm.ui.components.slack_share import render_slack_link_sender
from crm.ui.components.table_utils import render_table_with_export
from crm.ui.components.whatsapp_share import render_whatsapp_group_link_sender


def _split_full_name(full_name):
    parts = [p for p in (full_name or "").strip().split() if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _normalize_base_url(value):
    text = (value or "").strip()
    if not text:
        return ""
    return text.rstrip("/")


def _detect_base_url():
    configured = _normalize_base_url(
        os.getenv("APP_URL") or os.getenv("PUBLIC_APP_URL") or os.getenv("STREAMLIT_APP_URL")
    )
    if configured:
        return configured

    try:
        headers = getattr(getattr(st, "context", None), "headers", None)
        if headers:
            host = headers.get("x-forwarded-host") or headers.get("host")
            if host:
                proto = headers.get("x-forwarded-proto") or "https"
                prefix = headers.get("x-forwarded-prefix") or ""
                return _normalize_base_url(f"{proto}://{host}{prefix}")
    except Exception:
        pass

    try:
        from streamlit.web.server.websocket_headers import _get_websocket_headers

        headers = _get_websocket_headers() or {}
        host = headers.get("x-forwarded-host") or headers.get("host")
        if host:
            proto = headers.get("x-forwarded-proto") or "https"
            prefix = headers.get("x-forwarded-prefix") or ""
            return _normalize_base_url(f"{proto}://{host}{prefix}")
    except Exception:
        pass
    return "<APP_URL>"


def _build_app_link(params):
    base = _detect_base_url()
    return f"{base}?{urlencode(params)}"


def _show_link_hint_if_needed(link):
    if link.startswith("<APP_URL>"):
        st.caption(
            "Could not auto-detect your app URL in this environment. "
            "Set APP_URL in Streamlit secrets for fully qualified links."
        )


def _render_participant_registration_form(*, event_id, event_title, key_prefix):
    with st.form(f"{key_prefix}_registration_form", clear_on_submit=True):
        full_name = st.text_input("Full name *", key=f"{key_prefix}_full_name")
        email = st.text_input("Email *", key=f"{key_prefix}_email")
        phone = st.text_input("Phone (optional)", key=f"{key_prefix}_phone")
        group = st.selectbox(
            "Group",
            ["Supporter", "Member"],
            key=f"{key_prefix}_group",
        )
        registration_notes = st.text_area(
            "Notes (optional)",
            key=f"{key_prefix}_notes",
            height=80,
        )
        register_clicked = st.form_submit_button("Register")

    if register_clicked:
        first_name, last_name = _split_full_name(full_name)
        person_payload = {
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "phone": phone,
            "group": group,
        }
        if not str(email or "").strip():
            st.error("Email is required.")
        elif not str(full_name or "").strip():
            st.error("Full name is required.")
        elif register_person_to_event(
            event_id,
            person_payload,
            status="Registered",
            notes=registration_notes,
        ):
            st.success(f"Thanks! You are registered for {event_title}.")
        else:
            st.error("Could not register right now. Please try again.")


def render_event_registration_page(event_id=None, event_key=None):
    event = get_event(event_id=event_id, event_key=event_key)
    if not event:
        st.error("Event not found.")
        return

    st.subheader(event.get("name") or "Event registration")
    meta_bits = []
    if event.get("startDate"):
        meta_bits.append(f"Date: {event.get('startDate')}")
    if event.get("location"):
        meta_bits.append(f"Location: {event.get('location')}")
    if meta_bits:
        st.caption(" | ".join(meta_bits))
    if event.get("notes"):
        st.caption(event.get("notes"))

    st.markdown("### Registration form")
    _render_participant_registration_form(
        event_id=event.get("eventId"),
        event_title=event.get("name") or "the event",
        key_prefix=f"public_event_{event.get('eventId')}",
    )


def render_events_page():
    st.subheader("Events")

    events_df = list_events()
    status_df = (
        list_registration_status_counts(limit_events=20)
        if not events_df.empty
        else pd.DataFrame()
    )

    st.markdown("### Event statistics")
    total_events = int(len(events_df))
    if "registrations" in events_df.columns:
        total_regs = int(
            pd.to_numeric(events_df["registrations"], errors="coerce").fillna(0).sum()
        )
    else:
        total_regs = 0
    attended_count = 0
    if (
        not status_df.empty
        and "registrationStatus" in status_df.columns
        and "count" in status_df.columns
    ):
        attended_count = int(
            pd.to_numeric(
                status_df.loc[status_df["registrationStatus"] == "Attended", "count"],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        )
    attendance_rate = (attended_count / total_regs * 100.0) if total_regs else 0.0
    metrics = st.columns(4)
    metrics[0].metric("Events", f"{total_events:,}")
    metrics[1].metric("Registrations", f"{total_regs:,}")
    metrics[2].metric("Attended", f"{attended_count:,}")
    metrics[3].metric("Attendance rate", f"{attendance_rate:.1f}%")

    if not status_df.empty:
        chart_cols = st.columns(2)
        status_totals = (
            status_df.groupby("registrationStatus", as_index=False)["count"].sum()
        )
        status_chart = (
            alt.Chart(status_totals)
            .mark_bar()
            .encode(
                x=alt.X("registrationStatus:N", title="Registration status"),
                y=alt.Y("count:Q", title="Count"),
                tooltip=["registrationStatus:N", "count:Q"],
                color=alt.Color("registrationStatus:N", legend=None),
            )
        )
        chart_cols[0].altair_chart(status_chart, use_container_width=True)

        by_event = (
            status_df.groupby("eventName", as_index=False)["count"].sum()
            .sort_values("count", ascending=False)
            .head(10)
        )
        event_chart = (
            alt.Chart(by_event)
            .mark_bar()
            .encode(
                y=alt.Y("eventName:N", sort="-x", title="Event"),
                x=alt.X("count:Q", title="Registrations"),
                tooltip=["eventName:N", "count:Q"],
            )
        )
        chart_cols[1].altair_chart(event_chart, use_container_width=True)
    else:
        st.caption("No registration analytics yet. Registrations will appear after signups.")

    st.markdown("---")

    with st.expander("Create event", expanded=True):
        with st.form("events_create_form"):
            form_cols = st.columns(2)
            with form_cols[0]:
                name = st.text_input("Event name *", key="events_name")
                set_start = st.checkbox("Set start date", value=False, key="events_set_start")
                start_date_val = st.date_input(
                    "Start date",
                    value=date.today(),
                    key="events_start",
                    disabled=not set_start,
                )
                set_end = st.checkbox("Set end date", value=False, key="events_set_end")
                end_date_val = st.date_input(
                    "End date",
                    value=date.today(),
                    key="events_end",
                    disabled=not set_end,
                )
                location = st.text_input("Location", key="events_location")
            with form_cols[1]:
                status = st.selectbox(
                    "Status",
                    EVENT_STATUSES,
                    key="events_status",
                )
                capacity = st.number_input(
                    "Capacity",
                    min_value=0,
                    value=0,
                    step=10,
                    key="events_capacity",
                )
                notes = st.text_area("Notes", key="events_notes", height=80)
            create_clicked = st.form_submit_button("Create event")

        if create_clicked:
            ok = create_event(
                {
                    "name": name,
                    "startDate": start_date_val.isoformat() if set_start else "",
                    "endDate": end_date_val.isoformat() if set_end else "",
                    "location": location,
                    "status": status,
                    "capacity": capacity,
                    "notes": notes,
                }
            )
            if ok:
                st.success("Event created.")
                events_df = list_events()
            else:
                st.error("Event name is required.")

    if events_df.empty:
        st.info("No events found yet. Create an event first.")
    else:
        event_labels = []
        event_lookup = {}
        for _, row in events_df.iterrows():
            start = (row.get("startDate") or "").strip()
            start_label = f" — {start}" if start else ""
            label = f"{row.get('name', 'Untitled event')}{start_label}"
            if label in event_lookup:
                label = f"{label} ({str(row.get('eventId'))[:8]})"
            event_lookup[label] = row.get("eventId")
            event_labels.append(label)

        with st.expander("Participant registration link (shareable)", expanded=False):
            selected_event_label = st.selectbox(
                "Event",
                options=[""] + event_labels,
                key="events_share_link_event",
                help="Generate a public form link for participants.",
            )
            selected_event_id = event_lookup.get(selected_event_label)
            if selected_event_id:
                public_link = _build_app_link(
                    {"questionnaire": "event_registration", "event_id": selected_event_id}
                )
                st.text_input(
                    "Participant registration link",
                    value=public_link,
                    key="events_share_link_value",
                    help="Share this link so participants can register themselves.",
                )
                _show_link_hint_if_needed(public_link)
                st.text_area(
                    "Message to send",
                    value=(
                        f"Event registration: {selected_event_label}\n\n"
                        f"Please register using this link:\n{public_link}"
                    ),
                    height=120,
                    key="events_share_link_message",
                )
                render_whatsapp_group_link_sender(
                    key_prefix=f"events_share_link_{selected_event_id}",
                    source="events_registration_share",
                    link=public_link,
                    default_message=st.session_state.get(
                        "events_share_link_message",
                        (
                            f"Event registration: {selected_event_label}\n\n"
                            f"Please register using this link:\n{public_link}"
                        ),
                    ),
                    title="Send event registration link to WhatsApp group",
                    send_button_label="Send event link to WhatsApp group",
                    append_link_by_default=False,
                )
                render_slack_link_sender(
                    key_prefix=f"events_share_link_slack_{selected_event_id}",
                    source="events_registration_share",
                    link=public_link,
                    default_message=st.session_state.get(
                        "events_share_link_message",
                        (
                            f"Event registration: {selected_event_label}\n\n"
                            f"Please register using this link:\n{public_link}"
                        ),
                    ),
                    title="Send event registration link to Slack",
                    send_button_label="Send event link to Slack",
                    append_link_by_default=False,
                )

        with st.expander("Event registration form", expanded=True):
            with st.form("events_registration_form", clear_on_submit=True):
                selected_event_label = st.selectbox(
                    "Event *",
                    options=[""] + event_labels,
                    key="events_registration_event",
                    help="Select which event this person is registering for.",
                )
                full_name = st.text_input("Full name *", key="events_registration_full_name")
                email = st.text_input("Email *", key="events_registration_email")
                phone = st.text_input("Phone (optional)", key="events_registration_phone")
                group = st.selectbox(
                    "Group",
                    ["Supporter", "Member"],
                    key="events_registration_group",
                )
                registration_status = st.selectbox(
                    "Registration status",
                    EVENT_REGISTRATION_STATUSES,
                    key="events_registration_status",
                )
                registration_notes = st.text_area(
                    "Registration notes (optional)",
                    key="events_registration_notes",
                    height=80,
                )
                register_clicked = st.form_submit_button("Register person")

            if register_clicked:
                event_id = event_lookup.get(selected_event_label)
                if not event_id:
                    st.error("Select an event.")
                else:
                    first_name, last_name = _split_full_name(full_name)
                    person_payload = {
                        "email": email,
                        "firstName": first_name,
                        "lastName": last_name,
                        "phone": phone,
                        "group": group,
                    }
                    if not str(email or "").strip():
                        st.error("Email is required.")
                    elif not str(full_name or "").strip():
                        st.error("Full name is required.")
                    elif register_person_to_event(
                        event_id,
                        person_payload,
                        status=registration_status,
                        notes=registration_notes,
                    ):
                        st.success("Person registered to event.")
                    else:
                        st.error("Could not register person.")

        with st.expander("Registrations by event", expanded=False):
            selected_event_label = st.selectbox(
                "View registrations for event",
                options=[""] + event_labels,
                key="events_registration_view_event",
            )
            selected_event_id = event_lookup.get(selected_event_label)
            if selected_event_id:
                reg_df = list_event_registrations(selected_event_id, limit=2000)
                if reg_df.empty:
                    st.info("No registrations for this event yet.")
                else:
                    render_table_with_export(
                        reg_df,
                        key_prefix="events_registrations_table",
                        filename="event_registrations.csv",
                        column_config={
                            "registrationStatus": st.column_config.SelectboxColumn(
                                "Registration status",
                                options=EVENT_REGISTRATION_STATUSES,
                            )
                        },
                    )

    st.markdown("### Event list")
    if events_df.empty:
        st.info("No events found. Create one above.")
    else:
        event_df = events_df.rename(
            columns={
                "name": "Name",
                "startDate": "Start",
                "endDate": "End",
                "location": "Location",
                "status": "Status",
                "capacity": "Capacity",
                "registrations": "Registrations",
            }
        )
        event_df["Start"] = pd.to_datetime(event_df["Start"], errors="coerce")
        event_df["End"] = pd.to_datetime(event_df["End"], errors="coerce")
        render_table_with_export(
            event_df,
            key_prefix="events_table",
            filename="events.csv",
            column_config={
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=["Planned", "Scheduled", "Completed", "Cancelled"],
                ),
                "Start": st.column_config.DateColumn("Start", format="YYYY-MM-DD"),
                "End": st.column_config.DateColumn("End", format="YYYY-MM-DD"),
            },
        )
