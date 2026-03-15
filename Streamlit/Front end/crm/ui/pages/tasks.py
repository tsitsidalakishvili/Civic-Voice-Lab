import pandas as pd
import streamlit as st
import altair as alt
from datetime import date

from crm.data.people import search_people
from crm.data.segments import list_segments, run_saved_segment
from crm.data.tasks import (
    TASK_STATUSES,
    bulk_create_tasks,
    create_task,
    list_tasks,
    update_task_status,
)
from crm.ui.components.table_utils import render_table_with_export


def render_tasks_tab():
    st.subheader("Tasks / Follow-ups")

    filter_cols = st.columns([1, 1, 1, 1])
    with filter_cols[0]:
        status_filter = st.selectbox(
            "Status",
            ["(any)"] + TASK_STATUSES,
            index=0,
            key="tasks_status_filter",
            help="Filter the task queue by status.",
        )
    with filter_cols[1]:
        group_filter = st.selectbox(
            "Group",
            ["(any)", "Supporter", "Member"],
            index=0,
            key="tasks_group_filter",
            help="Filter tasks by the person’s group (Supporter/Member).",
        )
    with filter_cols[2]:
        limit = st.number_input(
            "Limit",
            min_value=10,
            max_value=1000,
            value=300,
            step=10,
            key="tasks_limit",
            help="Max number of tasks to load.",
        )
    with filter_cols[3]:
        refresh = st.button(
            "Refresh",
            key="tasks_refresh",
            help="Reload the task queue with the selected filters.",
        )

    status = None if status_filter == "(any)" else status_filter
    group = None if group_filter == "(any)" else group_filter
    if refresh:
        st.rerun()
    df = list_tasks(status=status, group=group, limit=limit)

    st.markdown("#### Task statistics")
    if not df.empty and "status" in df.columns:
        status_counts = (
            df["status"]
            .fillna("Open")
            .value_counts()
            .rename_axis("status")
            .reset_index(name="count")
        )
        total_tasks = int(status_counts["count"].sum())
        completed_tasks = int(
            status_counts.loc[status_counts["status"] == "Done", "count"].sum()
        )
        completion_rate = (completed_tasks / total_tasks * 100.0) if total_tasks else 0.0
        metrics = st.columns(3)
        metrics[0].metric("Total tasks", f"{total_tasks:,}")
        metrics[1].metric("Completed", f"{completed_tasks:,}")
        metrics[2].metric("Completion rate", f"{completion_rate:.1f}%")

        status_chart = (
            alt.Chart(status_counts)
            .mark_bar()
            .encode(
                x=alt.X("status:N", title="Task status"),
                y=alt.Y("count:Q", title="Count"),
                tooltip=["status:N", "count:Q"],
                color=alt.Color("status:N", legend=None),
            )
        )
        st.altair_chart(status_chart, use_container_width=True)
    else:
        st.caption("No task analytics yet. Create tasks to see status charts.")

    st.markdown("---")

    st.markdown("#### Create task")
    with st.form("tasks_person_search_form"):
        person_query = st.text_input(
            "Find person or segment (Name/Email)",
            key="tasks_person_query",
            help="Search people by name/email. Segment options are also available in the dropdown below.",
        )
        search_clicked = st.form_submit_button("Search")
    if search_clicked:
        query_clean = (person_query or "").strip()
        if len(query_clean) < 2:
            st.warning("Enter at least 2 characters to search.")
            st.session_state["tasks_person_query_committed"] = ""
        else:
            st.session_state["tasks_person_query_committed"] = query_clean
    committed_query = st.session_state.get("tasks_person_query_committed", "")

    matches = pd.DataFrame()
    if committed_query:
        with st.spinner("Searching people..."):
            matches = search_people(committed_query, limit=120)

    segments_df = list_segments()
    if committed_query and not segments_df.empty and "name" in segments_df.columns:
        segments_df = segments_df[
            segments_df["name"].fillna("").str.lower().str.contains(committed_query.lower())
        ]

    target_map = {"": None}
    if not segments_df.empty:
        for row in segments_df.itertuples(index=False):
            segment_id = str(getattr(row, "segmentId", "") or "").strip()
            segment_name = str(getattr(row, "name", "") or "Unnamed segment").strip()
            if not segment_id:
                continue
            label = f"Segment: {segment_name}"
            target_map[label] = {
                "type": "segment",
                "segment_id": segment_id,
                "segment_name": segment_name,
            }

    if not matches.empty and "email" in matches.columns:
        for row in matches.itertuples(index=False):
            email = str(getattr(row, "email", "") or "").strip()
            full_name = str(getattr(row, "fullName", "") or "").strip()
            if not email:
                continue
            person_label = full_name if full_name else email
            label = f"Person: {person_label} — {email}"
            target_map[label] = {
                "type": "person",
                "email": email,
                "full_name": full_name,
            }

    person_count = len([v for v in target_map.values() if isinstance(v, dict) and v.get("type") == "person"])
    segment_count = len([v for v in target_map.values() if isinstance(v, dict) and v.get("type") == "segment"])
    if committed_query:
        st.caption(f"{person_count:,} people and {segment_count:,} segments found.")
    elif segment_count:
        st.caption(f"{segment_count:,} segments available. Search to include matching people.")

    with st.form("tasks_create_form"):
        create_cols = st.columns([2, 2, 2, 1])
        with create_cols[0]:
            target_label = st.selectbox(
                "Person / Segment",
                options=list(target_map.keys()),
                key="tasks_target",
                help="Pick one person or one saved segment.",
            )
        with create_cols[1]:
            title = st.text_input(
                "Title *", key="tasks_title", help="Short task title (required)."
            )
            set_due = st.checkbox("Set due date", value=False, key="tasks_set_due")
            due_date_value = st.date_input(
                "Due date",
                value=date.today(),
                key="tasks_due_date_picker",
                disabled=not set_due,
            )
        with create_cols[2]:
            description = st.text_area("Notes (optional)", height=80, key="tasks_description")
        with create_cols[3]:
            status_new = st.selectbox("New Status", TASK_STATUSES, index=0, key="tasks_new_status")
            add_task_clicked = st.form_submit_button(
                "Add task", help="Create a task for the selected person or all people in the selected segment."
            )
    if add_task_clicked:
        target = target_map.get(target_label)
        if not target:
            st.error("Select a person or segment.")
            return
        due_date = due_date_value.isoformat() if set_due else ""
        if target.get("type") == "person":
            ok = create_task(
                target.get("email"),
                title,
                description=description,
                due_date=due_date,
                status=status_new,
            )
            if ok:
                st.success("Task created.")
                df = list_tasks(status=status, group=group, limit=limit)
            else:
                st.error("Could not create task (check person + title).")
        else:
            segment_df = run_saved_segment(target.get("segment_id"), limit=2000)
            if segment_df.empty:
                st.error("Selected segment has no people.")
            else:
                rows = []
                for row in segment_df.itertuples(index=False):
                    email = str(getattr(row, "email", "") or "").strip()
                    if not email:
                        continue
                    rows.append(
                        {
                            "email": email,
                            "title": title,
                            "description": description,
                            "status": status_new,
                            "dueDate": due_date,
                        }
                    )
                created = bulk_create_tasks(rows, default_status=status_new)
                if created > 0:
                    st.success(
                        f"Created {created:,} tasks for segment '{target.get('segment_name', 'Segment')}'."
                    )
                    df = list_tasks(status=status, group=group, limit=limit)
                else:
                    st.error("Could not create tasks for the selected segment.")

    st.markdown("#### Task queue")
    if df.empty:
        st.info("No tasks found yet. Create a task above.")
        return

    display_df = df[
        [
            "title",
            "status",
            "dueDate",
            "firstName",
            "lastName",
            "email",
            "group",
            "updatedAt",
        ]
    ].rename(
        columns={
            "title": "Title",
            "status": "Status",
            "dueDate": "Due",
            "firstName": "First",
            "lastName": "Last",
            "email": "Email",
            "group": "Group",
            "updatedAt": "Updated",
        }
    )
    st.caption(f"{len(display_df):,} tasks shown")
    display_df["Due"] = pd.to_datetime(display_df["Due"], errors="coerce")
    display_df["Email"] = display_df["Email"].apply(
        lambda value: f"mailto:{value}" if isinstance(value, str) and value.strip() else ""
    )
    render_table_with_export(
        display_df,
        key_prefix="tasks_queue",
        filename="tasks_queue.csv",
        column_config={
            "Status": st.column_config.SelectboxColumn("Status", options=TASK_STATUSES),
            "Due": st.column_config.DateColumn("Due", format="YYYY-MM-DD"),
            "Email": st.column_config.LinkColumn("Email", display_text=r"mailto:(.*)"),
        },
    )

    st.markdown("#### Update task status")
    task_ids = df["taskId"].tolist() if "taskId" in df.columns else []
    upd_cols = st.columns([2, 1, 1])
    with upd_cols[0]:
        selected_task = st.selectbox("Task", options=[""] + task_ids, key="tasks_update_task")
    with upd_cols[1]:
        new_status = st.selectbox("Set Status", TASK_STATUSES, key="tasks_update_status")
    with upd_cols[2]:
        if st.button("Update", key="tasks_update_btn", help="Update the selected task’s status."):
            ok = update_task_status(selected_task, new_status)
            if ok:
                st.success("Updated.")
            else:
                st.error("Update failed.")
