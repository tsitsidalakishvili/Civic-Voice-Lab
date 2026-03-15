import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from crm.analytics.people import load_supporter_summary
from crm.clients.deliberation import (
    list_due_diligence_reports,
    run_due_diligence_analysis,
    run_due_diligence_debate_prep,
)
from crm.config import DELIBERATION_API_URL, FEEDBACK_EMAIL_TO, get_config
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


def _render_competitor_watchlist(key_prefix: str = "dd_watchlist") -> tuple[str, str]:
    st.markdown("#### Competitor watchlist")
    prefix = str(key_prefix or "dd_watchlist").strip()
    with st.form(f"{prefix}_competitor_form", clear_on_submit=True):
        form_cols = st.columns([2, 1])
        with form_cols[0]:
            comp_name = st.text_input("Competitor name", key=f"{prefix}_competitor_name")
        with form_cols[1]:
            comp_type = st.selectbox(
                "Type",
                list(COMPETITOR_TYPES),
                index=0,
                key=f"{prefix}_competitor_type",
            )
        comp_notes = st.text_area("Notes (optional)", height=80, key=f"{prefix}_competitor_notes")
        save_clicked = st.form_submit_button("Save competitor", use_container_width=True)
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
        key=f"{prefix}_competitor_select",
    )
    selected = options.get(selected_label)
    if selected:
        name, competitor_type, competitor_id = selected
        delete_cols = st.columns([2, 1])
        with delete_cols[1]:
            if st.button("Delete selected", key=f"{prefix}_delete_competitor"):
                if delete_competitor(competitor_id):
                    st.success("Competitor deleted.")
                    st.rerun()
                else:
                    st.error("Could not delete competitor.")
        return name, competitor_type
    return "", ""


def _render_synced_source_checkbox(
    label: str,
    *,
    config_key: str,
    widget_key: str,
    default: bool = True,
) -> bool:
    current = bool(st.session_state.get(config_key, default))
    selected = st.checkbox(label, value=current, key=widget_key)
    st.session_state[config_key] = bool(selected)
    return bool(selected)


