import altair as alt
import pandas as pd
import streamlit as st

from crm.analytics.people import load_supporter_summary


def render_volunteers_page():
    st.subheader("Volunteers")

    df = load_supporter_summary()
    if df.empty:
        st.info("No volunteer data available yet.")
        return

    volunteers = df[df["effortScore"] > 0]
    total_volunteers = len(volunteers)
    avg_effort = float(volunteers["effortScore"].mean()) if total_volunteers else 0.0
    metrics = st.columns(3)
    metrics[0].metric("Active volunteers", f"{total_volunteers:,}")
    metrics[1].metric("Avg effort score", f"{avg_effort:.1f}")
    metrics[2].metric("Total people", f"{len(df):,}")

    st.markdown("### Top volunteers")
    top = (
        volunteers.sort_values("effortScore", ascending=False)
        .head(20)[
            [
                "fullName",
                "email",
                "group",
                "effortHours",
                "eventAttendCount",
                "referralCount",
                "ratingStars",
            ]
        ]
    )
    top = top.rename(
        columns={
            "fullName": "Name",
            "email": "Email",
            "group": "Group",
            "effortHours": "Effort Hours",
            "eventAttendCount": "Events Attended",
            "referralCount": "Referrals",
            "ratingStars": "Rating",
        }
    )
    st.dataframe(top, use_container_width=True)

    st.markdown("### Skill distribution")
    skill_counts = {}
    for skills in df["skills"]:
        for skill in skills or []:
            skill = str(skill).strip()
            if skill:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
    if not skill_counts:
        st.caption("No skills recorded yet.")
    else:
        skill_df = (
            pd.DataFrame([{"skill": k, "count": v} for k, v in skill_counts.items()])
            .sort_values("count", ascending=False)
            .head(20)
        )
        chart = (
            alt.Chart(skill_df)
            .mark_bar()
            .encode(x="skill:N", y="count:Q", tooltip=["skill:N", "count:Q"])
        )
        st.altair_chart(chart, use_container_width=True)
