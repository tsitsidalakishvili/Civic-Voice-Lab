import pandas as pd
import streamlit as st
from datetime import date

from crm.analytics.people import load_map_data, load_supporter_summary
from crm.data.people import load_person_profile, search_people, update_person_profile
from crm.data.tasks import create_task, list_tasks
from crm.ui.components.table_utils import render_table_with_export
from crm.utils.text import format_list_label

GENDER_OPTIONS = ["", "Male", "Female", "Other"]
TIME_AVAILABILITY_OPTIONS = [
    "",
    "Weekends",
    "Evenings",
    "Full-time",
    "Ad-hoc",
    "Unspecified",
]


def _safe_index(options, value):
    try:
        return options.index(value)
    except ValueError:
        return 0


def _clear_profile_form_state():
    for key in [
        "profiles_reveal",
        "profiles_first",
        "profiles_last",
        "profiles_phone",
        "profiles_gender",
        "profiles_age",
        "profiles_time",
        "profiles_about",
        "profiles_agrees",
        "profiles_interested",
        "profiles_fb",
    ]:
        st.session_state.pop(key, None)


def render_profiles_tab():
    st.subheader("Profiles")

    with st.form("profiles_search_form"):
        query_input = st.text_input("Search by Name or Email", key="profiles_search")
        search_clicked = st.form_submit_button("Search")
    if search_clicked:
        query_clean = (query_input or "").strip()
        if len(query_clean) < 2:
            st.warning("Enter at least 2 characters to search.")
            st.session_state["profiles_search_committed"] = ""
        else:
            st.session_state["profiles_search_committed"] = query_clean

    query = st.session_state.get("profiles_search_committed", "")
    if not query:
        st.info("Search to find a person.")
        return

    with st.spinner("Searching people..."):
        matches = search_people(query, limit=80)
    if matches.empty:
        st.info("No people found for this search.")
        return
    st.caption(f"{len(matches):,} people found.")

    label_rows = [
        f"{row.get('fullName','')} — {row.get('email','')}" for _, row in matches.iterrows()
    ]
    selection = st.selectbox("Select Person", options=[""] + label_rows, key="profiles_select")
    if not selection:
        return
    idx = label_rows.index(selection)
    email = matches.iloc[idx].get("email")
    if not email:
        st.warning("Selected row missing email.")
        return

    if st.session_state.get("profiles_active_email") != email:
        st.session_state["profiles_active_email"] = email
        _clear_profile_form_state()

    with st.spinner("Loading profile..."):
        prof = load_person_profile(email)
    if prof.empty:
        st.error("No profile found.")
        return

    row = prof.iloc[0].to_dict()
    summary_cols = st.columns(3)
    summary_cols[0].markdown(f"**Email**: `{email}`")
    summary_cols[1].markdown(f"**Tags**: {format_list_label(row.get('tags') or [])}")
    summary_cols[2].markdown(f"**Skills**: {format_list_label(row.get('skills') or [])}")

    details_tab, tasks_tab = st.tabs(["Details", "Tasks"])
    with details_tab:
        with st.form("profiles_details_form"):
            reveal = st.checkbox(
                "Reveal contact fields (PII)",
                value=False,
                key="profiles_reveal",
                help="When off, sensitive contact fields are masked to reduce accidental exposure.",
            )
            form_cols = st.columns(2)
            with form_cols[0]:
                first = st.text_input(
                    "First Name", value=row.get("firstName") or "", key="profiles_first"
                )
                last = st.text_input(
                    "Last Name", value=row.get("lastName") or "", key="profiles_last"
                )
                phone = st.text_input(
                    "Phone",
                    value=(row.get("phone") or "") if reveal else "••••••",
                    key="profiles_phone",
                    disabled=not reveal,
                )
                gender = st.selectbox(
                    "Gender",
                    GENDER_OPTIONS,
                    index=_safe_index(GENDER_OPTIONS, row.get("gender") or ""),
                    key="profiles_gender",
                )
                age_val = row.get("age")
                age = st.number_input(
                    "Age",
                    min_value=0,
                    max_value=120,
                    value=int(age_val)
                    if isinstance(age_val, (int, float)) and not pd.isna(age_val)
                    else 0,
                    step=1,
                    key="profiles_age",
                )
            with form_cols[1]:
                time_availability = st.selectbox(
                    "Time Availability",
                    TIME_AVAILABILITY_OPTIONS,
                    index=_safe_index(
                        TIME_AVAILABILITY_OPTIONS,
                        row.get("timeAvailability") or "Unspecified",
                    ),
                    key="profiles_time",
                )
                about = st.text_area(
                    "Motivation / Notes",
                    value=row.get("about") or "",
                    height=120,
                    key="profiles_about",
                )
                agrees = st.checkbox(
                    "Agrees with Manifesto",
                    value=bool(row.get("agreesWithManifesto")),
                    key="profiles_agrees",
                )
                interested = st.checkbox(
                    "Interested in Party Membership",
                    value=bool(row.get("interestedInMembership")),
                    key="profiles_interested",
                )
                fb = st.checkbox(
                    "Facebook Group Member",
                    value=bool(row.get("facebookGroupMember")),
                    key="profiles_fb",
                )

            payload = {
                "firstName": first,
                "lastName": last,
                "phone": phone if reveal else row.get("phone"),
                "gender": gender,
                "age": age if age else None,
                "timeAvailability": time_availability
                if time_availability and time_availability != "Unspecified"
                else "Unspecified",
                "about": about,
                "agreesWithManifesto": agrees,
                "interestedInMembership": interested,
                "facebookGroupMember": fb,
            }
            original_payload = {
                "firstName": row.get("firstName") or "",
                "lastName": row.get("lastName") or "",
                "phone": row.get("phone"),
                "gender": row.get("gender") or "",
                "age": int(row.get("age"))
                if isinstance(row.get("age"), (int, float)) and not pd.isna(row.get("age"))
                else None,
                "timeAvailability": row.get("timeAvailability") or "Unspecified",
                "about": row.get("about") or "",
                "agreesWithManifesto": bool(row.get("agreesWithManifesto")),
                "interestedInMembership": bool(row.get("interestedInMembership")),
                "facebookGroupMember": bool(row.get("facebookGroupMember")),
            }
            has_unsaved_changes = payload != original_payload
            if has_unsaved_changes:
                st.warning("Unsaved changes: review fields and click Save profile updates.")
            else:
                st.caption("No field changes detected.")

            save_clicked = st.form_submit_button(
                "Save profile updates",
                help="Write profile field updates to Neo4j.",
            )

        if save_clicked:
            ok = update_person_profile(email, payload)
            if ok:
                load_supporter_summary.clear()
                load_map_data.clear()
                st.success("Saved.")
            else:
                st.error("Save failed.")

    with tasks_tab:
        st.markdown("#### Tasks for this person")
        with st.form("profiles_task_form"):
            tcols = st.columns([2, 2, 1, 1])
            with tcols[0]:
                t_title = st.text_input("Task Title *", key="profiles_task_title")
            with tcols[1]:
                set_due = st.checkbox(
                    "Set due date", value=False, key="profiles_task_set_due"
                )
            with tcols[2]:
                t_due_date = st.date_input(
                    "Due date",
                    value=date.today(),
                    key="profiles_task_due_date",
                    disabled=not set_due,
                )
            with tcols[3]:
                add_task_clicked = st.form_submit_button(
                    "Add task", help="Create a follow-up task for this person."
                )
        if add_task_clicked:
            due_date = t_due_date.isoformat() if set_due else ""
            ok = create_task(email, t_title, due_date=due_date, status="Open")
            if ok:
                st.success("Task added.")
            else:
                st.error("Could not add task.")

        tdf = list_tasks(person_email=email, limit=200)
        if tdf.empty:
            st.caption("No tasks yet. Create a task above.")
        else:
            task_df = tdf[["title", "status", "dueDate", "updatedAt"]].rename(
                columns={
                    "title": "Title",
                    "status": "Status",
                    "dueDate": "Due",
                    "updatedAt": "Updated",
                }
            )
            task_df["Due"] = pd.to_datetime(task_df["Due"], errors="coerce")
            render_table_with_export(
                task_df,
                key_prefix="profiles_tasks_table",
                filename=f"profile_tasks_{email}.csv",
                column_config={
                    "Status": st.column_config.SelectboxColumn(
                        "Status", options=["Open", "In Progress", "Done", "Cancelled"]
                    ),
                    "Due": st.column_config.DateColumn("Due", format="YYYY-MM-DD"),
                },
            )
