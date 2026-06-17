import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from crm.analytics.people import load_supporter_summary
from crm.data.tasks import list_tasks
from crm.db.neo4j import run_query


def render_dashboard_how_it_works():
    st.markdown("### How it works")
    diagram = """
    <div style="width:100%; background:#ffffff; border:1px solid #E2E8F0; border-radius:12px; padding:8px;">
      <svg viewBox="0 0 1260 520" width="100%" height="500" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748B"></path>
          </marker>
        </defs>

        <rect x="20" y="18" width="1220" height="484" rx="12" fill="#F8FAFC" stroke="#E2E8F0"/>
        <text x="42" y="46" font-size="18" font-weight="700" fill="#0B3A52">CRM Flow</text>

        <rect x="45" y="78" width="180" height="118" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="58" y="106" font-size="15" font-weight="700" fill="#1E3A8A">Dashboard</text>
        <text x="58" y="130" font-size="12" fill="#334155">See KPIs, task feed,</text>
        <text x="58" y="148" font-size="12" fill="#334155">and trends first.</text>

        <rect x="245" y="78" width="180" height="118" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="258" y="106" font-size="15" font-weight="700" fill="#1E3A8A">People</text>
        <text x="258" y="130" font-size="12" fill="#334155">Create/search profiles</text>
        <text x="258" y="148" font-size="12" fill="#334155">and update details.</text>

        <rect x="445" y="78" width="180" height="118" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="458" y="106" font-size="15" font-weight="700" fill="#1E3A8A">Tasks</text>
        <text x="458" y="130" font-size="12" fill="#334155">Assign follow-ups and</text>
        <text x="458" y="148" font-size="12" fill="#334155">track completion.</text>

        <rect x="645" y="78" width="180" height="118" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="658" y="106" font-size="15" font-weight="700" fill="#1E3A8A">Outreach</text>
        <text x="658" y="130" font-size="12" fill="#334155">Prepare audiences and</text>
        <text x="658" y="148" font-size="12" fill="#334155">share campaign links.</text>

        <rect x="845" y="78" width="180" height="118" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="858" y="106" font-size="15" font-weight="700" fill="#1E3A8A">Events</text>
        <text x="858" y="130" font-size="12" fill="#334155">Run registrations and</text>
        <text x="858" y="148" font-size="12" fill="#334155">attendance workflows.</text>

        <rect x="1045" y="78" width="180" height="118" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="1058" y="106" font-size="15" font-weight="700" fill="#1E3A8A">Map</text>
        <text x="1058" y="130" font-size="12" fill="#334155">Analyze territory and</text>
        <text x="1058" y="148" font-size="12" fill="#334155">spatial supporter data.</text>

        <path d="M 225 137 L 245 137" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 425 137 L 445 137" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 625 137 L 645 137" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 825 137 L 845 137" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 1025 137 L 1045 137" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>

        <rect x="45" y="240" width="1180" height="110" rx="10" fill="#EEFDF3" stroke="#86EFAC"/>
        <text x="65" y="272" font-size="16" font-weight="700" fill="#166534">Shared data layer (Neo4j)</text>
        <text x="65" y="298" font-size="13" fill="#14532D">All CRM tabs read/write the same connected data: people, tasks, events, tags, skills, and engagement history.</text>
        <text x="65" y="320" font-size="13" fill="#14532D">Changes in one tab immediately affect what other tabs show.</text>

        <rect x="45" y="372" width="1180" height="110" rx="10" fill="#FFF7ED" stroke="#FDBA74"/>
        <text x="65" y="404" font-size="16" font-weight="700" fill="#9A3412">Operational loop</text>
        <text x="65" y="430" font-size="13" fill="#7C2D12">Monitor in Dashboard → update People/Tasks → execute via Outreach/Events → verify distribution on Map → iterate.</text>
        <text x="65" y="452" font-size="13" fill="#7C2D12">This loop keeps campaign execution aligned and measurable.</text>
      </svg>
    </div>
    """
    components.html(diagram, height=510, scrolling=False)
    st.markdown(
        "- **Dashboard**: baseline health check and trend monitoring.\n"
        "- **People**: maintain supporter/member profiles and attributes.\n"
        "- **Tasks**: operational execution queue with status tracking.\n"
        "- **Outreach**: message planning and audience activation.\n"
        "- **Events**: registration and participation workflows.\n"
        "- **Map**: geographic coverage and prioritization."
    )