def render_due_diligence_page():
    st.subheader("Due Diligence")
    st.caption(
        "Select person/organization, check CRM + competitors, run analysis, then launch workflow."
    )

    def _set_subject(name: str, subject_type: str, start_mode: str) -> None:
        st.session_state["dd_subject_name"] = str(name or "").strip()
        st.session_state["dd_subject_type"] = str(subject_type or "").strip()
        st.session_state["dd_start_mode"] = str(start_mode or "").strip()

    analysis_tab, debate_tab, configure_tab, watchlist_tab, launch_tab = st.tabs(
        ["Analysis", "Debate prep", "Configure", "Watchlist", "Launch"]
    )

    with analysis_tab:
        st.markdown("#### Subject analysis")
        analysis_cols = st.columns([3, 1, 1])
        with analysis_cols[0]:
            default_subject = str(st.session_state.get("dd_subject_name") or "").strip()
            if "dd_analysis_subject_name" not in st.session_state and default_subject:
                st.session_state["dd_analysis_subject_name"] = default_subject
            subject_name = st.text_input(
                "Person / organization",
                key="dd_analysis_subject_name",
                placeholder="Enter full name or organization...",
            ).strip()
        with analysis_cols[1]:
            subject_type = st.selectbox(
                "Type",
                ["Person", "Organization"],
                key="dd_analysis_subject_type",
            )
        with analysis_cols[2]:
            st.write("")
            st.write("")
            if st.button("Set active subject", key="dd_set_subject_analysis", use_container_width=True):
                if subject_name:
                    _set_subject(subject_name, subject_type, "Analysis")
                    st.success(f"Active subject: {subject_name} ({subject_type})")
                else:
                    st.warning("Enter a subject name first.")

        if st.button("Run internal checks", key="dd_run_internal_checks"):
            st.session_state["dd_run_internal_checks"] = True

        run_checks = bool(st.session_state.get("dd_run_internal_checks", False))
        if run_checks and subject_name:
            query = subject_name.lower()
            crm_df = load_supporter_summary()
            if crm_df.empty:
                crm_matches = crm_df
            else:
                name_series = (
                    crm_df["fullName"].astype(str).str.lower()
                    if "fullName" in crm_df.columns
                    else crm_df.index.to_series().map(lambda _: "")
                )
                email_series = (
                    crm_df["email"].astype(str).str.lower()
                    if "email" in crm_df.columns
                    else crm_df.index.to_series().map(lambda _: "")
                )
                searchable = name_series + " " + email_series
                crm_matches = crm_df[searchable.str.contains(query, na=False)]

            comp_df = list_competitors()
            if comp_df.empty:
                comp_matches = comp_df
            else:
                comp_searchable = (
                    comp_df["name"].astype(str).str.lower()
                    if "name" in comp_df.columns
                    else comp_df.index.to_series().map(lambda _: "")
                )
                comp_matches = comp_df[comp_searchable.str.contains(query, na=False)]

            metric_cols = st.columns(3)
            metric_cols[0].metric("CRM matches", len(crm_matches))
            metric_cols[1].metric("Competitor matches", len(comp_matches))
            metric_cols[2].metric(
                "Subject status",
                "Known"
                if (len(crm_matches) + len(comp_matches)) > 0
                else "New",
            )

            crm_match_cols = [c for c in ["fullName", "email", "group"] if c in crm_matches.columns]
            comp_match_cols = [c for c in ["name", "competitorType", "notes"] if c in comp_matches.columns]

            st.markdown("##### CRM check results")
            if crm_matches.empty:
                st.caption("No CRM records matched this subject.")
            elif crm_match_cols:
                st.dataframe(crm_matches[crm_match_cols], use_container_width=True, height=180)

            st.markdown("##### Competitor check results")
            if comp_matches.empty:
                st.caption("No competitor records matched this subject.")
            elif comp_match_cols:
                st.dataframe(comp_matches[comp_match_cols], use_container_width=True, height=180)

        st.markdown("---")
        st.markdown("##### External analysis sources")
        src_cols = st.columns(3)
        with src_cols[0]:
            _render_synced_source_checkbox(
                "Wikidata",
                config_key="dd_cfg_use_wikidata",
                widget_key="dd_cfg_use_wikidata_analysis",
                default=True,
            )
        with src_cols[1]:
            _render_synced_source_checkbox(
                "OpenSanctions",
                config_key="dd_cfg_use_opensanctions",
                widget_key="dd_cfg_use_opensanctions_analysis",
                default=True,
            )
        with src_cols[2]:
            _render_synced_source_checkbox(
                "News / Web",
                config_key="dd_cfg_use_news",
                widget_key="dd_cfg_use_news_analysis",
                default=True,
            )
        use_demo = st.checkbox(
            "Use demo data if sources are unavailable",
            value=bool(st.session_state.get("dd_cfg_use_demo", True)),
            key="dd_cfg_use_demo",
        )
        if st.button("Run analysis", key="dd_run_external_analysis"):
            if not subject_name:
                st.warning("Set a subject first.")
            else:
                enabled = []
                if st.session_state.get("dd_cfg_use_wikidata"):
                    enabled.append("Wikidata")
                if st.session_state.get("dd_cfg_use_opensanctions"):
                    enabled.append("OpenSanctions")
                if st.session_state.get("dd_cfg_use_news"):
                    enabled.append("News/Web")
                progress = st.progress(0, text="Starting external analysis...")
                payload = {
                    "subject": subject_name,
                    "subjectType": subject_type or "Person",
                    "useWikidata": bool(st.session_state.get("dd_cfg_use_wikidata", True)),
                    "useOpenSanctions": bool(st.session_state.get("dd_cfg_use_opensanctions", True)),
                    "useNews": bool(st.session_state.get("dd_cfg_use_news", True)),
                    "maxNews": 8,
                    "demo": bool(use_demo),
                }
                progress.progress(25, text="Querying public sources...")
                result = run_due_diligence_analysis(payload, show_error=True)
                if result:
                    st.session_state["dd_analysis_result"] = result
                    progress.progress(80, text="Storing and compiling report...")
                    st.success(
                        f"Analysis complete for {subject_name} ({subject_type}) using: "
                        f"{', '.join(enabled) if enabled else 'no sources selected'}."
                    )
                    progress.progress(100, text="Report ready.")
                    warnings_text = " ".join(result.get("warnings") or []).lower()
                    steps = [
                        ("Validate subject", "Done"),
                        (
                            "Query Wikidata",
                            "Skipped"
                            if not payload["useWikidata"]
                            else ("Warning" if "wikidata request failed" in warnings_text else "Done"),
                        ),
                        (
                            "Query OpenSanctions",
                            "Skipped"
                            if not payload["useOpenSanctions"]
                            else (
                                "Warning"
                                if "opensanctions request failed" in warnings_text
                                else "Done"
                            ),
                        ),
                        (
                            "Query News / Web",
                            "Skipped"
                            if not payload["useNews"]
                            else ("Warning" if "gdelt news request failed" in warnings_text else "Done"),
                        ),
                        ("Store report", "Done" if result.get("reportId") else "Warning"),
                        ("Compile report", "Done"),
                    ]
                    st.session_state["dd_analysis_steps"] = steps

        analysis_result = st.session_state.get("dd_analysis_result") or {}
        analysis_steps = st.session_state.get("dd_analysis_steps") or []
        if analysis_steps:
            st.markdown("##### Analysis steps")
            step_df = pd.DataFrame(analysis_steps, columns=["Step", "Status"])
            st.dataframe(step_df, use_container_width=True, height=220)
        if analysis_result:
            summary = analysis_result.get("summary") or {}
            st.markdown("##### External analysis results")
            st.info(
                f"Risk level: {summary.get('risk_level', 'Unknown')} · "
                f"Total hits: {summary.get('total_hits', 0)}"
            )
            if "risk_score" in summary:
                st.caption(f"Risk score: {summary.get('risk_score', 0)}/100")
            rationale = summary.get("risk_rationale") or []
            if rationale:
                st.markdown("**Risk rationale**")
                for item in rationale:
                    st.write(f"- {item}")
            report_id = str(analysis_result.get("reportId") or "").strip()
            if report_id:
                pdf_url = f"{DELIBERATION_API_URL.rstrip('/')}/due-diligence/reports/{report_id}/pdf"
                _link_button("Download PDF report", pdf_url)
            warnings = analysis_result.get("warnings") or []
            if warnings:
                st.warning("\n".join([str(w) for w in warnings]))

            wikidata_rows = analysis_result.get("wikidata") or []
            if wikidata_rows:
                st.markdown("**Wikidata**")
                st.dataframe(pd.DataFrame(wikidata_rows), use_container_width=True, height=180)
            else:
                st.caption("No Wikidata matches.")

            opensanctions_rows = analysis_result.get("opensanctions") or []
            if opensanctions_rows:
                st.markdown("**OpenSanctions**")
                st.dataframe(pd.DataFrame(opensanctions_rows), use_container_width=True, height=180)
            else:
                st.caption("No OpenSanctions matches.")

            news_rows = analysis_result.get("news") or []
            if news_rows:
                st.markdown("**News / Web (GDELT)**")
                st.dataframe(pd.DataFrame(news_rows), use_container_width=True, height=220)
            else:
                st.caption("No recent news found.")

        if subject_name:
            st.markdown("##### Report history")
            history_rows = list_due_diligence_reports(subject_name, limit=8, show_error=False) or []
            if history_rows:
                history_df = pd.DataFrame(history_rows)
                st.dataframe(history_df, use_container_width=True, height=220)
                for row in history_rows:
                    report_id = str(row.get("reportId") or "").strip()
                    if not report_id:
                        continue
                    pdf_url = (
                        f"{DELIBERATION_API_URL.rstrip('/')}/due-diligence/reports/{report_id}/pdf"
                    )
                    created_at = row.get("createdAt") or "—"
                    risk_level = row.get("riskLevel") or "—"
                    st.markdown(f"- {created_at} · {risk_level} · [PDF]({pdf_url})")
            else:
                st.caption("No prior reports for this subject.")

    with debate_tab:
        st.markdown("#### Debate prep")
        st.caption(
            "Search Google and Wikipedia to map public context and debate strategy themes."
        )
        default_opponent = str(st.session_state.get("dd_subject_name") or "").strip()
        if "dd_debate_opponent" not in st.session_state and default_opponent:
            st.session_state["dd_debate_opponent"] = default_opponent
        if "dd_debate_topic" not in st.session_state:
            st.session_state["dd_debate_topic"] = "education"

        debate_cols = st.columns([3, 2, 1, 1])
        with debate_cols[0]:
            opponent = st.text_input("Opponent name", key="dd_debate_opponent")
        with debate_cols[1]:
            topic = st.text_input("Topic", key="dd_debate_topic")
        with debate_cols[2]:
            years_back = st.number_input(
                "Years back", min_value=1, max_value=10, value=2, step=1, key="dd_debate_years"
            )
        with debate_cols[3]:
            max_results = st.number_input(
                "Max results",
                min_value=5,
                max_value=100,
                value=25,
                step=5,
                key="dd_debate_max_results",
            )
        debate_opts = st.columns(3)
        with debate_opts[0]:
            use_wikipedia = st.checkbox(
                "Wikipedia primer",
                value=bool(st.session_state.get("dd_debate_wikipedia", True)),
                key="dd_debate_wikipedia",
            )
        with debate_opts[1]:
            use_google = st.checkbox(
                "Google search results",
                value=bool(st.session_state.get("dd_debate_google", True)),
                key="dd_debate_google",
            )
        with debate_opts[2]:
            use_local_media = st.checkbox(
                "Local media RSS (Publika, Netgazeti)",
                value=bool(st.session_state.get("dd_debate_local_media", True)),
                key="dd_debate_local_media",
            )
        use_demo = st.checkbox(
            "Use demo data if sources are unavailable",
            value=bool(st.session_state.get("dd_debate_demo", True)),
            key="dd_debate_demo",
        )
        if st.button("Run debate prep", key="dd_run_debate_prep"):
            if not opponent or not topic:
                st.warning("Enter an opponent name and topic.")
            else:
                payload = {
                    "opponent": opponent.strip(),
                    "topic": topic.strip(),
                    "yearsBack": int(years_back),
                    "maxResults": int(max_results),
                    "useWikipedia": bool(use_wikipedia),
                    "useGoogle": bool(use_google),
                    "useLocalMedia": bool(use_local_media),
                    "demo": bool(use_demo),
                }
                result = run_due_diligence_debate_prep(payload, show_error=True)
                if result:
                    st.session_state["dd_debate_result"] = result

        debate_result = st.session_state.get("dd_debate_result") or {}
        if debate_result:
            mentions = debate_result.get("mentions") or []
            st.success(
                f"{len(mentions)} mentions · {debate_result.get('startDate')} → "
                f"{debate_result.get('endDate')}"
            )
            st.caption(f"Query: {debate_result.get('query')}")
            keywords = debate_result.get("keywords") or []
            if keywords:
                st.caption(f"Keywords: {', '.join(keywords)}")
            warnings = debate_result.get("warnings") or []
            if warnings:
                st.warning("\n".join([str(w) for w in warnings]))

            wiki_results = debate_result.get("wikipedia") or []
            if wiki_results:
                st.markdown("##### Wikipedia primer")
                st.dataframe(pd.DataFrame(wiki_results), use_container_width=True, height=220)
            else:
                st.caption("No Wikipedia matches yet.")

            themes = debate_result.get("themes") or []
            if themes:
                st.markdown("##### Strategy map")
                st.dataframe(pd.DataFrame(themes), use_container_width=True, height=220)
            else:
                st.caption("No themes detected yet.")

            if mentions:
                st.markdown("##### Web mentions")
                st.dataframe(pd.DataFrame(mentions), use_container_width=True, height=260)
                st.markdown("##### Source links")
                for item in mentions[:12]:
                    title = item.get("title") or "Source"
                    url = item.get("url") or ""
                    if url:
                        st.markdown(f"- [{title}]({url})")
            else:
                st.caption("No mentions found for this query.")

    with configure_tab:
        st.markdown("#### Configure")
        cfg_data_tab, cfg_sources_tab = st.tabs(["CRM & Competitors", "Public sources"])
        with cfg_data_tab:
            summary_df = load_supporter_summary()
            total_people = len(summary_df)
            if not summary_df.empty and "group" in summary_df.columns:
                total_supporters = int((summary_df["group"] == "Supporter").sum())
                total_members = int((summary_df["group"] == "Member").sum())
            else:
                total_supporters = 0
                total_members = 0
            mcols = st.columns(3)
            mcols[0].metric("CRM people", total_people)
            mcols[1].metric("Supporters", total_supporters)
            mcols[2].metric("Members", total_members)
            st.markdown("##### Competitor records")
            selected_name, selected_type = _render_competitor_watchlist(
                key_prefix="dd_cfg_competitor"
            )
            if selected_name and selected_type:
                if st.button("Set selected as active subject", key="dd_cfg_use_selected_subject"):
                    _set_subject(selected_name, selected_type, "Configure")
                    st.success(f"Active subject set: {selected_name} ({selected_type})")
                    st.rerun()

        with cfg_sources_tab:
            st.caption("Control which external sources are used during analysis.")
            _render_synced_source_checkbox(
                "Enable Wikidata",
                config_key="dd_cfg_use_wikidata",
                widget_key="dd_cfg_use_wikidata_configure",
                default=True,
            )
            _render_synced_source_checkbox(
                "Enable OpenSanctions",
                config_key="dd_cfg_use_opensanctions",
                widget_key="dd_cfg_use_opensanctions_configure",
                default=True,
            )
            _render_synced_source_checkbox(
                "Enable News / Web",
                config_key="dd_cfg_use_news",
                widget_key="dd_cfg_use_news_configure",
                default=True,
            )
            st.markdown("##### Source connection status")
            open_key = str(get_config("OPENSANCTIONS_API_KEY") or "").strip()
            news_key = str(get_config("NEWS_API_KEY") or "").strip()
            st.write(f"- OpenSanctions API key: {'Configured' if open_key else 'Not configured'}")
            st.write(f"- News API key: {'Configured' if news_key else 'Not configured'}")
            st.caption(
                "API keys and base URLs are managed in .env / Streamlit secrets."
            )

    with watchlist_tab:
        st.markdown("#### Watchlist")
        st.caption("Save competitors and optionally use one as your intake subject.")
        selected_name, selected_type = _render_competitor_watchlist(
            key_prefix="dd_watchlist_competitor"
        )
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
        start_mode = str(st.session_state.get("dd_start_mode") or "Analysis")
        if subject_name:
            st.success(f"Launch subject: {subject_name} ({subject_type})")
        else:
            st.warning("No subject selected yet. Set one in Analysis or Watchlist.")

        app_url = (
            str(get_config("DUE_DILIGENCE_APP_URL") or "").strip()
            or str(get_config("DD_APP_URL") or "").strip()
        )
        use_wikidata = bool(st.session_state.get("dd_cfg_use_wikidata", True))
        use_opensanctions = bool(st.session_state.get("dd_cfg_use_opensanctions", True))
        use_news = bool(st.session_state.get("dd_cfg_use_news", True))
        if app_url:
            st.success("External Due Diligence app is configured.")
            st.text_input("Configured app URL", value=app_url, key="dd_app_url_preview")
            app_launch_url = _append_query_params(
                app_url,
                {
                    "subject": subject_name,
                    "subject_type": subject_type,
                    "start_mode": start_mode.replace(" ", "_").lower(),
                    "use_wikidata": "1" if use_wikidata else "0",
                    "use_opensanctions": "1" if use_opensanctions else "0",
                    "use_news": "1" if use_news else "0",
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
                        f"Wikidata: {'on' if use_wikidata else 'off'}\n"
                        f"OpenSanctions: {'on' if use_opensanctions else 'off'}\n"
                        f"News/Web: {'on' if use_news else 'off'}\n\n"
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
