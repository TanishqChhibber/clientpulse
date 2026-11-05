"""
ClientPulse - Report Management
===============================
Create, edit, recalculate, and save digital marketing performance reports
with real-time CTR, CPL, and previous period delta comparisons.
"""

import streamlit as st
from datetime import date, timedelta
import database
from utils.ui import apply_custom_theme, render_header

apply_custom_theme()

# Check if editing a specific report passed via session state or query params
editing_report_id = st.session_state.get("edit_report_id", None)
query_report_id = st.query_params.get("edit_id", None)
if query_report_id:
    editing_report_id = query_report_id

render_header(
    title="Report Management" if not editing_report_id else "Edit Marketing Report",
    subtitle="Generate comprehensive marketing performance reports with automated ROI metrics.",
    badge_text="Report Builder" if not editing_report_id else "Edit Mode",
    badge_type="active"
)

# Fetch all clients
clients = database.get_clients(status="all")
if not clients:
    st.warning("⚠️ No clients found in database. Please register a client in Client Management or seed demo data first.")
    st.stop()

client_map = {c["id"]: f"{c['name']} ({c.get('industry') or 'General'})" for c in clients}

# Option to toggle between Create New vs Edit Existing
mode = "Create New Report"
if editing_report_id:
    mode = "Edit Existing Report"

mode_choice = st.radio(
    "Report Action",
    ["Create New Report", "Edit Existing Report"],
    index=0 if not editing_report_id else 1,
    horizontal=True
)

current_report = None
if mode_choice == "Edit Existing Report":
    all_reports = database.get_reports()
    if not all_reports:
        st.info("No existing reports found to edit.")
        st.stop()
    
    rep_options = {r["id"]: f"{r['title']} - {r['client_name']} ({r['status']})" for r in all_reports}
    default_idx = 0
    if editing_report_id and editing_report_id in rep_options:
        default_idx = list(rep_options.keys()).index(editing_report_id)

    selected_rep_id = st.selectbox(
        "Select Report to Edit",
        options=list(rep_options.keys()),
        index=default_idx,
        format_func=lambda x: rep_options[x]
    )
    current_report = database.get_report_by_id(selected_rep_id)

# ------------------------------------------------------------------------------
# Report Form Fields Pre-fill
# ------------------------------------------------------------------------------
default_client_id = current_report["client_id"] if current_report else list(client_map.keys())[0]
default_title = current_report["title"] if current_report else "Q3 2026 Growth & Acquisition Performance Report"
default_start = date.fromisoformat(current_report["period_start"]) if current_report else date.today() - timedelta(days=30)
default_end = date.fromisoformat(current_report["period_end"]) if current_report else date.today()

default_imp = int(current_report["impressions"]) if current_report else 250000
default_clicks = int(current_report["clicks"]) if current_report else 8500
default_leads = int(current_report["leads"]) if current_report else 420
default_spend = float(current_report["spend"]) if current_report else 12500.00

default_prev_imp = int(current_report["prev_impressions"]) if current_report else 210000
default_prev_clicks = int(current_report["prev_clicks"]) if current_report else 6800
default_prev_leads = int(current_report["prev_leads"]) if current_report else 310
default_prev_spend = float(current_report["prev_spend"]) if current_report else 10500.00

default_summary = (current_report["summary"] or "") if current_report else (
    "Campaign performance over this reporting period demonstrated positive momentum across Google Search and Meta Ads. "
    "Ad spend optimization reduced overall cost per lead while increasing qualified pipeline conversion."
)
default_recommendations = (current_report["recommendations"] or "") if current_report else (
    "1. Allocate 15% more budget towards the top performing search keyword ad groups.\n"
    "2. Refresh ad creatives on paid social with high-converting short-form video.\n"
    "3. A/B test landing page lead forms to reduce bounce rates."
)
default_status = current_report["status"] if current_report else "draft"

# ------------------------------------------------------------------------------
# Input Form
# ------------------------------------------------------------------------------
st.markdown("#### 1. Campaign Details")
client_col, title_col = st.columns([1, 2])
with client_col:
    selected_client_id = st.selectbox(
        "Client *",
        options=list(client_map.keys()),
        index=list(client_map.keys()).index(default_client_id) if default_client_id in client_map else 0,
        format_func=lambda x: client_map[x],
        # A report's client cannot be changed after creation (update_report does not move reports)
        disabled=bool(current_report),
        help="The client is fixed once a report is created." if current_report else None
    )
with title_col:
    report_title = st.text_input("Report Title *", value=default_title)

date_col1, date_col2 = st.columns(2)
with date_col1:
    period_start = st.date_input("Reporting Period Start", value=default_start)
with date_col2:
    period_end = st.date_input("Reporting Period End", value=default_end)

st.markdown("---")
st.markdown("#### 2. Performance Metrics & Previous Period Comparison")

mcol1, mcol2 = st.columns(2)

with mcol1:
    st.markdown("##### 📌 Current Period Metrics")
    inp_spend = st.number_input("Ad Spend ($) *", min_value=0.0, value=default_spend, step=500.0, format="%.2f")
    inp_imp = st.number_input("Impressions *", min_value=0, value=default_imp, step=1000)
    inp_clicks = st.number_input("Clicks *", min_value=0, value=default_clicks, step=100)
    inp_leads = st.number_input("Leads / Conversions *", min_value=0, value=default_leads, step=10)

