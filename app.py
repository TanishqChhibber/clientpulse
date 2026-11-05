"""
ClientPulse - Main Application Shell & Multipage Router
=======================================================
Agency performance reporting platform with Supabase PostgreSQL persistence
and Streamable HTTP MCP integration for Claude.
"""

import hmac
import os

import streamlit as st
import database
from utils.ui import apply_custom_theme, render_sidebar_brand

# Page configuration
st.set_page_config(
    page_title="ClientPulse | Marketing Agency SaaS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply global SaaS styling
apply_custom_theme()

# ------------------------------------------------------------------------------
# Direct Public Shareable Link Intercept
# ------------------------------------------------------------------------------
# If accessed via a public share token (e.g., http://localhost:8501/?page=public&token=XYZ),
# render the public report view cleanly without exposing agency administration navigation.
query_token = st.query_params.get("token")
query_page = st.query_params.get("page")

if query_token or query_page == "public":
    # Hide sidebar for public clients
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="stSidebarCollapsedControl"] {display: none;}
        </style>
        """,
        unsafe_allow_html=True
    )
    # Directly execute the public report page
    import importlib.util
    import os
    public_page_path = os.path.join(os.path.dirname(__file__), "pages", "5_public.py")
    spec = importlib.util.spec_from_file_location("public_page", public_page_path)
    public_mod = importlib.util.module_from_spec(spec)
    # Public visitors may only view the report their token points to (no report picker)
    public_mod.PUBLIC_LINK_MODE = True
    spec.loader.exec_module(public_mod)
    st.stop()

# ------------------------------------------------------------------------------
# Optional Agency Login (enabled when APP_PASSWORD is set)
# ------------------------------------------------------------------------------
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

if APP_PASSWORD and not st.session_state.get("agency_authenticated"):
    st.markdown("### ⚡ ClientPulse Agency Login")
    with st.form("agency_login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Sign In"):
            if hmac.compare_digest(entered.encode(), APP_PASSWORD.encode()):
                st.session_state["agency_authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.stop()

# ------------------------------------------------------------------------------
# Multipage Navigation Setup for Agency Users
# ------------------------------------------------------------------------------
render_sidebar_brand()

pages = [
    st.Page("pages/1_overview.py", title="Overview Dashboard", icon="📊", default=True),
    st.Page("pages/2_clients.py", title="Client Management", icon="👥"),
    st.Page("pages/3_create_report.py", title="Create & Edit Report", icon="📝"),
    st.Page("pages/4_history.py", title="Report History", icon="📂"),
    st.Page("pages/5_public.py", title="Public Shareable View", icon="🌐"),
]

nav = st.navigation(pages)
nav.run()