def _render_dashboard_actual_app():

    df_summary = load_supporter_summary()
    if df_summary.empty:
        st.info("No people data found yet.")
        return

    total_people = len(df_summary)
    total_supporters = int((df_summary["group"] == "Supporter").sum())
    total_members = int((df_summary["group"] == "Member").sum())
    avg_effort = float(df_summary["effortScore"].mean()) if total_people else 0.0

    metrics = st.columns(4)
    metrics[0].metric("Total people", f"{total_people:,}")
    metrics[1].metric("Supporters", f"{total_supporters:,}")
    metrics[2].metric("Members", f"{total_members:,}")
    metrics[3].metric("Avg effort score", f"{avg_effort:.1f}")

    with st.expander("Task feed", expanded=False):
        tasks = list_tasks(status="Open", limit=15)
        if tasks.empty:
            st.info("No open tasks yet.")
        else:
            task_df = tasks[
                ["title", "dueDate", "firstName", "lastName", "email", "group", "updatedAt"]
            ].rename(
                columns={
                    "title": "Task",
                    "dueDate": "Due",
                    "firstName": "First",
                    "lastName": "Last",
                    "email": "Email",
                    "group": "Group",
                    "updatedAt": "Updated",
                }
            )
            st.dataframe(task_df, use_container_width=True)

    st.markdown("#### Snapshot charts")
    chart_cols = st.columns(3)

    group_counts = (
        df_summary["group"]
        .value_counts()
        .rename_axis("group")
        .reset_index(name="count")
    )
    group_chart = (
        alt.Chart(group_counts)
        .mark_bar()
        .encode(x="group:N", y="count:Q", tooltip=["group:N", "count:Q"])
    )
    chart_cols[0].altair_chart(group_chart, use_container_width=True)

    gender_counts = (
        df_summary["gender"]
        .fillna("Unspecified")
        .value_counts()
        .rename_axis("gender")
        .reset_index(name="count")
    )
    gender_chart = (
        alt.Chart(gender_counts)
        .mark_bar()
        .encode(x="gender:N", y="count:Q", tooltip=["gender:N", "count:Q"])
    )
    chart_cols[1].altair_chart(gender_chart, use_container_width=True)

    rating_counts = (
        df_summary["rating"]
        .value_counts()
        .sort_index()
        .rename_axis("rating")
        .reset_index(name="count")
    )
    rating_chart = (
        alt.Chart(rating_counts)
        .mark_bar()
        .encode(x="rating:O", y="count:Q", tooltip=["rating:O", "count:Q"])
    )
    chart_cols[2].altair_chart(rating_chart, use_container_width=True)

    df_manifesto = run_query(
        """
        MATCH (p:Person)
        RETURN CASE
            WHEN p.agreesWithManifesto IS NULL THEN 'Unspecified'
            WHEN p.agreesWithManifesto THEN 'Yes'
            ELSE 'No'
        END AS agrees, count(p) AS count
        """,
        silent=True,
    )
    df_membership = run_query(
        """
        MATCH (p:Person)
        RETURN CASE
            WHEN p.interestedInMembership IS NULL THEN 'Unspecified'
            WHEN p.interestedInMembership THEN 'Yes'
            ELSE 'No'
        END AS interested, count(p) AS count
        """,
        silent=True,
    )
    df_facebook = run_query(
        """
        MATCH (p:Person)
        RETURN CASE
            WHEN p.facebookGroupMember IS NULL THEN 'Unspecified'
            WHEN p.facebookGroupMember THEN 'Yes'
            ELSE 'No'
        END AS facebook, count(p) AS count
        """,
        silent=True,
    )
    df_type_gender = run_query(
        """
        MATCH (p:Person)-[:CLASSIFIED_AS]->(st:SupporterType)
        RETURN st.name AS type, coalesce(p.gender,'Unspecified') AS gender, count(p) AS count
        """,
        silent=True,
    )
    df_time = run_query(
        """
        MATCH (p:Person)
        RETURN coalesce(p.timeAvailability,'Unspecified') AS availability, count(p) AS count
        """,
        silent=True,
    )
    df_involve = run_query(
        """
        MATCH (p:Person)-[:INTERESTED_IN]->(ia:InvolvementArea)
        RETURN ia.name AS area, count(p) AS count
        ORDER BY count DESC
        LIMIT 10
        """,
        silent=True,
    )
    df_skills = run_query(
        """
        MATCH (p:Person)-[:CAN_CONTRIBUTE_WITH]->(s:Skill)
        RETURN s.name AS skill, count(p) AS count
        ORDER BY count DESC
        LIMIT 10
        """,
        silent=True,
    )

    manifesto_yes = (
        int(df_manifesto.loc[df_manifesto["agrees"] == "Yes", "count"].sum())
        if not df_manifesto.empty
        else 0
    )
    membership_yes = (
        int(df_membership.loc[df_membership["interested"] == "Yes", "count"].sum())
        if not df_membership.empty
        else 0
    )
    facebook_yes = (
        int(df_facebook.loc[df_facebook["facebook"] == "Yes", "count"].sum())
        if not df_facebook.empty
        else 0
    )
    manifesto_pct = (manifesto_yes / total_people * 100) if total_people else 0
    membership_pct = (membership_yes / total_people * 100) if total_people else 0
    facebook_pct = (facebook_yes / total_people * 100) if total_people else 0

    with st.expander("Statistics", expanded=True):
        stat_cols = st.columns(2)
        with stat_cols[0]:
            st.markdown("**Supporter vs Member**")
            st.altair_chart(group_chart, use_container_width=True)
        with stat_cols[1]:
            st.markdown("**Gender distribution**")
            st.altair_chart(gender_chart, use_container_width=True)

        stat_cols = st.columns(2)
        with stat_cols[0]:
            st.markdown("**Rating distribution**")
            st.altair_chart(rating_chart, use_container_width=True)
        with stat_cols[1]:
            st.markdown("**Age distribution**")
            age_df = df_summary.dropna(subset=["age"])
            if age_df.empty:
                st.caption("No age data available.")
            else:
                age_chart = (
                    alt.Chart(age_df)
                    .mark_bar()
                    .encode(
                        alt.X("age:Q", bin=alt.Bin(maxbins=12)),
                        y="count()",
                        tooltip=["count()"],
                    )
                )
                st.altair_chart(age_chart, use_container_width=True)

        st.markdown("**Effort score summary**")
        effort_stats = (
            df_summary["effortScore"]
            .describe()
            .loc[["mean", "min", "max"]]
            .round(2)
            .to_frame("value")
            .reset_index()
            .rename(columns={"index": "metric"})
        )
        st.dataframe(effort_stats, use_container_width=True)

    with st.expander("Engagement analytics", expanded=False):
        indicator_metrics = st.columns(3)
        indicator_metrics[0].metric("Manifesto Agree (%)", f"{manifesto_pct:.1f}%")
        indicator_metrics[1].metric("Membership Interest (%)", f"{membership_pct:.1f}%")
        indicator_metrics[2].metric("Facebook Group Member (%)", f"{facebook_pct:.1f}%")

    with st.expander("People breakdown", expanded=False):
        if not df_type_gender.empty:
            st.markdown("**Gender by Supporter Type**")
            gender_stack = (
                alt.Chart(df_type_gender)
                .mark_bar()
                .encode(
                    x=alt.X("type:N", title="Supporter Type"),
                    y=alt.Y("count:Q"),
                    color=alt.Color("gender:N"),
                    tooltip=["type:N", "gender:N", "count:Q"],
                )
            )
            st.altair_chart(gender_stack, use_container_width=True)

        if not df_time.empty:
            st.markdown("**Time Availability**")
            time_bar = (
                alt.Chart(df_time)
                .mark_bar()
                .encode(
                    y=alt.Y("availability:N", sort="-x"),
                    x=alt.X("count:Q"),
                    tooltip=["availability:N", "count:Q"],
                )
            )
            st.altair_chart(time_bar, use_container_width=True)

        indicator_cols = st.columns(3)
        with indicator_cols[0]:
            if not df_manifesto.empty:
                st.markdown("**Agrees With Manifesto**")
                manifesto_chart = (
                    alt.Chart(df_manifesto)
                    .mark_arc(innerRadius=40)
                    .encode(
                        theta=alt.Theta("count:Q"),
                        color=alt.Color("agrees:N"),
                        tooltip=["agrees:N", "count:Q"],
                    )
                )
                st.altair_chart(manifesto_chart, use_container_width=True)
        with indicator_cols[1]:
            if not df_membership.empty:
                st.markdown("**Interested in Party Membership**")
                membership_chart = (
                    alt.Chart(df_membership)
                    .mark_arc(innerRadius=40)
                    .encode(
                        theta=alt.Theta("count:Q"),
                        color=alt.Color("interested:N"),
                        tooltip=["interested:N", "count:Q"],
                    )
                )
                st.altair_chart(membership_chart, use_container_width=True)
        with indicator_cols[2]:
            if not df_facebook.empty:
                st.markdown("**Facebook Group Member**")
                facebook_chart = (
                    alt.Chart(df_facebook)
                    .mark_arc(innerRadius=40)
                    .encode(
                        theta=alt.Theta("count:Q"),
                        color=alt.Color("facebook:N"),
                        tooltip=["facebook:N", "count:Q"],
                    )
                )
                st.altair_chart(facebook_chart, use_container_width=True)

        top_cols = st.columns(2)
        with top_cols[0]:
            if not df_involve.empty:
                st.markdown("**Top Involvement Areas**")
                involve_bar = (
                    alt.Chart(df_involve)
                    .mark_bar()
                    .encode(
                        y=alt.Y("area:N", sort="-x"),
                        x=alt.X("count:Q"),
                        tooltip=["area:N", "count:Q"],
                    )
                )
                st.altair_chart(involve_bar, use_container_width=True)
        with top_cols[1]:
            if not df_skills.empty:
                st.markdown("**Top Skills**")
                skill_bar = (
                    alt.Chart(df_skills)
                    .mark_bar()
                    .encode(
                        y=alt.Y("skill:N", sort="-x"),
                        x=alt.X("count:Q"),
                        tooltip=["skill:N", "count:Q"],
                    )
                )
                st.altair_chart(skill_bar, use_container_width=True)


