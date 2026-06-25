from __future__ import annotations

import time

import streamlit as st

import crm.db.neo4j as neo4j_db
from crm.clients.deliberation import delib_api_get
from crm.config import (
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_SANDBOX_DATABASE,
    NEO4J_SANDBOX_PASSWORD,
    NEO4J_SANDBOX_URI,
    NEO4J_SANDBOX_USER,
    PUBLIC_ONLY,
    SUPPORTER_ACCESS_CODE,
)
from crm.db.neo4j import init_driver
from crm.services.feedback import render_feedback_widget


_GLOBAL_STYLE = """
<style>
/* Make Streamlit tooltip icons more visible */
[data-testid="stTooltipIcon"] {
  opacity: 1 !important;
  color: #6b7280 !important;
}
[data-testid="stTooltipIcon"] svg {
  width: 18px !important;
  height: 18px !important;
}
/* Compact + colorful page rhythm */
[data-testid="stAppViewContainer"] .main .block-container {
  max-width: 100% !important;
  padding-top: 0.55rem !important;
  padding-bottom: 0.8rem !important;
  padding-left: 0.85rem !important;
  padding-right: 0.85rem !important;
}
[data-testid="stAppViewContainer"] .main .block-container h1,
[data-testid="stAppViewContainer"] .main .block-container h2,
[data-testid="stAppViewContainer"] .main .block-container h3,
[data-testid="stAppViewContainer"] .main .block-container h4 {
  margin-top: 0.14rem !important;
  margin-bottom: 0.28rem !important;
  line-height: 1.2 !important;
}
[data-testid="stAppViewContainer"] .main .block-container h1 {
  color: #0B3A52 !important;
}
[data-testid="stAppViewContainer"] .main .block-container h2,
[data-testid="stAppViewContainer"] .main .block-container h3 {
  color: #0B3A52 !important;
  padding: 0.36rem 0.62rem !important;
  border-left: 4px solid #167CA7;
  border-radius: 10px;
  background: linear-gradient(
    90deg,
    rgba(22, 124, 167, 0.18) 0%,
    rgba(22, 124, 167, 0.08) 60%,
    rgba(22, 124, 167, 0.02) 100%
  );
}
[data-testid="stAppViewContainer"] .main .block-container h4 {
  color: #0B3A52 !important;
  padding-left: 0.45rem !important;
  border-left: 3px solid #6BB5D3;
}
div[data-testid="stCaptionContainer"] {
  margin-top: -0.08rem !important;
  margin-bottom: 0.16rem !important;
}
.block-container hr {
  margin-top: 0.4rem !important;
  margin-bottom: 0.4rem !important;
}
[data-testid="stHorizontalBlock"] {
  gap: 0.65rem !important;
}
[data-testid="stVerticalBlock"] > div.element-container {
  margin-bottom: 0.32rem !important;
}
[data-testid="stMetric"] {
  border: 1px solid #D3E7F2;
  border-radius: 10px;
  padding: 0.35rem 0.45rem !important;
  background: #F8FCFF;
}
[data-testid="stForm"],
[data-testid="stExpander"] details {
  border-radius: 12px !important;
}
@media (max-width: 768px) {
  [data-testid="stAppViewContainer"] .main .block-container {
    padding-left: 0.6rem !important;
    padding-right: 0.6rem !important;
    padding-top: 0.45rem !important;
  }
  [data-testid="stHorizontalBlock"] {
    gap: 0.45rem !important;
  }
}
</style>
"""


