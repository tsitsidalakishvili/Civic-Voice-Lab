import streamlit as st

from crm.analytics.people import load_supporter_summary
from crm.ui.components.import_export import render_import_export_section


def render_data_page():
    st.subheader("Data")

    df = load_supporter_summary()
    if df.empty:
        st.info("No people data available yet.")
    else:
        total = len(df)
        missing_age = int(df["age"].isna().sum()) if "age" in df.columns else total
        missing_gender = (
            int(df["gender"].isna().sum()) if "gender" in df.columns else total
        )
        if "timeAvailability" in df.columns:
            missing_time = int(
                (df["timeAvailability"].fillna("Unspecified") == "Unspecified").sum()
            )
        else:
            missing_time = total

        metrics = st.columns(4)
        metrics[0].metric("Total people", f"{total:,}")
        metrics[1].metric("Missing age", f"{missing_age:,}")
        metrics[2].metric("Missing gender", f"{missing_gender:,}")
        metrics[3].metric("Missing availability", f"{missing_time:,}")

    st.markdown("### Import / Export")
    tab_supporters, tab_members = st.tabs(["Supporters", "Members"])
    with tab_supporters:
        render_import_export_section("supporters", "Supporter", "Supporter")
    with tab_members:
        render_import_export_section("members", "Member", "Member")
