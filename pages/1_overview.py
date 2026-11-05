"""
ClientPulse - Overview Dashboard
================================
Presents high-level agency KPIs, reporting metrics, interactive Plotly
analytics charts, and recent activity log.
"""

import os

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

import database
from utils.ui import apply_custom_theme, render_header, render_metric_card, get_plotly_layout, esc

apply_custom_theme()

render_header(
    title="Overview Dashboard",
    subtitle="Real-time agency performance metrics, report analytics, and client activity.",
    badge_text="Live Monitoring",
    badge_type="active"
)

# Fetch latest metrics and records
metrics = database.get_dashboard_metrics()
clients = database.get_clients()
reports = database.get_reports()
activity = database.get_recent_activity(8)

# ------------------------------------------------------------------------------
# 1. Top-Level Metric Cards
# ------------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    render_metric_card(
        label="Total Clients",
        value=str(metrics["total_clients"]),
        delta=f"{metrics['active_clients']} Active",
        delta_type="positive" if metrics["active_clients"] > 0 else "neutral"
    )

with col2:
    render_metric_card(
        label="Total Reports",
        value=str(metrics["total_reports"]),
        delta=f"{metrics['published_reports']} Published / {metrics['draft_reports']} Draft",
        delta_type="neutral"
    )

with col3:
    render_metric_card(
        label="Total Ad Spend Managed",
        value=f"${metrics['total_spend']:,.2f}",
        delta=f"{metrics['total_leads']:,} Leads Generated",
        delta_type="positive"
    )

with col4:
    render_metric_card(
        label="Blended Performance",
        value=f"${metrics['avg_cpl']:.2f} CPL",
        delta=f"{metrics['avg_ctr']:.2f}% Avg CTR",
        delta_type="positive" if metrics["avg_cpl"] > 0 and metrics["avg_cpl"] < 50 else "neutral"
    )

st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# 2. Interactive Plotly Reporting Analytics Charts
# ------------------------------------------------------------------------------
chart_col1, chart_col2 = st.columns([3, 2])

with chart_col1:
    st.markdown("##### 📈 Campaign Ad Spend vs. Leads Generated")
    if reports:
        # Group spend and leads by client
        df_reports = pd.DataFrame(reports)
        # Aggregate by client
        agg = df_reports.groupby("client_name").agg({
            "spend": "sum",
            "leads": "sum",
            "impressions": "sum",
            "clicks": "sum"
        }).reset_index()

        fig = go.Figure()
        # Bar for Spend
        fig.add_trace(go.Bar(
            name="Ad Spend ($)",
            x=agg["client_name"],
            y=agg["spend"],
            marker_color="#6366F1",
            text=[f"${v:,.0f}" for v in agg["spend"]],
            textposition="auto",
            yaxis="y"
        ))
        # Line / Scatter for Leads on secondary axis
        fig.add_trace(go.Scatter(
            name="Leads Generated",
            x=agg["client_name"],
            y=agg["leads"],
            mode="lines+markers+text",
            text=agg["leads"],
            textposition="top center",
            marker=dict(color="#10B981", size=10),
            line=dict(color="#10B981", width=3),
            yaxis="y2"
        ))

        layout = get_plotly_layout("", height=360)
        layout["yaxis"] = dict(
            title="Spend ($)",
            gridcolor="#F1F5F9",
            zerolinecolor="#E2E8F0"
        )
        layout["yaxis2"] = dict(
            title="Leads",
            overlaying="y",
            side="right",
            gridcolor="rgba(0,0,0,0)",
            zeroline=False
        )
        fig.update_layout(layout)
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No campaign reports available yet to chart. Seed demo data or create a report.")

with chart_col2:
    st.markdown("##### 🎯 Report Status Breakdown")
    if reports:
        status_counts = {"Published": metrics["published_reports"], "Draft": metrics["draft_reports"]}
        fig_donut = go.Figure(data=[go.Pie(
            labels=list(status_counts.keys()),
            values=list(status_counts.values()),
            hole=0.6,
            marker_colors=["#10B981", "#F59E0B"],
            textinfo="label+value",
            showlegend=True
        )])
        donut_layout = get_plotly_layout("", height=360)
        donut_layout["margin"] = {"l": 10, "r": 10, "t": 20, "b": 20}
        fig_donut.update_layout(donut_layout)
        st.plotly_chart(fig_donut, width="stretch")
    else:
        st.info("No report data available.")

# ------------------------------------------------------------------------------
# 3. Recent Activity Feed & Quick Actions
# ------------------------------------------------------------------------------
feed_col, action_col = st.columns([3, 2])

with feed_col:
    st.markdown("##### ⚡ Recent Agency Activity")
    if activity:
        for act in activity:
            action_type = act.get("action", "")
            icon = "📝"
            if "client" in action_type:
                icon = "👥"
            elif "publish" in action_type:
                icon = "🌐"
            elif "seed" in action_type:
                icon = "🌱"
            elif "delete" in action_type:
                icon = "🗑️"

            created_time = str(act.get("created_at") or "")[:19].replace("T", " ")
            st.markdown(
                f"""
                <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:0.75rem 1rem; margin-bottom:0.5rem; display:flex; justify-content:space-between; align-items:center;">
                    <div style="display:flex; align-items:center; gap:0.75rem;">
                        <span style="font-size:1.2rem;">{icon}</span>
                        <div>
                            <div style="font-size:0.9rem; font-weight:600; color:#1E1B4B;">{esc(act.get('details'))}</div>
                            <div style="font-size:0.75rem; color:#64748B;">Action: <code>{esc(act.get('action'))}</code> • Target: <code>{esc(act.get('entity_id'))}</code></div>
                        </div>
                    </div>
                    <div style="font-size:0.75rem; color:#94A3B8; white-space:nowrap;">{created_time}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
    else:
        st.markdown("<p style='color:#64748B;'>No activity logged yet.</p>", unsafe_allow_html=True)

with action_col:
    st.markdown("##### 🛠️ Quick Actions")
    st.markdown(
        """
        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:1.25rem;">
            <p style="font-size:0.85rem; color:#475569; margin-bottom:1rem;">
                Manage your agency workflows, seed sample marketing clients, or connect Claude via MCP.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.write("")

    with st.popover("🌱 Seed / Reset Realistic Demo Data", width="stretch"):
        st.warning("This **deletes all clients, reports, and activity** and replaces them with demo data.")
        confirm_reset = st.checkbox("I understand all existing data will be erased", key="confirm_seed_reset")
        if st.button("Reset & Seed Demo Data", disabled=not confirm_reset, type="primary"):
            res = database.seed_demo_data(force=True)
            st.toast(res["message"], icon="✅")
            st.rerun()

    st.markdown(
        f"""
        <div style="margin-top:1rem; font-size:0.8rem; color:#64748B;">
            <strong>MCP Server:</strong> Streamable HTTP endpoint at <code>http://localhost:{esc(os.getenv("MCP_PORT", "8000"))}/mcp</code>
            (start it with <code>python run.py mcp</code>).<br>
            Claude can create clients and reports automatically.
        </div>
        """,
        unsafe_allow_html=True
    )