_QUESTIONNAIRE_KIOSK_STYLE = """
<style>
html body section[data-testid="stSidebar"],
html body [data-testid="stSidebar"],
html body [data-testid="stSidebarUserContent"],
html body [data-testid="stSidebarContent"],
html body [data-testid="stSidebarHeader"],
html body [data-testid="stSidebarNav"],
html body [data-testid="stSidebarNavItems"],
html body [data-testid="stSidebarNavLink"],
html body [data-testid="stPageLink"],
html body [data-testid="stSidebarCollapsedControl"],
html body [data-testid="collapsedControl"],
html body [aria-label="Sidebar"],
html body [aria-label="Page navigation"],
html body aside {
  display: none !important;
  visibility: hidden !important;
  width: 0 !important;
  min-width: 0 !important;
  max-width: 0 !important;
}
html body header[data-testid="stHeader"],
html body [data-testid="stToolbar"],
html body [data-testid="stDecoration"],
html body [data-testid="stStatusWidget"],
html body #MainMenu,
html body footer,
html body nav,
html body button[kind="headerNoPadding"],
html body button[title="View sidebar"],
html body button[title="Close sidebar"] {
  display: none !important;
}
html body [data-testid="stAppViewContainer"] > .main {
  margin-left: 0 !important;
}
html body .block-container {
  max-width: 100% !important;
  padding-left: 0.35rem !important;
  padding-right: 0.35rem !important;
}
</style>
"""


def _query_param_raw(name: str):
    value = None
    try:
        value = st.query_params.get(name)
    except Exception:
        value = None
    if isinstance(value, list):
        return value[0] if value else None
    if value not in (None, ""):
        return value
    try:
        params = st.experimental_get_query_params()
        fallback = params.get(name)
        if isinstance(fallback, list):
            return fallback[0] if fallback else None
        return fallback
    except Exception:
        return value


def _is_questionnaire_kiosk_request() -> bool:
    questionnaire_kind = str(_query_param_raw("questionnaire") or "").strip().lower()
    if questionnaire_kind in {"deliberation", "deliberation_admin"}:
        return True
    if questionnaire_kind:
        return False

    convo_id = str(
        _query_param_raw("conversation_id") or _query_param_raw("conversation") or ""
    ).strip()
    if not convo_id:
        return False
    mobile = str(_query_param_raw("mobile") or "").strip().lower()
    view = str(_query_param_raw("view") or "").strip().lower()
    embed = str(_query_param_raw("embed") or "").strip().lower()
    return (
        mobile in {"1", "true", "yes", "on"}
        or view == "mobile"
        or embed in {"1", "true", "yes", "on"}
    )


def apply_global_styles() -> None:
    kiosk_mode = _is_questionnaire_kiosk_request()
    try:
        st.set_option("client.showSidebarNavigation", not kiosk_mode)
    except Exception:
        pass

    style = _GLOBAL_STYLE
    if kiosk_mode:
        style += _QUESTIONNAIRE_KIOSK_STYLE
    st.markdown(style, unsafe_allow_html=True)


def get_query_param(name: str):
    return _query_param_raw(name)


def ensure_db_connection(*, show_sidebar: bool = True) -> bool:
    target_uri = str(NEO4J_SANDBOX_URI or NEO4J_URI or "").strip()
    target_user = str(NEO4J_SANDBOX_USER or NEO4J_USER or "neo4j").strip()
    target_password = str(NEO4J_SANDBOX_PASSWORD or NEO4J_PASSWORD or "").strip()
    target_database = str(NEO4J_SANDBOX_DATABASE or NEO4J_DATABASE or "neo4j").strip()
    connection_mode = "Sandbox (Web)" if NEO4J_SANDBOX_URI else "Primary"

    active_uri = str(getattr(neo4j_db, "_active_uri", "") or "").strip()
    active_user = str(getattr(neo4j_db, "_active_user", "") or "").strip()
    active_db = str(getattr(neo4j_db, "_active_database", "") or "").strip()
    if (
        neo4j_db.driver is not None
        and active_uri == target_uri
        and active_user == target_user
        and active_db == target_database
    ):
        return True

    cooldown_s = 30
    last_failed_at = float(st.session_state.get("_db_connect_failed_at", 0.0) or 0.0)
    elapsed = time.time() - last_failed_at
    if last_failed_at > 0 and elapsed < cooldown_s:
        remaining = int(cooldown_s - elapsed)
        if show_sidebar:
            st.sidebar.warning(
                f"Database reconnect is cooling down ({remaining}s). "
                "Check Neo4j credentials/network and retry shortly."
            )
        return False

    if show_sidebar:
        st.sidebar.markdown("### Database")
        st.sidebar.caption(f"Connection: {connection_mode}")
    if not target_uri or not target_password:
        if show_sidebar:
            st.sidebar.warning(
                "Neo4j credentials missing. Set either "
                "NEO4J_SANDBOX_URI/NEO4J_SANDBOX_PASSWORD or "
                "NEO4J_URI/NEO4J_PASSWORD."
            )
        return False

    ok = init_driver(
        uri=target_uri,
        user=target_user,
        password=target_password,
        database=target_database,
    )
    if not ok or neo4j_db.driver is None:
        st.session_state["_db_connect_failed_at"] = time.time()
        if connection_mode == "Sandbox (Web)":
            st.error(
                "Missing or invalid Sandbox Neo4j credentials. "
                "Set NEO4J_SANDBOX_URI and NEO4J_SANDBOX_PASSWORD."
            )
        else:
            st.error(
                "Missing or invalid Primary Neo4j credentials. "
                "Set NEO4J_URI and NEO4J_PASSWORD."
            )
        return False
    st.session_state["_db_connect_failed_at"] = 0.0
    return True


