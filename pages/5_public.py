"""
ClientPulse - Public Client-Facing Report
=========================================
Client-facing campaign reporting view accessible without login via secure
unique share token.
"""

from typing import Optional

import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import database
from utils.ui import apply_custom_theme, get_plotly_layout, esc, build_period_comparison_chart, render_html

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

# Extract report values
client_name = report.get("client_name", "Client")
client_industry = report.get("client_industry", "")
title = report.get("title", "Campaign Performance Report")
period_start = report.get("period_start", "")
period_end = report.get("period_end", "")

spend = float(report.get("spend", 0.0))
impressions = int(report.get("impressions", 0))
clicks = int(report.get("clicks", 0))
leads = int(report.get("leads", 0))
ctr = float(report.get("ctr", 0.0))
cpl = float(report.get("cpl", 0.0))
cvr = float(report.get("conversion_rate", 0.0))

prev_spend = float(report.get("prev_spend", 0.0))
prev_imp = int(report.get("prev_impressions", 0))
prev_clicks = int(report.get("prev_clicks", 0))
prev_leads = int(report.get("prev_leads", 0))

prev_cpl = (prev_spend / prev_leads) if prev_leads > 0 else 0.0
prev_ctr = (prev_clicks / prev_imp * 100) if prev_imp > 0 else 0.0

delta_spend = ((spend - prev_spend) / prev_spend * 100) if prev_spend > 0 else None
delta_leads = ((leads - prev_leads) / prev_leads * 100) if prev_leads > 0 else None
delta_cpl = ((cpl - prev_cpl) / prev_cpl * 100) if prev_cpl > 0 else None
delta_ctr = ((ctr - prev_ctr) / prev_ctr * 100) if prev_ctr > 0 else None


def render_public_metric(label: str, value: str, delta, higher_is_better: Optional[bool]):
    """Metric card with a vs-previous-period delta; higher_is_better=None renders it neutral."""
    if delta is None:
        delta_class, delta_text = "cp-delta-neutral", "No previous period data"
    else:
        if higher_is_better is None:
            delta_class = "cp-delta-neutral"
        else:
            is_good = delta >= 0 if higher_is_better else delta <= 0
            delta_class = "cp-delta-positive" if is_good else "cp-delta-negative"
        delta_text = f"{delta:+.1f}% vs prev period"
    st.markdown(
        f"""
        <div class="cp-metric-card">
            <div class="cp-metric-label">{label}</div>
            <div class="cp-metric-value">{value}</div>
            <div class="cp-metric-delta {delta_class}">{delta_text}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# ------------------------------------------------------------------------------
# Client Facing Presentation
# ------------------------------------------------------------------------------
render_html(
    f"""
    <div class="public-report-hero">
        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
                <div class="public-report-agency">⚡ ClientPulse &bull; Campaign Performance Report</div>
                <h1 class="public-report-title">{esc(title)}</h1>
                <div class="public-report-meta">
                    <strong>Client:</strong> {esc(client_name)} &nbsp;&bull;&nbsp; 
                    {f"<strong>Industry:</strong> {esc(client_industry)} &nbsp;&bull;&nbsp; " if client_industry else ""}
                    <strong>Reporting Period:</strong> {esc(period_start)} to {esc(period_end)}
                </div>
            </div>
            <div style="text-align:right;">
                <span class="cp-badge cp-badge-published">Official Agency Report</span>
            </div>
        </div>
    </div>
    """
)

# Metric Cards
mcol1, mcol2, mcol3, mcol4 = st.columns(4)

with mcol1:
    # Spend going up is neither good nor bad on its own, so keep it neutral
    render_public_metric("Ad Spend", f"${spend:,.2f}", delta_spend, higher_is_better=None)
with mcol2:
    render_public_metric("Qualified Leads", f"{leads:,}", delta_leads, higher_is_better=True)
with mcol3:
    render_public_metric("Cost Per Lead (CPL)", f"${cpl:.2f}", delta_cpl, higher_is_better=False)
with mcol4:
    render_public_metric("Click-Through Rate", f"{ctr:.2f}%", delta_ctr, higher_is_better=True)

st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

# Visual Chart Section
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("##### 📊 Campaign Conversion Funnel")
    fig_funnel = go.Figure(go.Funnel(
        y=["Impressions", "Clicks", "Conversions (Leads)"],
        x=[impressions, clicks, leads],
        textinfo="value+percent initial",
        marker={"color": ["#818CF8", "#6366F1", "#10B981"]}
    ))
    layout_f = get_plotly_layout("", height=320)
    fig_funnel.update_layout(layout_f)
    st.plotly_chart(fig_funnel, width="stretch")

with chart_col2:
    st.markdown("##### ⚖️ Current vs. Previous Period Comparison")
    fig_bar = build_period_comparison_chart([
        ("Previous", {"spend": prev_spend, "clicks": prev_clicks, "leads": prev_leads}, "#CBD5E1"),
        ("Current", {"spend": spend, "clicks": clicks, "leads": leads}, "#4F46E5"),
    ])
    st.plotly_chart(fig_bar, width="stretch")

# ------------------------------------------------------------------------------
# Qualitative Narrative & Recommendations
# ------------------------------------------------------------------------------
st.markdown("---")
st.markdown("### 📋 Executive Performance Summary")
st.markdown(
    f"""
    <div class="public-narrative-card">
        <p style="margin:0; font-size:1rem; line-height:1.7; color:#334155; white-space:pre-line;">{esc(report.get('summary') or 'No summary provided.')}</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("### 💡 Strategic Next Steps & Recommendations")
st.markdown(
    f"""
    <div class="public-recommendations-card">
        <p style="margin:0; font-size:1rem; line-height:1.7; color:#334155; white-space:pre-line;">{esc(report.get('recommendations') or 'No recommendations provided.')}</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<div style='margin-top: 2rem;'></div>", unsafe_allow_html=True)

# Footer & Print button
fcol1, fcol2 = st.columns([3, 1])
with fcol1:
    st.markdown(
        """
        <div style="font-size:0.85rem; color:#94A3B8; border-top:1px solid #E2E8F0; padding-top:1rem;">
            Prepared by your Digital Marketing Agency &bull; Powered by <strong>ClientPulse</strong>
        </div>
        """,
        unsafe_allow_html=True
    )
with fcol2:
    # st.markdown strips inline event handlers, so the button lives in a small same-origin iframe
    print_button_html = """
        <button onclick="window.parent.print()" style="float:right; background:#F1F5F9; border:1px solid #CBD5E1; border-radius:8px; padding:0.4rem 0.8rem; font-size:0.85rem; font-weight:600; cursor:pointer; color:#334155; font-family:Inter, sans-serif;">
            🖨️ Print / Save as PDF
        </button>
    """
    if hasattr(st, "iframe"):
        st.iframe(print_button_html, height=45)
    else:
        components.html(print_button_html, height=45)
