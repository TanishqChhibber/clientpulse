"""
ClientPulse - Report History & Archive
======================================
Search, filter, inspect, compare, and manage historical campaign reports.
"""

import streamlit as st
import pandas as pd
import database
from utils.ui import apply_custom_theme, render_header, esc, build_period_comparison_chart

apply_custom_theme()

render_header(
    title="Report History & Archive",
    subtitle="Search historical campaign reports, compare performance periods, and share client links.",
    badge_text="Archive",
    badge_type="active"
)

tab_list, tab_compare = st.tabs(["📂 All Reports", "⚖️ Period Comparison"])

# ------------------------------------------------------------------------------
# TAB 1: Search & List All Reports
# ------------------------------------------------------------------------------
with tab_list:
    fcol1, fcol2, fcol3 = st.columns([2, 1, 1])

    with fcol1:
        search_query = st.text_input("🔍 Search Reports", placeholder="Search by title, client, or summary...")

    with fcol2:
        all_clients = database.get_clients()
        client_options = {"all": "All Clients"}
        for c in all_clients:
            client_options[c["id"]] = c["name"]
        selected_client = st.selectbox(
            "Filter Client",
            options=list(client_options.keys()),
            format_func=lambda x: client_options[x]
        )

    with fcol3:
        status_filter = st.selectbox("Status Filter", ["all", "published", "draft"])

    reports = database.get_reports(
        client_id=selected_client if selected_client != "all" else None,
        status=status_filter if status_filter != "all" else None,
        search=search_query
    )

    if not reports:
        st.info("No reports found matching the criteria.")
    else:
        st.markdown(f"**Found {len(reports)} Report{'s' if len(reports) != 1 else ''}:**")
        for rep in reports:
            rid = rep["id"]
            rtitle = rep["title"]
            rclient = rep.get("client_name", "Unknown Client")
            rstatus = rep.get("status", "draft")
            safe_title = esc(rtitle)
            safe_client = esc(rclient)
            safe_status = esc(rstatus)
            safe_id = esc(rid)
            safe_start = esc(rep["period_start"])
            safe_end = esc(rep["period_end"])
            rspend = float(rep.get("spend", 0.0))
            rleads = int(rep.get("leads", 0))
            rctr = float(rep.get("ctr", 0.0))
            rcpl = float(rep.get("cpl", 0.0))
            token = rep.get("share_token", "")
            share_url = f"{database.PUBLIC_APP_URL}/?page=public&token={token}"

            badge_bg = "#ECFDF5" if rstatus == "published" else "#FFFBEB"
            badge_color = "#065F46" if rstatus == "published" else "#92400E"

            with st.container():
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:1.25rem; margin-bottom:1rem; box-shadow:0 1px 3px rgba(0,0,0,0.02);">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                            <div>
                                <div style="display:flex; align-items:center; gap:0.5rem;">
                                    <div style="margin:0; font-size:1.15rem; color:#1E1B4B; font-weight:700;">{safe_title}</div>
                                    <span style="background:{badge_bg}; color:{badge_color}; padding:0.2rem 0.55rem; border-radius:9999px; font-size:0.7rem; font-weight:700; text-transform:uppercase;">
                                        {safe_status}
                                    </span>
                                </div>
                                <div style="font-size:0.85rem; color:#6366F1; font-weight:600; margin-top:0.25rem;">
                                    Client: {safe_client} &nbsp;|&nbsp; Period: {safe_start} to {safe_end}
                                </div>
                                <div style="font-size:0.85rem; color:#475569; margin-top:0.4rem;">
                                    Spend: <strong>${rspend:,.2f}</strong> &nbsp;•&nbsp; 
                                    Leads: <strong>{rleads:,}</strong> &nbsp;•&nbsp; 
                                    CPL: <strong>${rcpl:.2f}</strong> &nbsp;•&nbsp; 
                                    CTR: <strong>{rctr:.2f}%</strong>
                                </div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:0.75rem; color:#94A3B8;">ID: <code>{safe_id}</code></div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Report Action Buttons
                bcol0, bcol1, bcol2, bcol3, bcol4 = st.columns([1.1, 1.2, 1.2, 1.5, 0.8])
                with bcol0:
                    if st.button("📊 Dashboard", key=f"dash_btn_{rid}"):
                        st.session_state["dashboard_report_id"] = rid
                        st.switch_page("pages/0_dashboard.py")
                with bcol1:
                    if st.button("✏️ Edit in Builder", key=f"edit_btn_{rid}"):
                        st.session_state["edit_report_id"] = rid
                        st.switch_page("pages/3_create_report.py")

                with bcol2:
                    if rstatus == "draft":
                        if st.button("🚀 Publish Now", key=f"pub_btn_{rid}"):
                            database.publish_report(rid)
                            st.toast("Report published!", icon="🌐")
                            st.rerun()
                    else:
                        if st.button("📥 Revert to Draft", key=f"draft_btn_{rid}"):
                            database.update_report(rid, status="draft")
                            st.toast("Reverted report to draft.", icon="ℹ️")
                            st.rerun()

                with bcol3:
                    if rstatus == "published":
                        st.link_button("🌐 Open Public View", url=share_url, width="stretch")
                    else:
                        st.caption("🔒 Publish to enable public URL")

                with bcol4:
                    with st.popover("🗑️ Delete"):
                        st.write(f"Delete **{rtitle}**?")
                        if st.button("Confirm", key=f"del_confirm_{rid}", type="primary"):
                            database.delete_report(rid)
                            st.toast("Report deleted.", icon="🗑️")
                            st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: Period Comparison
