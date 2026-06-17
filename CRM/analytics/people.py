import pandas as pd
import streamlit as st

from crm.db.neo4j import run_query
from crm.utils.text import format_list_label


def classify_group(types):
    types = types or []
    for t in types:
        if t and "member" in str(t).lower():
            return "Member"
    return "Supporter"


def _education_score(level):
    if not level:
        return 0
    text = str(level).lower()
    if "phd" in text:
        return 4
    if "master" in text:
        return 3
    if "bachelor" in text:
        return 2
    if "high" in text:
        return 1
    return 0


def pick_education(levels):
    levels = levels or []
    cleaned = [str(x).strip() for x in levels if str(x).strip()]
    if not cleaned:
        return ("Unspecified", 0)
    scored = [(level, _education_score(level)) for level in cleaned]
    scored = sorted(scored, key=lambda item: item[1], reverse=True)
    return scored[0]


def calc_rating(effort_score):
    if effort_score is None or pd.isna(effort_score):
        return None
    if effort_score >= 120:
        return 5
    if effort_score >= 80:
        return 4
    if effort_score >= 40:
        return 3
    if effort_score >= 15:
        return 2
    if effort_score > 0:
        return 1
    return None


def rating_stars(value):
    if value is None or pd.isna(value):
        return "Not rated"
    filled = max(0, min(5, int(value)))
    return "⭐" * filled + "☆" * (5 - filled)


def rating_color(value):
    if value is None or pd.isna(value):
        return [120, 120, 120, 140]
    if value >= 4:
        return [46, 204, 113, 190]
    if value >= 3:
        return [241, 196, 15, 190]
    return [231, 76, 60, 190]


def age_group(value):
    if value is None or pd.isna(value):
        return "Unspecified"
    try:
        age = int(value)
    except (TypeError, ValueError):
        return "Unspecified"
    if age < 18:
        return "Under 18"
    if age < 25:
        return "18-24"
    if age < 35:
        return "25-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    if age < 65:
        return "55-64"
    return "65+"