def _supporter_mode() -> bool:
    supporter_mode = not PUBLIC_ONLY
    if SUPPORTER_ACCESS_CODE:
        st.sidebar.markdown("### Access")
        entered_code = st.sidebar.text_input(
            "Supporter access code",
            type="password",
            help=(
                "If set in .env, this code gates access to CRM pages. "
                "Share only with trusted team members."
            ),
        )
        supporter_mode = entered_code == SUPPORTER_ACCESS_CODE
    return supporter_mode


def ensure_supporter_access(page_name: str) -> bool:
    if not _supporter_mode():
        from crm.ui.pages.deliberation import render_deliberation

        st.info("Public view: deliberation participation only.")
        render_feedback_widget("Deliberation (Public)")
        render_deliberation(public_only=True)
        return False
    render_feedback_widget(page_name)
    return True


def _apply_questionnaire_kiosk_shell() -> None:
    st.markdown(_QUESTIONNAIRE_KIOSK_STYLE, unsafe_allow_html=True)


def handle_special_entrypoints() -> bool:
    questionnaire_kind = get_query_param("questionnaire")
    if questionnaire_kind:
        kind = str(questionnaire_kind).strip().lower()
        if kind in {"deliberation", "deliberation_admin"}:
            from crm.ui.pages.deliberation import render_deliberation

            _apply_questionnaire_kiosk_shell()
            convo_id = get_query_param("conversation_id") or get_query_param("conversation")
            if convo_id:
                # Always trust explicit deeplink conversation id to avoid stale session state.
                st.session_state["delib_conversation_id"] = str(convo_id).strip()
            render_deliberation(public_only=True)
            return True

        if kind in {"event_registration", "event"}:
            from crm.ui.pages.events import render_event_registration_page

            if not ensure_db_connection(show_sidebar=False):
                st.error("Database connection unavailable for event registration.")
                return True
            event_id = get_query_param("event_id") or get_query_param("event")
            event_key = get_query_param("event_key") or get_query_param("eventKey")
            render_event_registration_page(event_id=event_id, event_key=event_key)
            return True

        st.error("Unknown questionnaire type.")
        return True

    # Fallback for mobile links where `questionnaire` can be dropped on reruns.
    if _is_questionnaire_kiosk_request():
        from crm.ui.pages.deliberation import render_deliberation

        _apply_questionnaire_kiosk_shell()
        convo_id = get_query_param("conversation_id") or get_query_param("conversation")
        if convo_id:
            st.session_state["delib_conversation_id"] = str(convo_id).strip()
        render_deliberation(public_only=True)
        return True

    survey_id = get_query_param("survey")
    if survey_id:
        from crm.ui.components.questionnaire import render_survey_page

        render_survey_page(str(survey_id).strip())
        return True
    return False
