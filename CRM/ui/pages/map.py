import pydeck as pdk
import streamlit as st

from crm.analytics.people import load_map_data


def render_map_page():
    st.subheader("Map")
    df_geo = load_map_data()
    if df_geo.empty:
        st.info("No people with latitude/longitude found.")
        return

    sidebar_col, map_col = st.columns([1, 4])
    with sidebar_col:
        st.markdown("**Filters**")
        time_options = sorted(
            [
                value
                for value in df_geo["timeAvailability"].dropna().unique().tolist()
                if str(value).strip() and str(value).lower() != "unspecified"
            ]
        )
        age_group_order = [
            "Under 18",
            "18-24",
            "25-34",
            "35-44",
            "45-54",
            "55-64",
            "65+",
            "Unspecified",
        ]
        age_group_options = [
            value
            for value in age_group_order
            if value in df_geo["ageGroup"].dropna().unique().tolist()
        ]
        skill_options = sorted(
            {
                str(skill).strip()
                for skills in df_geo["skills"]
                for skill in (skills or [])
                if str(skill).strip()
            }
        )
        gender_options = sorted(
            [
                value
                for value in df_geo["gender"].dropna().unique().tolist()
                if str(value).strip() and str(value).lower() != "unspecified"
            ]
        )

        with st.form("map_filters_form"):
            with st.expander("People", expanded=True):
                show_supporters = st.checkbox(
                    "Show Supporters",
                    value=True,
                    key="map_show_supporters",
                    help="Include supporters on the map and in the filtered table.",
                )
                show_members = st.checkbox(
                    "Show Members",
                    value=True,
                    key="map_show_members",
                    help="Include members on the map and in the filtered table.",
                )
                selected_gender = st.multiselect(
                    "Gender", gender_options, default=[], key="map_gender"
                )
                selected_age_groups = st.multiselect(
                    "Age Group", age_group_options, default=[], key="map_age_groups"
                )

            with st.expander("Availability & skills", expanded=False):
                selected_time = st.multiselect(
                    "Time Availability",
                    time_options,
                    default=[],
                    key="map_time",
                    help="Filter by people’s time availability field.",
                )
                selected_skills = st.multiselect(
                    "Skills", skill_options, default=[], key="map_skills"
                )

            with st.expander("Engagement", expanded=False):
                min_effort = st.number_input(
                    "Minimum Effort Hours",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="map_min_effort",
                )
                min_events = st.number_input(
                    "Minimum Events Attended",
                    min_value=0,
                    value=0,
                    step=1,
                    key="map_min_events",
                )
                min_referrals = st.number_input(
                    "Minimum Referrals",
                    min_value=0,
                    value=0,
                    step=1,
                    key="map_min_referrals",
                )

            with st.expander("Text search", expanded=False):
                address_query = st.text_input(
                    "Address / Location Contains", value="", key="map_address_query"
                )
                motivation_query = st.text_input(
                    "Motivation Contains", value="", key="map_motivation_query"
                )

            action_cols = st.columns(2)
            with action_cols[0]:
                st.form_submit_button("Apply Filters")
            with action_cols[1]:
                reset_filters = st.form_submit_button("Reset Filters")

        if reset_filters:
            reset_values = {
                "map_show_supporters": True,
                "map_show_members": True,
                "map_gender": [],
                "map_age_groups": [],
                "map_time": [],
                "map_skills": [],
                "map_min_effort": 0.0,
                "map_min_events": 0,
                "map_min_referrals": 0,
                "map_address_query": "",
                "map_motivation_query": "",
            }
            for key, value in reset_values.items():
                st.session_state[key] = value
            st.rerun()

    df_filtered = df_geo.copy()
    if not show_supporters:
        df_filtered = df_filtered[df_filtered["group"] != "Supporter"]
    if not show_members:
        df_filtered = df_filtered[df_filtered["group"] != "Member"]
    if selected_time:
        df_filtered = df_filtered[df_filtered["timeAvailability"].isin(selected_time)]
    if selected_age_groups:
        df_filtered = df_filtered[df_filtered["ageGroup"].isin(selected_age_groups)]
    if selected_skills:
        df_filtered = df_filtered[
            df_filtered["skills"].apply(
                lambda skills: any(skill in (skills or []) for skill in selected_skills)
            )
        ]
    if selected_gender:
        df_filtered = df_filtered[df_filtered["gender"].isin(selected_gender)]
    if address_query.strip():
        df_filtered = df_filtered[
            df_filtered["address"].str.contains(address_query, case=False, na=False)
        ]
    if motivation_query.strip():
        df_filtered = df_filtered[
            df_filtered["about"].str.contains(motivation_query, case=False, na=False)
        ]
    if min_effort > 0:
        df_filtered = df_filtered[df_filtered["effortHours"] >= min_effort]
    if min_events > 0:
        df_filtered = df_filtered[df_filtered["eventAttendCount"] >= min_events]
    if min_referrals > 0:
        df_filtered = df_filtered[df_filtered["referralCount"] >= min_referrals]

    with map_col:
        if df_filtered.empty:
            st.info("No map points for the selected filter.")
            return

        st.caption(f"{len(df_filtered):,} people shown")
        st.caption("Hover points for details.")
        legend_cols = st.columns(2)
        legend_cols[0].markdown(
            "<div style='display:flex;align-items:center;gap:6px;'>"
            "<span style='width:14px;height:14px;background:#118DC1;display:inline-block;border-radius:3px;'></span>"
            "<span style='font-size:12px;'>Supporter</span></div>",
            unsafe_allow_html=True,
        )
        legend_cols[1].markdown(
            "<div style='display:flex;align-items:center;gap:6px;'>"
            "<span style='width:14px;height:14px;background:#0B5E85;display:inline-block;border-radius:3px;'></span>"
            "<span style='font-size:12px;'>Member</span></div>",
            unsafe_allow_html=True,
        )

        scatter = pdk.Layer(
            "ScatterplotLayer",
            data=df_filtered,
            get_position=["lon", "lat"],
            get_fill_color="color",
            get_radius="pointSize",
            pickable=True,
        )

        view_state = pdk.ViewState(
            latitude=df_filtered["lat"].mean(),
            longitude=df_filtered["lon"].mean(),
            zoom=11,
            pitch=20,
        )

        deck = pdk.Deck(
            layers=[scatter],
            initial_view_state=view_state,
            tooltip={
                "text": "Name: {fullName}\nTime availability: {timeAvailability}\nRating: {ratingStars}\n{involvementTitle}: {involvementLabel}\nHow they can help: {skillsLabel}\nAddress: {addressLabel}"
            },
        )
        st.pydeck_chart(deck, use_container_width=True)

        st.markdown("---")
        st.markdown("### Filtered People (Table View)")
        table_df = df_filtered[
            [
                "fullName",
                "email",
                "group",
                "timeAvailability",
                "ageGroup",
                "gender",
                "addressLabel",
                "involvementLabel",
                "skillsLabel",
                "ratingStars",
                "about",
            ]
        ].rename(
            columns={
                "fullName": "Name",
                "email": "Email",
                "group": "Group",
                "timeAvailability": "Time Availability",
                "ageGroup": "Age Group",
                "gender": "Gender",
                "addressLabel": "Address",
                "involvementLabel": "Involvement",
                "skillsLabel": "How They Can Help",
                "ratingStars": "Rating",
                "about": "Motivation",
            }
        )
        st.dataframe(table_df, use_container_width=True)
