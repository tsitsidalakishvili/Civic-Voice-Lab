import pandas as pd
import streamlit as st

from crm.analytics.people import load_map_data, load_supporter_summary
from crm.data.people import bulk_upsert_people
from crm.utils.text import build_import_rows


def render_import_export_section(section_id, default_type_value, export_group):
    st.markdown("---")
    st.markdown("**Import / Export (CSV)**")
    upload = st.file_uploader("Upload CSV", type=["csv"], key=f"{section_id}_upload")
    if upload is not None:
        try:
            df_upload = pd.read_csv(upload)
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")
            df_upload = pd.DataFrame()

        if not df_upload.empty:
            st.caption("Preview")
            st.dataframe(df_upload.head(10), use_container_width=True)

            if st.button(
                "Import CSV",
                key=f"{section_id}_import_btn",
                help="Bulk upsert people from CSV. Requires an email column.",
            ):
                rows = build_import_rows(df_upload, default_type_value)
                if not rows:
                    st.error("No valid rows found. Ensure the CSV has an email column.")
                elif bulk_upsert_people(rows):
                    load_supporter_summary.clear()
                    load_map_data.clear()
                    st.success(f"Imported {len(rows)} rows.")

    st.markdown("**Export current data (CSV)**")
    df_export = load_supporter_summary()
    if df_export.empty:
        st.info("No data available to export.")
    else:
        df_export = df_export[df_export["group"] == export_group]
        if df_export.empty:
            st.info(f"No {export_group.lower()} data available to export.")
        else:
            export_df = df_export[
                [
                    "fullName",
                    "email",
                    "group",
                    "effortScore",
                    "effortHours",
                    "eventAttendCount",
                    "referralCount",
                    "joinCount",
                    "skillCount",
                    "educationLevel",
                    "ratingStars",
                    "gender",
                    "age",
                ]
            ].rename(
                columns={
                    "fullName": "Full Name",
                    "effortScore": "Effort Score",
                    "effortHours": "Effort Hours",
                    "eventAttendCount": "Event Attend Count",
                    "referralCount": "Referral Count",
                    "joinCount": "Join Count",
                    "skillCount": "Skill Count",
                    "educationLevel": "Education",
                    "ratingStars": "Rating",
                }
            )
            st.dataframe(export_df, use_container_width=True)