# ------------------------------------------------------------------------------
with tab_compare:
    st.markdown("##### ⚖️ Historical Period Comparison")
    all_reps = database.get_reports()
    if len(all_reps) < 2:
        st.info("At least two reports are required to compare performance periods.")
    else:
        def short_title(title: str, limit: int = 20) -> str:
            return title if len(title) <= limit else f"{title[:limit]}..."

        rep_dict = {r["id"]: f"{r['title']} ({r['client_name']}) - {r['period_start']}" for r in all_reps}

        ccol1, ccol2 = st.columns(2)
        with ccol1:
            rep_a_id = st.selectbox("Select Baseline Report (Period A)", options=list(rep_dict.keys()), format_func=lambda x: rep_dict[x], index=0)
        with ccol2:
            rep_b_id = st.selectbox("Select Target Report (Period B)", options=list(rep_dict.keys()), format_func=lambda x: rep_dict[x], index=1)

        if rep_a_id == rep_b_id:
            st.warning("Select two different reports to compare.")
            rep_a = rep_b = None
        else:
            rep_a = database.get_report_by_id(rep_a_id)
            rep_b = database.get_report_by_id(rep_b_id)

        if rep_a and rep_b:
            # Metrics comparison table
            comp_data = {
                "Metric": ["Ad Spend ($)", "Impressions", "Clicks", "Leads / Conversions", "CTR (%)", "Cost Per Lead ($)", "Conversion Rate (%)"],
                f"Period A ({short_title(rep_a['title'])})": [
                    f"${rep_a['spend']:,.2f}",
                    f"{rep_a['impressions']:,}",
                    f"{rep_a['clicks']:,}",
                    f"{rep_a['leads']:,}",
                    f"{rep_a['ctr']:.2f}%",
                    f"${rep_a['cpl']:.2f}",
                    f"{rep_a['conversion_rate']:.2f}%"
                ],
                f"Period B ({short_title(rep_b['title'])})": [
                    f"${rep_b['spend']:,.2f}",
                    f"{rep_b['impressions']:,}",
                    f"{rep_b['clicks']:,}",
                    f"{rep_b['leads']:,}",
                    f"{rep_b['ctr']:.2f}%",
                    f"${rep_b['cpl']:.2f}",
                    f"{rep_b['conversion_rate']:.2f}%"
                ]
            }
            df_comp = pd.DataFrame(comp_data)
            st.dataframe(df_comp, width="stretch", hide_index=True)

            # Chart comparison: one panel per metric so each uses its own true scale
            fig_comp = build_period_comparison_chart(
                [("Period A", rep_a, "#6366F1"), ("Period B", rep_b, "#10B981")],
                title="Period A vs Period B Comparison"
            )
            st.plotly_chart(fig_comp, width="stretch")