def enrich_people_core(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "timeAvailability" not in df.columns:
        df["timeAvailability"] = "Unspecified"
    else:
        df["timeAvailability"] = df["timeAvailability"].fillna("Unspecified")
    df["types"] = df["types"].apply(lambda v: v or [])
    df["group"] = df["types"].apply(classify_group)
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["ageGroup"] = df["age"].apply(age_group)
    df["activityCount"] = pd.to_numeric(df["activityCount"], errors="coerce").fillna(0).astype(int)
    df["eventJoinCount"] = pd.to_numeric(df["eventJoinCount"], errors="coerce").fillna(0).astype(int)
    df["eventAttendRelCount"] = pd.to_numeric(
        df["eventAttendRelCount"], errors="coerce"
    ).fillna(0).astype(int)
    df["skills"] = df["skills"].apply(lambda v: v or [])
    df["skillCount"] = df["skills"].apply(lambda v: len([x for x in v if x]))
    df["skillsLabel"] = df["skills"].apply(format_list_label)
    df["eventAttendProp"] = pd.to_numeric(df["eventAttendProp"], errors="coerce").fillna(0).astype(int)
    df["referredCount"] = pd.to_numeric(df["referredCount"], errors="coerce").fillna(0).astype(int)
    df["recruitedCount"] = pd.to_numeric(df["recruitedCount"], errors="coerce").fillna(0).astype(int)
    df["referralProp"] = pd.to_numeric(df["referralProp"], errors="coerce").fillna(0).astype(int)
    df["eventAttendCount"] = df["eventAttendRelCount"] + df["eventAttendProp"]
    df["referralCount"] = df["referredCount"] + df["recruitedCount"] + df["referralProp"]
    df["joinCount"] = df["activityCount"] + df["eventJoinCount"]
    df["effortHours"] = pd.to_numeric(df["effortHours"], errors="coerce").fillna(0.0)
    df["donationTotal"] = pd.to_numeric(df["donationTotal"], errors="coerce").fillna(0.0)
    education_values = df["educationLevels"].apply(pick_education)
    df["educationLevel"] = education_values.apply(lambda value: value[0])
    df["educationScore"] = education_values.apply(lambda value: value[1])
    df["effortScore"] = df["effortHours"] + df["eventAttendCount"] + df["referralCount"]
    df["hasParticipation"] = (
        df["activityCount"] + df["eventJoinCount"] + df["eventAttendCount"]
    ) > 0
    df["rating"] = df["effortScore"].apply(calc_rating)
    df.loc[~df["hasParticipation"], "rating"] = pd.NA
    df["ratingStars"] = df["rating"].apply(rating_stars)
    full_name = (df["firstName"].fillna("") + " " + df["lastName"].fillna("")).str.strip()
    df["fullName"] = full_name.mask(full_name == "", df["email"])
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_supporter_summary():
    df = run_query(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:IS_SUPPORTER]->(s:Supporter)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        OPTIONAL MATCH (p)-[:HAS_ACTIVITY]->(a:Activity)
        OPTIONAL MATCH (p)-[r:REGISTERED_FOR]->(:Event)
        OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
        OPTIONAL MATCH (p)-[:HAS_EDUCATION]->(ed:EducationLevel)
        OPTIONAL MATCH (p)<-[:REFERRED_BY]-(refP:Person)
        OPTIONAL MATCH (s)-[:RECRUITED]->(sr:Supporter)
        WITH p, s,
             collect(DISTINCT st.name) AS types,
             collect(DISTINCT ed.name) AS educationLevels,
             count(DISTINCT a) AS activityCount,
             count(DISTINCT r) AS eventJoinCount,
             count(DISTINCT CASE WHEN r.status = 'Attended' THEN r ELSE NULL END) AS eventAttendRelCount,
             collect(DISTINCT sk.name) AS skills,
             count(DISTINCT refP) AS referredCount,
             count(DISTINCT sr) AS recruitedCount
        RETURN
          p.email AS email,
          p.firstName AS firstName,
          p.lastName AS lastName,
          coalesce(p.gender, 'Unspecified') AS gender,
          coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
          p.age AS age,
          types,
          activityCount,
          eventJoinCount,
          eventAttendRelCount,
          skills,
          educationLevels,
          coalesce(p.eventsAttendedCount, 0) AS eventAttendProp,
          coalesce(p.referralCount, 0) AS referralProp,
          referredCount,
          recruitedCount,
          coalesce(p.effortHours, p.volunteerHours, s.volunteer_hours, s.volunteerHours, 0) AS effortHours,
          coalesce(p.donationTotal, 0) AS donationTotal
        """,
        silent=True,
    )
    if df.empty:
        return df
    return enrich_people_core(df)


@st.cache_data(ttl=60)
def load_map_data():
    df = run_query(
        """
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:LIVES_AT]->(a:Address)
        WITH p,
             coalesce(p.lat, a.latitude) AS lat,
             coalesce(p.lon, a.longitude) AS lon,
             coalesce(p.address, a.fullAddress) AS address
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        OPTIONAL MATCH (p)-[:IS_SUPPORTER]->(s:Supporter)
        OPTIONAL MATCH (p)-[:CLASSIFIED_AS]->(st:SupporterType)
        OPTIONAL MATCH (p)-[:HAS_ACTIVITY]->(a:Activity)
        OPTIONAL MATCH (p)-[r:REGISTERED_FOR]->(:Event)
        OPTIONAL MATCH (p)-[:CAN_CONTRIBUTE_WITH]->(sk:Skill)
        OPTIONAL MATCH (p)-[:HAS_EDUCATION]->(ed:EducationLevel)
        OPTIONAL MATCH (p)-[:INTERESTED_IN]->(ia:InvolvementArea)
        OPTIONAL MATCH (p)<-[:REFERRED_BY]-(refP:Person)
        OPTIONAL MATCH (s)-[:RECRUITED]->(sr:Supporter)
        WITH p, s, lat, lon, address,
             collect(DISTINCT st.name) AS types,
             collect(DISTINCT ed.name) AS educationLevels,
             collect(DISTINCT ia.name) AS involvementAreas,
             count(DISTINCT a) AS activityCount,
             count(DISTINCT r) AS eventJoinCount,
             count(DISTINCT CASE WHEN r.status = 'Attended' THEN r ELSE NULL END) AS eventAttendRelCount,
             collect(DISTINCT sk.name) AS skills,
             count(DISTINCT refP) AS referredCount,
             count(DISTINCT sr) AS recruitedCount
        RETURN
          lat,
          lon,
          address AS address,
          p.email AS email,
          p.firstName AS firstName,
          p.lastName AS lastName,
          p.age AS age,
          coalesce(p.gender, 'Unspecified') AS gender,
          coalesce(p.timeAvailability, 'Unspecified') AS timeAvailability,
          coalesce(p.about, '') AS about,
          types,
          involvementAreas,
          activityCount,
          eventJoinCount,
          eventAttendRelCount,
          skills,
          educationLevels,
          coalesce(p.eventsAttendedCount, 0) AS eventAttendProp,
          coalesce(p.referralCount, 0) AS referralProp,
          referredCount,
          recruitedCount,
          coalesce(p.effortHours, p.volunteerHours, s.volunteer_hours, s.volunteerHours, 0) AS effortHours,
          coalesce(p.donationTotal, 0) AS donationTotal
        """,
        silent=True,
    )
    if df.empty:
        return df
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df["timeAvailability"] = df["timeAvailability"].fillna("Unspecified")
    df["about"] = df["about"].fillna("")
    df["address"] = df["address"].fillna("")
    df["addressLabel"] = df["address"].apply(
        lambda value: value if str(value).strip() else "Unspecified"
    )
    df["involvementAreas"] = df["involvementAreas"].apply(lambda v: v or [])
    df["involvementLabel"] = df["involvementAreas"].apply(format_list_label)
    df = enrich_people_core(df)
    df["involvementTitle"] = df["group"].apply(
        lambda value: "Desired involvement"
        if value == "Supporter"
        else "Current involvement"
    )
    df["pointSize"] = (6 + df["effortScore"].clip(lower=0) * 0.2).clip(4, 60)
    df["color"] = df["group"].map(
        {"Supporter": [17, 141, 193, 180], "Member": [11, 94, 133, 180]}
    )
    df["color"] = df["color"].apply(
        lambda value: value if isinstance(value, list) else [120, 120, 120, 180]
    )
    df["ratingColor"] = df["rating"].apply(rating_color)
    return df


def answer_chat(question, df_summary):
    text = question.lower().strip()
    if df_summary.empty:
        return "No supporter data available yet.", None

    if "gender" in text:
        counts = (
            df_summary["gender"]
            .fillna("Unspecified")
            .value_counts()
            .rename_axis("gender")
            .reset_index(name="count")
        )
        return "Here is the gender breakdown.", counts

    if "age" in text:
        age_series = df_summary["age"].dropna()
        if age_series.empty:
            return "No age data available.", None
        stats = (
            age_series.describe()
            .loc[["count", "mean", "min", "max"]]
            .round(2)
            .to_frame("value")
            .reset_index()
            .rename(columns={"index": "metric"})
        )
        return "Age summary (count, mean, min, max).", stats

    if "member" in text or "supporter" in text:
        counts = (
            df_summary["group"]
            .value_counts()
            .rename_axis("group")
            .reset_index(name="count")
        )
        return "Supporter vs member counts.", counts

    if "effort" in text or "hours" in text:
        top = (
            df_summary.sort_values("effortScore", ascending=False)
            .head(10)[
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
        return "Top supporters by effort score.", top

    return (
        "Try asking about gender, age, top joiners, or member counts.",
        None,
    )


def sort_people(df, sort_by):
    if df.empty:
        return df
    if sort_by == "Effort score":
        return df.sort_values("effortScore", ascending=False)
    if sort_by == "Effort hours":
        return df.sort_values("effortHours", ascending=False)
    if sort_by == "Join count":
        return df.sort_values("joinCount", ascending=False)
    if sort_by == "Rating":
        return df.sort_values("rating", ascending=False)
    return df.sort_values("fullName")