with mcol2:
    st.markdown("##### ⏳ Previous Period Comparison (Benchmark)")
    inp_prev_spend = st.number_input("Previous Ad Spend ($)", min_value=0.0, value=default_prev_spend, step=500.0, format="%.2f")
    inp_prev_imp = st.number_input("Previous Impressions", min_value=0, value=default_prev_imp, step=1000)
    inp_prev_clicks = st.number_input("Previous Clicks", min_value=0, value=default_prev_clicks, step=100)
    inp_prev_leads = st.number_input("Previous Leads / Conversions", min_value=0, value=default_prev_leads, step=10)

# Calculate live preview metrics
calc_ctr = (inp_clicks / inp_imp * 100) if inp_imp > 0 else 0.0
calc_cpl = (inp_spend / inp_leads) if inp_leads > 0 else 0.0
calc_cvr = (inp_leads / inp_clicks * 100) if inp_clicks > 0 else 0.0

prev_ctr = (inp_prev_clicks / inp_prev_imp * 100) if inp_prev_imp > 0 else 0.0
prev_cpl = (inp_prev_spend / inp_prev_leads) if inp_prev_leads > 0 else 0.0

# Deltas
delta_spend = ((inp_spend - inp_prev_spend) / inp_prev_spend * 100) if inp_prev_spend > 0 else 0.0
delta_leads = ((inp_leads - inp_prev_leads) / inp_prev_leads * 100) if inp_prev_leads > 0 else 0.0
delta_cpl = ((calc_cpl - prev_cpl) / prev_cpl * 100) if prev_cpl > 0 else 0.0
delta_ctr = ((calc_ctr - prev_ctr) / prev_ctr * 100) if prev_ctr > 0 else 0.0

st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
st.markdown("##### ⚡ Live Real-Time Derived Metrics")

rcol1, rcol2, rcol3, rcol4 = st.columns(4)
rcol1.metric("Click-Through Rate (CTR)", f"{calc_ctr:.2f}%", f"{delta_ctr:+.1f}% vs prev", delta_color="normal")
rcol2.metric("Cost Per Lead (CPL)", f"${calc_cpl:.2f}", f"{delta_cpl:+.1f}% vs prev", delta_color="inverse")
rcol3.metric("Lead Volume", f"{inp_leads:,}", f"{delta_leads:+.1f}% vs prev", delta_color="normal")
rcol4.metric("Conversion Rate", f"{calc_cvr:.2f}%")

if inp_clicks > inp_imp:
    st.warning("Clicks exceed impressions, so CTR will be above 100%. Double-check the numbers.")
if inp_prev_clicks > inp_prev_imp:
    st.warning("Previous-period clicks exceed previous impressions. Double-check the benchmark numbers.")

st.markdown("---")
st.markdown("#### 3. Strategic Analysis & Action Items")

inp_summary = st.text_area(
    "Executive Performance Summary *",
    value=default_summary,
    height=140,
    help="High-level overview explaining key results, campaign wins, and channel performance."
)

inp_recommendations = st.text_area(
    "Strategic Recommendations *",
    value=default_recommendations,
    height=140,
    help="Actionable, strategic recommendations for the client's upcoming campaigns."
)

st.markdown("#### 4. Publishing & Visibility")
pub_col1, pub_col2 = st.columns([1, 2])
with pub_col1:
    inp_status = st.selectbox(
        "Report Status",
        ["draft", "published"],
        index=0 if default_status == "draft" else 1,
        help="Published reports generate a live public URL accessible by the client."
    )

with pub_col2:
    if inp_status == "published":
        st.info("🌐 Setting to **Published** will allow anyone with the generated public link to view this report without logging in.")

st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

# Save Button
button_label = "💾 Save Changes to Report" if current_report else "🚀 Generate & Save Report"

def show_public_link(share_token: str):
    pub_url = f"{database.PUBLIC_APP_URL}/?page=public&token={share_token}"
    st.markdown(f"**Public Client Share Link:** [{pub_url}]({pub_url})")


if st.button(button_label, width="stretch"):
    if not report_title.strip():
        st.error("Report Title is required.")
    elif period_end < period_start:
        st.error("Period End date cannot be before Period Start date.")
    else:
        report_fields = dict(
            title=report_title,
            period_start=str(period_start),
            period_end=str(period_end),
            impressions=inp_imp,
            clicks=inp_clicks,
            leads=inp_leads,
            spend=inp_spend,
            prev_impressions=inp_prev_imp,
            prev_clicks=inp_prev_clicks,
            prev_leads=inp_prev_leads,
            prev_spend=inp_prev_spend,
            summary=inp_summary,
            recommendations=inp_recommendations,
            status=inp_status
        )
        try:
            if current_report:
                saved = database.update_report(report_id=current_report["id"], **report_fields)
                st.success(f"Report '{report_title}' updated successfully!")
                # Clear edit state
                st.session_state.pop("edit_report_id", None)
            else:
                saved = database.create_report(client_id=selected_client_id, **report_fields)
                st.success(f"Report '{report_title}' created successfully! (ID: `{saved['id']}`)")
        except ValueError as e:
            st.error(f"Could not save report: {e}")
        else:
            if saved and inp_status == "published":
                show_public_link(saved["share_token"])
