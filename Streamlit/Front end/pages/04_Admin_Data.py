from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from crm.ui.pages.admin import render_admin_page
from crm.ui.pages.data import render_data_page
from crm.ui.shell import (
    apply_global_styles,
    ensure_db_connection,
    ensure_supporter_access,
    handle_special_entrypoints,
)


st.set_page_config(page_title="Admin / Data", layout="wide", initial_sidebar_state="collapsed")
apply_global_styles()
if handle_special_entrypoints():
    st.stop()
if not ensure_supporter_access("Admin/Data"):
    st.stop()
if not ensure_db_connection():
    st.stop()

st.subheader("Admin / Data")
admin_tab, data_tab = st.tabs(["Admin", "Data"])
with admin_tab:
    render_admin_page()
with data_tab:
    render_data_page()
