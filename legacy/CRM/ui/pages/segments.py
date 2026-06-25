import pandas as pd
import streamlit as st

from crm.data.people import get_distinct_values
from crm.data.segments import (
    delete_segment,
    list_segments,
    run_saved_segment,
    upsert_segment,
)
from crm.ui.components.table_utils import render_table_with_export


def render_segments_tab():
    st.subheader("Segments")

    st.markdown("#### Create / update segment")
    form_cols = st.columns(2)
    with form_cols[0]:
        seg_name = st.text_input(
            "Segment name",
            key="segments_name",
            help="A short name for this reusable filter (required).",
        )
        seg_desc = st.text_input(
            "Description (optional)",
            key="segments_desc",
            help="Optional note about what this segment is for.",
        )
        group = st.selectbox(
            "Group",
            ["", "Supporter", "Member"],
            key="segments_group",
            help="Optional group restriction.",
        )
        time_availability = st.multiselect(
            "Time availability",
            [
                "Weekends",
                "Evenings",
                "Full-time",
                "Ad-hoc",
                "Unspecified",
            ],
            default=[],
            key="segments_time",
            help="Match people by time availability.",
        )
        min_effort = st.text_input(
            "Min effort hours",
            key="segments_min_effort",
            help="Filter for people with at least this many effort hours.",
        )
    with form_cols[1]:
        tags = st.multiselect(
            "Tags",
            get_distinct_values("Tag"),
            default=[],
            key="segments_tags",
            help="Match people who have any of these tags.",
        )
        skills = st.multiselect(
            "Skills",
            get_distinct_values("Skill"),
            default=[],
            key="segments_skills",
            help="Match people who have any of these skills.",
        )
        name_contains = st.text_input(
            "Name contains",
            key="segments_name_contains",
            help="Case-insensitive substring match on the person’s full name.",
        )
        address_contains = st.text_input(
            "Address contains",
            key="segments_address_contains",
            help="Case-insensitive substring match on address text.",
        )

    filter_spec = {
        "group": group or None,
        "timeAvailability": time_availability or None,
        "tags": tags or None,
        "skills": skills or None,
        "nameContains": name_contains or None,
        "addressContains": address_contains or None,
        "minEffortHours": min_effort or None,
    }

    if st.button(
        "Save segment",
        key="segments_save_btn",
        help="Save this filter definition as a reusable segment.",
    ):
        ok = upsert_segment(seg_name, seg_desc, filter_spec)
        if ok:
            st.session_state["segments_select"] = (seg_name or "").strip()
            st.session_state["segments_saved_notice"] = "Segment saved."
        else:
            st.error("Could not save segment (name required).")

    st.markdown("#### Saved segments")
    if st.session_state.get("segments_saved_notice"):
        st.success(st.session_state.pop("segments_saved_notice"))
    sdf = list_segments()
    if sdf.empty:
        st.info("No segments yet.")
        return

    st.caption("Existing segments")
    render_table_with_export(
        sdf.rename(
            columns={
                "name": "Name",
                "description": "Description",
                "updatedAt": "Updated",
            }
        ),
        key_prefix="segments_list",
        filename="segments.csv",
    )

    names = sdf["name"].dropna().tolist() if "name" in sdf.columns else []
    sel = st.selectbox(
        "Select segment",
        options=[""] + names,
        key="segments_select",
        help="Pick a saved segment to run it and view matching people.",
    )
    if not sel:
        st.caption("Select a segment to run it.")
        return

    seg_rows = sdf[sdf["name"] == sel] if "name" in sdf.columns else pd.DataFrame()
    seg_id = (
        seg_rows["segmentId"].iloc[0]
        if not seg_rows.empty and "segmentId" in seg_rows.columns
        else None
    )
    if not seg_id:
        st.error("Could not resolve segment id.")
        return

    run_cols = st.columns([1, 1, 2])
    with run_cols[0]:
        run_limit = st.number_input(
            "Result limit",
            min_value=10,
            max_value=2000,
            value=500,
            step=50,
            key="segments_limit",
            help="Max number of people to return for this segment.",
        )
    with run_cols[1]:
        if st.button(
            "Run segment",
            key="segments_run_btn",
            help="Execute this saved segment and show matching people.",
        ):
            st.session_state["segments_last_run"] = str(seg_id)
    with run_cols[2]:
        if st.button(
            "Delete segment",
            key="segments_delete_btn",
            help="Delete this segment definition from Neo4j.",
        ):
            ok = delete_segment(seg_id)
            if ok:
                st.success("Deleted.")
                st.session_state["segments_last_run"] = None
                st.session_state["segments_select"] = ""
                st.rerun()
            else:
                st.error("Delete failed.")

    if st.session_state.get("segments_last_run") == str(seg_id):
        with st.spinner("Running segment..."):
            rdf = run_saved_segment(seg_id, limit=run_limit)
        if rdf.empty:
            st.info("No matches for this segment.")
        else:
            ordered = [
                "fullName",
                "email",
                "group",
                "timeAvailability",
                "address",
                "effortHours",
                "tags",
                "skills",
            ]
            cols = [col for col in ordered if col in rdf.columns]
            render_table_with_export(
                rdf[cols] if cols else rdf,
                key_prefix=f"segments_run_{seg_id}",
                filename=f"segment_{seg_id}_results.csv",
            )
