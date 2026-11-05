"""
ClientPulse - Public Client-Facing Report
=========================================
Client-facing campaign reporting view accessible without login via secure
unique share token.
"""

import re

import streamlit as st
import database
from utils.dashboard import render_dashboard_body
from utils.pdf_report import build_report_pdf
from utils.ui import apply_custom_theme, esc, render_html

apply_custom_theme()

# Read token from query parameters
query_token = st.query_params.get("token", None)

# Set by app.py when this page is served to an external visitor via a share link.
# In that mode the agency report picker must never be shown.
public_link_mode = globals().get("PUBLIC_LINK_MODE", False)

# If no token in query params, provide an interactive token selector/input (agency preview only)
token = query_token
if not token and public_link_mode:
    st.error("⚠️ This report link is incomplete. Please use the full link shared by your agency.")
    st.stop()

if not token:
    st.markdown(
        """
        <div style="background:#F5F3FF; border:1px solid #DDD6FE; border-radius:12px; padding:1.5rem; margin-bottom:1.5rem;">
            <h3 style="margin:0 0 0.5rem 0; color:#4F46E5;">🌐 Public Client Portal</h3>
            <p style="margin:0; color:#4B5563; font-size:0.9rem;">
                This page renders published client-facing reports. In production, clients access this directly via their unique shareable link (without agency login).
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    published_reps = [r for r in database.get_reports() if r.get("status") == "published"]
    if published_reps:
        options = {r["share_token"]: f"{r['title']} - {r['client_name']}" for r in published_reps}
        selected_token = st.selectbox(
            "Select Published Report to Preview as Client",
            options=list(options.keys()),
            format_func=lambda x: options[x]
        )
        token = selected_token
    else:
        st.info("No reports are currently published. Go to Report Builder or Report History to publish a report.")
        token_input = st.text_input("Or enter a Share Token manually:")
        if token_input:
            token = token_input.strip()

if not token:
    st.stop()

# Retrieve report by share token
report = database.get_report_by_share_token(token)

if not report:
    st.error("⚠️ Invalid or expired report link. Either this report does not exist or it has not been published yet.")
    st.stop()

# ------------------------------------------------------------------------------
# Client-facing report: same dashboard as the agency view, read-only
# ------------------------------------------------------------------------------
breakdowns = database.get_report_breakdowns(report["id"])
insights = database.get_report_insights(report)
spec = database.get_dashboard_spec(report)
client_name = report.get("client_name", "Client")
client_industry = report.get("client_industry", "")

hero_col, pdf_col = st.columns([4, 1], vertical_alignment="center")
with hero_col:
    render_html(f"""
        <div class="public-report-hero" style="margin-bottom:1rem;">
            <div class="public-report-agency">⚡ ClientPulse &bull; Campaign Performance Report</div>
            <h1 class="public-report-title">{esc(report.get('title'))}</h1>
            <div class="public-report-meta">
                <strong>Client:</strong> {esc(client_name)} &nbsp;&bull;&nbsp;
                {f"<strong>Industry:</strong> {esc(client_industry)} &nbsp;&bull;&nbsp; " if client_industry else ""}
                <strong>Reporting Period:</strong> {esc(report.get('period_start'))} to {esc(report.get('period_end'))}
            </div>
        </div>
    """)
with pdf_col:
    pdf_name = re.sub(r"[^A-Za-z0-9]+", "-", f"{client_name} {report.get('title', 'report')}").strip("-").lower()
    st.download_button(
        "⬇ Download PDF",
        data=lambda: build_report_pdf(report, breakdowns, insights, spec),
        file_name=f"{pdf_name}.pdf",
        mime="application/pdf",
        on_click="ignore",
        type="primary",
        width="stretch",
    )

render_dashboard_body(report, breakdowns, insights, show_insights=True, key_suffix="public", client_view=True, spec=spec)

render_html("""
    <div style="font-size:0.85rem; color:#94A3B8; border-top:1px solid #E2E8F0; padding-top:1rem; margin-top:1rem;">
        Prepared by your Digital Marketing Agency &bull; Powered by <strong>ClientPulse</strong>
    </div>
""")
