import streamlit as st

from crm.db.neo4j import run_query, run_write
from crm.utils.text import clean_text


def upsert_whatsapp_group(name, invite_link, notes=""):
    name = clean_text(name)
    invite_link = clean_text(invite_link)
    notes = clean_text(notes) or ""
    if not name or not invite_link:
        return False
    result = run_write(
        """
        MERGE (g:WhatsAppGroup {name: $name})
        ON CREATE SET g.groupId = randomUUID(), g.createdAt = datetime()
        SET g.inviteLink = $inviteLink,
            g.notes = $notes,
            g.updatedAt = datetime()
        """,
        {"name": name, "inviteLink": invite_link, "notes": notes},
    )
    if result:
        list_whatsapp_groups.clear()
    return result


@st.cache_data(ttl=30, show_spinner=False)
def list_whatsapp_groups():
    return run_query(
        """
        MATCH (g:WhatsAppGroup)
        RETURN
          g.groupId AS groupId,
          g.name AS name,
          coalesce(g.inviteLink, '') AS inviteLink,
          coalesce(g.notes, '') AS notes,
          toString(g.updatedAt) AS updatedAt
        ORDER BY g.updatedAt DESC
        """,
        silent=True,
    )


def delete_whatsapp_group(group_id):
    group_id = clean_text(group_id)
    if not group_id:
        return False
    result = run_write(
        """
        MATCH (g:WhatsAppGroup {groupId: $groupId})
        DETACH DELETE g
        """,
        {"groupId": group_id},
    )
    if result:
        list_whatsapp_groups.clear()
    return result
