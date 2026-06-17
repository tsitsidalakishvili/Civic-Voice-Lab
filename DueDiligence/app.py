from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crm.ui.pages.due_diligence import render_due_diligence_page
from crm.ui.shell import (
    apply_global_styles,
    ensure_supporter_access,
    handle_special_entrypoints,
)


st.set_page_config(
    page_title="FS Due Diligence",
    layout="wide",
    initial_sidebar_state="collapsed",
)
apply_global_styles()

if handle_special_entrypoints():
    st.stop()
if not ensure_supporter_access("Due Diligence"):
    st.stop()

render_due_diligence_page()