def render_dashboard_trends_page():
    st.subheader("Dashboard Trends")
    st.caption("Chart-focused view of supporter and engagement distributions.")
    df_summary = load_supporter_summary()
    if df_summary.empty:
        st.info("No people data found yet.")
        return

    group_counts = (
        df_summary["group"].value_counts().rename_axis("group").reset_index(name="count")
    )
    gender_counts = (
        df_summary["gender"]
        .fillna("Unspecified")
        .value_counts()
        .rename_axis("gender")
        .reset_index(name="count")
    )
    rating_counts = (
        df_summary["rating"]
        .value_counts()
        .sort_index()
        .rename_axis("rating")
        .reset_index(name="count")
    )
    effort_bins = (
        pd.cut(
            df_summary["effortScore"],
            bins=[-0.01, 0, 10, 25, 50, 100, float("inf")],
            labels=["0", "1-10", "11-25", "26-50", "51-100", "100+"],
        )
        .value_counts()
        .sort_index()
        .rename_axis("effortBand")
        .reset_index(name="count")
    )

    chart_cols = st.columns(2)
    chart_cols[0].altair_chart(
        alt.Chart(group_counts)
        .mark_bar()
        .encode(x="group:N", y="count:Q", tooltip=["group", "count"]),
        use_container_width=True,
    )
    chart_cols[1].altair_chart(
        alt.Chart(gender_counts)
        .mark_bar()
        .encode(x="gender:N", y="count:Q", tooltip=["gender", "count"]),
        use_container_width=True,
    )

    chart_cols = st.columns(2)
    chart_cols[0].altair_chart(
        alt.Chart(rating_counts)
        .mark_bar()
        .encode(x="rating:O", y="count:Q", tooltip=["rating", "count"]),
        use_container_width=True,
    )
    chart_cols[1].altair_chart(
        alt.Chart(effort_bins)
        .mark_bar()
        .encode(x="effortBand:N", y="count:Q", tooltip=["effortBand", "count"]),
        use_container_width=True,
    )


def render_dashboard_page():
    st.subheader("Dashboard")
    _render_dashboard_actual_app()

