import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from crm.config import FEEDBACK_EMAIL_TO, get_config
from crm.data.competitors import (
    COMPETITOR_TYPES,
    delete_competitor,
    list_competitors,
    upsert_competitor,
)


def _link_button(label: str, url: str) -> None:
    if not url:
        return
    try:
        st.link_button(label, url, use_container_width=True)
    except Exception:
        st.markdown(f"[{label}]({url})")


def _build_gmail_compose_url(*, to_email: str, subject: str, body: str) -> str:
    params = {
        "view": "cm",
        "fs": "1",
        "su": subject,
        "body": body,
    }
    to_value = str(to_email or "").strip()
    if to_value:
        params["to"] = to_value
    return "https://mail.google.com/mail/?" + urlencode(params, quote_via=quote_plus)


def _append_query_params(url: str, params: dict[str, str]) -> str:
    clean_url = str(url or "").strip()
    if not clean_url:
        return ""
    parsed = urlparse(clean_url)
    merged = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        text = str(value or "").strip()
        if text:
            merged[key] = text
    new_query = urlencode(merged, quote_via=quote_plus)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def _render_architecture_card(title: str, concept: str, outcome: str, tone: str = "default") -> None:
    palettes = {
        "default": {"bg": "#F8FAFF", "border": "#9FB8E8", "title": "#1E3A8A"},
        "entry": {"bg": "#FFF7ED", "border": "#FDBA74", "title": "#9A3412"},
        "monitor": {"bg": "#ECFDF3", "border": "#86EFAC", "title": "#166534"},
    }
    palette = palettes.get(tone, palettes["default"])
    st.markdown(
        f"""
        <div style="
            border: 1px solid {palette['border']};
            background: {palette['bg']};
            border-radius: 10px;
            padding: 8px 10px;
            margin: 0;
            min-height: 132px;
        ">
            <div style="font-size: 14px; font-weight: 700; color: {palette['title']}; margin-bottom: 4px;">
                {title}
            </div>
            <div style="font-size: 12px; margin-bottom: 3px;">
                <b>Concept:</b> {concept}
            </div>
            <div style="font-size: 12px;">
                <b>Outcome:</b> {outcome}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_due_diligence_how_it_works() -> None:
    st.markdown("### Workflow architecture")
    html = """
    <div style="width:100%; background:#ffffff; border:1px solid #E2E8F0; border-radius:12px; padding:8px;">
      <svg viewBox="0 0 1280 760" width="100%" height="740" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748B"></path>
          </marker>
          <filter id="shadow" x="-10%" y="-10%" width="130%" height="130%">
            <feDropShadow dx="0" dy="1" stdDeviation="1.2" flood-color="#CBD5E1" flood-opacity="0.9"/>
          </filter>
        </defs>

        <rect x="20" y="18" width="1240" height="724" rx="12" fill="#F8FAFC" stroke="#E2E8F0"/>

        <!-- Entry row -->
        <rect x="50" y="55" width="260" height="120" rx="10" fill="#EFF6FF" stroke="#93C5FD" filter="url(#shadow)"/>
        <text x="66" y="82" font-size="16" font-weight="700" fill="#1E3A8A">CRM Context</text>
        <text x="66" y="104" font-size="13" fill="#334155">Profile / Task / Event trigger</text>
        <text x="66" y="124" font-size="13" fill="#334155">Outcome: scoped investigation</text>

        <rect x="350" y="55" width="260" height="120" rx="10" fill="#FFF7ED" stroke="#FDBA74" filter="url(#shadow)"/>
        <text x="366" y="82" font-size="16" font-weight="700" fill="#9A3412">Competitor Lead</text>
        <text x="366" y="104" font-size="13" fill="#7C2D12">External person/company trigger</text>
        <text x="366" y="124" font-size="13" fill="#7C2D12">Outcome: direct intake subject</text>

        <rect x="680" y="55" width="280" height="120" rx="10" fill="#EEF2FF" stroke="#A5B4FC" filter="url(#shadow)"/>
        <text x="696" y="82" font-size="16" font-weight="700" fill="#312E81">1) Start Point</text>
        <text x="696" y="104" font-size="13" fill="#3730A3">Normalize entry path</text>
        <text x="696" y="124" font-size="13" fill="#3730A3">Outcome: one investigation context</text>

        <!-- Analysis row -->
        <rect x="50" y="245" width="280" height="130" rx="10" fill="#F8FAFF" stroke="#9FB8E8" filter="url(#shadow)"/>
        <text x="66" y="272" font-size="16" font-weight="700" fill="#1E3A8A">2) Entity Resolution</text>
        <text x="66" y="295" font-size="13" fill="#334155">Match / create canonical IDs</text>
        <text x="66" y="315" font-size="13" fill="#334155">Outcome: deduplicated subject</text>

        <rect x="360" y="245" width="280" height="130" rx="10" fill="#F8FAFF" stroke="#9FB8E8" filter="url(#shadow)"/>
        <text x="376" y="272" font-size="16" font-weight="700" fill="#1E3A8A">3) Enrichment</text>
        <text x="376" y="295" font-size="13" fill="#334155">Wikidata / OpenSanctions / News</text>
        <text x="376" y="315" font-size="13" fill="#334155">Outcome: source-linked facts</text>

        <rect x="670" y="245" width="280" height="130" rx="10" fill="#F8FAFF" stroke="#9FB8E8" filter="url(#shadow)"/>
        <text x="686" y="272" font-size="16" font-weight="700" fill="#1E3A8A">4) Neo4j Graph</text>
        <text x="686" y="295" font-size="13" fill="#334155">Nodes + relationships + provenance</text>
        <text x="686" y="315" font-size="13" fill="#334155">Outcome: queryable network state</text>

        <rect x="980" y="245" width="250" height="130" rx="10" fill="#F8FAFF" stroke="#9FB8E8" filter="url(#shadow)"/>
        <text x="996" y="272" font-size="16" font-weight="700" fill="#1E3A8A">5) Risk View</text>
        <text x="996" y="295" font-size="13" fill="#334155">2-hop exposure checks</text>
        <text x="996" y="315" font-size="13" fill="#334155">Outcome: prioritized risk signals</text>

        <!-- Decisions row -->
        <rect x="250" y="465" width="280" height="130" rx="10" fill="#F8FAFF" stroke="#9FB8E8" filter="url(#shadow)"/>
        <text x="266" y="492" font-size="16" font-weight="700" fill="#1E3A8A">6) Report</text>
        <text x="266" y="515" font-size="13" fill="#334155">Evidence-backed findings summary</text>
        <text x="266" y="535" font-size="13" fill="#334155">Outcome: decision-ready PDF</text>

        <rect x="560" y="465" width="280" height="130" rx="10" fill="#F8FAFF" stroke="#9FB8E8" filter="url(#shadow)"/>
        <text x="576" y="492" font-size="16" font-weight="700" fill="#1E3A8A">7) CRM Actions</text>
        <text x="576" y="515" font-size="13" fill="#334155">Follow-up / escalate / monitor</text>
        <text x="576" y="535" font-size="13" fill="#334155">Outcome: accountable next steps</text>

        <rect x="870" y="465" width="360" height="130" rx="10" fill="#ECFDF3" stroke="#86EFAC" filter="url(#shadow)"/>
        <text x="886" y="492" font-size="16" font-weight="700" fill="#166534">Weekly Monitoring</text>
        <text x="886" y="515" font-size="13" fill="#14532D">Refresh mentions and new media signals</text>
        <text x="886" y="535" font-size="13" fill="#14532D">Outcome: continuously updated risk posture</text>

        <!-- Connectors -->
        <path d="M 310 115 L 680 115" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 610 115 L 680 115" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 820 175 L 820 235 L 190 235 L 190 245" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 330 310 L 360 310" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 640 310 L 670 310" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 950 310 L 980 310" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 1105 375 L 1105 430 L 390 430 L 390 465" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 530 530 L 560 530" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 1050 465 L 1050 390 L 810 390 L 810 375" stroke="#16A34A" stroke-width="2.2" fill="none" marker-end="url(#arrow)"/>

        <!-- Labels -->
        <text x="700" y="33" font-size="14" fill="#475569" text-anchor="middle">ENTRY</text>
        <text x="640" y="223" font-size="14" fill="#475569" text-anchor="middle">ANALYSIS</text>
        <text x="640" y="443" font-size="14" fill="#475569" text-anchor="middle">DECISIONS & OPERATIONS</text>
      </svg>
    </div>
    """
    components.html(html, height=770, scrolling=False)


def _render_competitor_watchlist() -> tuple[str, str]:
    st.markdown("#### Competitor watchlist")
    with st.form("dd_competitor_form", clear_on_submit=True):
        form_cols = st.columns([2, 1])
        with form_cols[0]:
            comp_name = st.text_input("Competitor name")
        with form_cols[1]:
            comp_type = st.selectbox("Type", list(COMPETITOR_TYPES), index=0)
        comp_notes = st.text_area("Notes (optional)", height=80)
        save_clicked = st.form_submit_button("Save competitor")
    if save_clicked:
        if not str(comp_name or "").strip():
            st.warning("Competitor name is required.")
        elif upsert_competitor(comp_name, comp_type, comp_notes):
            st.success("Competitor saved.")
            st.rerun()
        else:
            st.error("Could not save competitor.")

    competitors_df = list_competitors()
    if competitors_df.empty:
        st.caption("No competitors saved yet.")
        return "", ""

    st.dataframe(competitors_df, use_container_width=True, height=220)
    options = {}
    for row in competitors_df.itertuples(index=False):
        competitor_id = str(getattr(row, "competitorId", "") or "").strip()
        name = str(getattr(row, "name", "") or "").strip()
        competitor_type = str(getattr(row, "competitorType", "") or "").strip()
        if not competitor_id or not name:
            continue
        label = f"{name} ({competitor_type})"
        if label in options:
            label = f"{label} [{competitor_id[:8]}]"
        options[label] = (name, competitor_type, competitor_id)

    if not options:
        return "", ""

    selected_label = st.selectbox(
        "Select competitor",
        options=[""] + list(options.keys()),
        key="dd_competitor_select",
    )
    selected = options.get(selected_label)
    if selected:
        name, competitor_type, competitor_id = selected
        delete_cols = st.columns([2, 1])
        with delete_cols[1]:
            if st.button("Delete selected", key="dd_delete_competitor"):
                if delete_competitor(competitor_id):
                    st.success("Competitor deleted.")
                    st.rerun()
                else:
                    st.error("Could not delete competitor.")
        return name, competitor_type
    return "", ""


def render_due_diligence_page():
    st.subheader("Due Diligence")
    st.caption("Simple flow: Data Entry subject, watchlist, and launch DD.")

    def _set_subject(name: str, subject_type: str, start_mode: str) -> None:
        st.session_state["dd_subject_name"] = str(name or "").strip()
        st.session_state["dd_subject_type"] = str(subject_type or "").strip()
        st.session_state["dd_start_mode"] = str(start_mode or "").strip()

    data_entry_tab, watchlist_tab, launch_tab = st.tabs(["Data Entry", "Watchlist", "Launch"])

    with data_entry_tab:
        st.markdown("#### Data Entry")
        st.caption("Choose one source and set the subject for the investigation.")
        start_mode = st.radio(
            "Source",
            ["CRM context", "Competitors", "Watchlist"],
            horizontal=True,
            key="dd_intake_source",
        )

        if start_mode == "CRM context":
            crm_cols = st.columns([2, 1, 1])
            with crm_cols[0]:
                subject_name = st.text_input(
                    "CRM subject name",
                    key="dd_start_crm_subject",
                    help="Search target from CRM context.",
                ).strip()
            with crm_cols[1]:
                subject_type = st.selectbox(
                    "Type",
                    ["Person", "Company"],
                    key="dd_start_crm_subject_type",
                )
            with crm_cols[2]:
                st.write("")
                st.write("")
                if st.button("Set subject", key="dd_set_subject_crm", use_container_width=True):
                    if subject_name:
                        _set_subject(subject_name, subject_type, "CRM context")
                        st.success(f"Subject set: {subject_name} ({subject_type})")
                    else:
                        st.warning("Enter a CRM subject name.")

        elif start_mode == "Competitors":
            comp_cols = st.columns([2, 1, 1])
            with comp_cols[0]:
                subject_name = st.text_input(
                    "Competitor name",
                    key="dd_start_competitor_name",
                    help="Direct competitor intake.",
                ).strip()
            with comp_cols[1]:
                subject_type = st.selectbox(
                    "Type",
                    ["Person", "Company"],
                    key="dd_start_competitor_type",
                )
            with comp_cols[2]:
                st.write("")
                st.write("")
                if st.button(
                    "Set subject",
                    key="dd_set_subject_competitor",
                    use_container_width=True,
                ):
                    if subject_name:
                        _set_subject(subject_name, subject_type, "Competitors")
                        st.success(f"Subject set: {subject_name} ({subject_type})")
                    else:
                        st.warning("Enter a competitor name.")
        else:
            subject_name = str(st.session_state.get("dd_subject_name") or "").strip()
            subject_type = str(st.session_state.get("dd_subject_type") or "").strip()
            if subject_name and str(st.session_state.get("dd_start_mode") or "") == "Watchlist":
                st.success(f"Subject from watchlist: {subject_name} ({subject_type})")
            else:
                st.info("Go to the Watchlist tab, select a record, then set it as intake subject.")

        current_name = str(st.session_state.get("dd_subject_name") or "").strip()
        current_type = str(st.session_state.get("dd_subject_type") or "").strip()
        current_mode = str(st.session_state.get("dd_start_mode") or "").strip()
        if current_name:
            st.markdown("---")
            st.markdown("**Current intake subject**")
            st.success(f"{current_name} ({current_type}) — source: {current_mode or 'not set'}")

    with watchlist_tab:
        st.markdown("#### Watchlist")
        st.caption("Save competitors and optionally use one as your intake subject.")
        selected_name, selected_type = _render_competitor_watchlist()
        if selected_name and selected_type:
            st.success(f"Selected watchlist item: {selected_name} ({selected_type})")
            if st.button("Use selected as intake subject", key="dd_use_watchlist_subject"):
                _set_subject(selected_name, selected_type, "Watchlist")
                st.success("Watchlist subject set for intake.")
                st.rerun()

    with launch_tab:
        st.markdown("#### Launch")
        subject_name = str(st.session_state.get("dd_subject_name") or "").strip()
        subject_type = str(st.session_state.get("dd_subject_type") or "").strip()
        start_mode = str(st.session_state.get("dd_start_mode") or "CRM context")
        if subject_name:
            st.success(f"Launch subject: {subject_name} ({subject_type})")
        else:
            st.warning("No subject selected yet. Set one in Intake or Watchlist.")

        app_url = (
            str(get_config("DUE_DILIGENCE_APP_URL") or "").strip()
            or str(get_config("DD_APP_URL") or "").strip()
        )
        if app_url:
            st.success("External Due Diligence app is configured.")
            st.text_input("Configured app URL", value=app_url, key="dd_app_url_preview")
            app_launch_url = _append_query_params(
                app_url,
                {
                    "subject": subject_name,
                    "subject_type": subject_type,
                    "start_mode": start_mode.replace(" ", "_").lower(),
                },
            )
            action_cols = st.columns(3)
            with action_cols[0]:
                _link_button("🚀 Open DD app", app_launch_url or app_url)
            with action_cols[1]:
                if st.button("🖼️ Toggle embed", key="dd_embed_toggle", use_container_width=True):
                    st.session_state["dd_embed_external_app"] = not bool(
                        st.session_state.get("dd_embed_external_app")
                    )
            with action_cols[2]:
                to_email = st.text_input(
                    "Gmail to",
                    value=str(FEEDBACK_EMAIL_TO or "").strip(),
                    key="dd_gmail_to",
                    help="Optional recipient for Gmail compose action.",
                )
                gmail_url = _build_gmail_compose_url(
                    to_email=to_email,
                    subject="Due Diligence subject review",
                    body=(
                        f"Start mode: {start_mode}\n"
                        f"Subject: {subject_name or 'not set'}\n"
                        f"Subject type: {subject_type or 'not set'}\n\n"
                        f"Due Diligence app:\n{app_launch_url or app_url}"
                    ),
                )
                _link_button("✉️ Open in Gmail", gmail_url)
            with st.expander("Open app inside this tab", expanded=False):
                if st.checkbox("Embed external DD app", key="dd_embed_external_app"):
                    components.iframe(app_launch_url or app_url, height=900, scrolling=True)
        else:
            st.info(
                "External DD app URL is not configured yet. "
                "Set `DUE_DILIGENCE_APP_URL` (or `DD_APP_URL`) in secrets/.env."
            )
            st.markdown("**Run locally**")
            st.code(
                "cd DD\n"
                "python -m pip install -r requirements.txt\n"
                "python -m app.scripts.init_db\n"
                "streamlit run app/main.py",
                language="bash",
            )
            st.caption(
                "After deployment, set DUE_DILIGENCE_APP_URL so this tab can open/embed the live app."
            )
