import streamlit as st

from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text

COMPETITOR_TYPES = ("Person", "Company")


def upsert_competitor(name, competitor_type, notes=""):
    name = clean_text(name)
    competitor_type = clean_text(competitor_type)
    notes = clean_text(notes) or ""
    if not name or competitor_type not in COMPETITOR_TYPES:
        return False
    result = run_write(
        """
        MERGE (c:Competitor {nameKey: toLower($name), competitorType: $competitorType})
        ON CREATE SET c.competitorId = randomUUID(), c.createdAt = datetime()
        SET c.name = $name,
            c.notes = $notes,
            c.updatedAt = datetime()
        """,
        {"name": name, "competitorType": competitor_type, "notes": notes},
    )
    if result:
        list_competitors.clear()
    return result


@st.cache_data(ttl=30, show_spinner=False)
def list_competitors():
    return run_query(
        """
        MATCH (c:Competitor)
        RETURN
          c.competitorId AS competitorId,
          c.name AS name,
          c.competitorType AS competitorType,
          coalesce(c.notes, '') AS notes,
          toString(c.updatedAt) AS updatedAt
        ORDER BY c.updatedAt DESC
        """,
        silent=True,
    )


def delete_competitor(competitor_id):
    competitor_id = clean_text(competitor_id)
    if not competitor_id:
        return False
    result = run_write(
        """
        MATCH (c:Competitor {competitorId: $competitorId})
        DETACH DELETE c
        """,
        {"competitorId": competitor_id},
    )
    if result:
        list_competitors.clear()
    return result
