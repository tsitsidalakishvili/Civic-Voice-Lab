from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from crm.ui.pages.dashboard import render_dashboard_how_it_works
from crm.ui.pages.due_diligence import render_due_diligence_how_it_works
from crm.ui.shell import (
    apply_global_styles,
    ensure_supporter_access,
    handle_special_entrypoints,
)


st.set_page_config(page_title="Home", layout="wide", initial_sidebar_state="collapsed")
apply_global_styles()

if handle_special_entrypoints():
    st.stop()

st.title("Home")


def _render_deliberation_how_it_works() -> None:
    st.markdown("### Deliberation workflow")
    html = """
    <div style="width:100%; background:#ffffff; border:1px solid #E2E8F0; border-radius:12px; padding:8px;">
      <svg viewBox="0 0 1240 520" width="100%" height="500" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748B"></path>
          </marker>
        </defs>
        <rect x="20" y="18" width="1200" height="484" rx="12" fill="#F8FAFC" stroke="#E2E8F0"/>
        <text x="42" y="46" font-size="18" font-weight="700" fill="#0B3A52">Deliberation Flow</text>

        <rect x="45" y="84" width="210" height="122" rx="10" fill="#EEF2FF" stroke="#A5B4FC"/>
        <text x="62" y="112" font-size="15" font-weight="700" fill="#312E81">1) Configure</text>
        <text x="62" y="136" font-size="12" fill="#3730A3">Create conversation topic,</text>
        <text x="62" y="154" font-size="12" fill="#3730A3">moderation, and rules.</text>

        <rect x="275" y="84" width="210" height="122" rx="10" fill="#EFF6FF" stroke="#93C5FD"/>
        <text x="292" y="112" font-size="15" font-weight="700" fill="#1E3A8A">2) Share</text>
        <text x="292" y="136" font-size="12" fill="#334155">Distribute participant/admin</text>
        <text x="292" y="154" font-size="12" fill="#334155">links and questionnaire.</text>

        <rect x="505" y="84" width="210" height="122" rx="10" fill="#ECFDF3" stroke="#86EFAC"/>
        <text x="522" y="112" font-size="15" font-weight="700" fill="#166534">3) Participate</text>
        <text x="522" y="136" font-size="12" fill="#14532D">Participants swipe vote:</text>
        <text x="522" y="154" font-size="12" fill="#14532D">agree, disagree, pass.</text>

        <rect x="735" y="84" width="210" height="122" rx="10" fill="#FFF7ED" stroke="#FDBA74"/>
        <text x="752" y="112" font-size="15" font-weight="700" fill="#9A3412">4) Moderate</text>
        <text x="752" y="136" font-size="12" fill="#7C2D12">Review submitted comments</text>
        <text x="752" y="154" font-size="12" fill="#7C2D12">before publishing.</text>

        <rect x="965" y="84" width="210" height="122" rx="10" fill="#FDF2F8" stroke="#F9A8D4"/>
        <text x="982" y="112" font-size="15" font-weight="700" fill="#9D174D">5) Monitor</text>
        <text x="982" y="136" font-size="12" fill="#831843">Track consensus, clusters,</text>
        <text x="982" y="154" font-size="12" fill="#831843">and report-ready insights.</text>

        <path d="M 255 145 L 275 145" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 485 145 L 505 145" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 715 145 L 735 145" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>
        <path d="M 945 145 L 965 145" stroke="#64748B" stroke-width="2" fill="none" marker-end="url(#arrow)"/>

        <rect x="45" y="252" width="1130" height="98" rx="10" fill="#EFF6FF" stroke="#BFDBFE"/>
        <text x="66" y="284" font-size="16" font-weight="700" fill="#1E3A8A">Shared deliberation data layer</text>
        <text x="66" y="309" font-size="13" fill="#334155">Conversations, comments, and votes stay synchronized between participant and admin views.</text>
        <text x="66" y="330" font-size="13" fill="#334155">Mobile swipe UX and moderation both feed the same analytics outputs.</text>

        <rect x="45" y="368" width="1130" height="112" rx="10" fill="#F8FAFC" stroke="#CBD5E1"/>
        <text x="66" y="400" font-size="16" font-weight="700" fill="#0F172A">Operational loop</text>
        <text x="66" y="425" font-size="13" fill="#334155">Configure → collect input → moderate quality → monitor consensus → refine next conversation.</text>
        <text x="66" y="447" font-size="13" fill="#334155">This creates a repeatable participation cycle with measurable outcomes.</text>
      </svg>
    </div>
    """
    components.html(html, height=510, scrolling=False)

if not ensure_supporter_access("Home"):
    st.stop()

st.markdown("### How it works")
crm_tab, dd_tab, deliberation_tab = st.tabs(["CRM", "Due Diligence", "Deliberation"])
with crm_tab:
    render_dashboard_how_it_works()
with dd_tab:
    render_due_diligence_how_it_works()
with deliberation_tab:
    _render_deliberation_how_it_works()
