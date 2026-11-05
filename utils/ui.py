"""
ClientPulse UI Kit
==================
Consistent Purple/Indigo SaaS styling, responsive metric cards,
custom badges, and Plotly charting themes.
"""

import html
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Optional, Dict, Any


def esc(value: Any) -> str:
    """HTML-escape user-provided text before interpolating it into unsafe_allow_html markup."""
    return html.escape("" if value is None else str(value))


def apply_custom_theme():
    """Inject premium Purple/Indigo SaaS design styles into the Streamlit session."""
    st.markdown(
        """
        <style>
        /* Import Google Font Inter */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        /* Main Container Background and Padding */
        .main .block-container {
            padding-top: 1.8rem;
            padding-bottom: 3.5rem;
            max-width: 1200px;
        }

        /* Top Bar & Header Accent */
        .cp-header-wrap {
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid #E0E7FF;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .cp-title {
            font-size: 1.85rem;
            font-weight: 800;
            color: #1E1B4B;
            letter-spacing: -0.025em;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }
        .cp-subtitle {
            font-size: 0.95rem;
            color: #64748B;
            margin-top: 0.25rem;
        }

        /* Metric Cards */
        .cp-metric-card {
            background: #FFFFFF;
            border: 1px solid #E0E7FF;
            border-radius: 12px;
            padding: 1.25rem 1.4rem;
            box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.05), 0 2px 4px -2px rgba(79, 70, 229, 0.05);
            transition: all 0.2s ease-in-out;
            height: 100%;
        }
        .cp-metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.1), 0 4px 6px -4px rgba(79, 70, 229, 0.1);
            border-color: #C7D2FE;
        }
        .cp-metric-label {
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #6366F1;
            margin-bottom: 0.4rem;
        }
        .cp-metric-value {
            font-size: 1.75rem;
            font-weight: 800;
            color: #1E1B4B;
            letter-spacing: -0.02em;
            line-height: 1.2;
        }
        .cp-metric-delta {
            font-size: 0.85rem;
            font-weight: 600;
            margin-top: 0.4rem;
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }
        .cp-delta-positive {
            color: #059669;
        }
        .cp-delta-negative {
            color: #DC2626;
        }
        .cp-delta-neutral {
            color: #64748B;
        }

        /* Status Pills */
        .cp-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.65rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 9999px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .cp-badge-published {
            background-color: #ECFDF5;
            color: #065F46;
            border: 1px solid #A7F3D0;
        }
        .cp-badge-draft {
            background-color: #FFFBEB;
            color: #92400E;
            border: 1px solid #FDE68A;
        }
        .cp-badge-active {
            background-color: #EEF2FF;
            color: #3730A3;
            border: 1px solid #C7D2FE;
        }
        .cp-badge-inactive {
            background-color: #F1F5F9;
            color: #475569;
            border: 1px solid #E2E8F0;
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #FAFAFD;
            border-right: 1px solid #EDE9FE;
        }
        .sidebar-brand-box {
            padding: 1.25rem 0.5rem 1.5rem 0.5rem;
            border-bottom: 1px solid #E0E7FF;
            margin-bottom: 1.25rem;
        }
        .sidebar-brand-title {
            font-size: 1.4rem;
            font-weight: 800;
            color: #4F46E5;
            letter-spacing: -0.02em;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .sidebar-brand-tag {
            font-size: 0.75rem;
            color: #6B7280;
            font-weight: 500;
            margin-top: 0.2rem;
        }

        /* Buttons & Accent Elements */
        div.stButton > button:first-child {
            background-color: #4F46E5;
            color: #FFFFFF;
            font-weight: 600;
            border-radius: 8px;
            border: none;
            padding: 0.45rem 1rem;
            transition: all 0.15s ease-in-out;
        }
        div.stButton > button:first-child:hover {
            background-color: #4338CA;
            color: #FFFFFF;
            box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
        }

        /* Section Cards */
        .cp-section-box {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        }

        /* Public Client Facing Report Styling */
        .public-report-container {
            background: #FFFFFF;
            border: 1px solid #E0E7FF;
            border-radius: 16px;
            padding: 2.5rem;
            box-shadow: 0 12px 24px -4px rgba(79, 70, 229, 0.08);
            margin-top: 1rem;
        }
        .public-report-hero {
            border-bottom: 2px solid #EEF2FF;
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }
        .public-report-agency {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: #6366F1;
            font-weight: 700;
        }
        .public-report-title {
            font-size: 2.1rem;
            font-weight: 800;
            color: #1E1B4B;
            margin: 0.4rem 0;
            letter-spacing: -0.02em;
        }
        .public-report-meta {
            font-size: 0.95rem;
            color: #64748B;
        }
        .public-narrative-card {
            background-color: #F8FAFC;
            border-left: 4px solid #6366F1;
            border-radius: 0 8px 8px 0;
            padding: 1.25rem 1.5rem;
            margin: 1.25rem 0;
        }
        .public-recommendations-card {
            background-color: #FAF5FF;
            border-left: 4px solid #9333EA;
            border-radius: 0 8px 8px 0;
            padding: 1.25rem 1.5rem;
            margin: 1.25rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def render_header(title: str, subtitle: Optional[str] = None, badge_text: Optional[str] = None, badge_type: str = "active"):
    """Render a unified page header with title, optional subtitle and badge."""
    badge_html = f'<span class="cp-badge cp-badge-{badge_type}">{badge_text}</span>' if badge_text else ''
    subtitle_html = f'<div class="cp-subtitle">{subtitle}</div>' if subtitle else ''
    st.markdown(
        f"""
        <div class="cp-header-wrap">
            <div>
                <div class="cp-title">
                    <span>{title}</span>
                    {badge_html}
                </div>
                {subtitle_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_metric_card(
    label: str,
    value: str,
    delta: Optional[str] = None,
    delta_type: str = "neutral"
):
    """
    Render a clean SaaS metric card.
    delta_type: "positive" (green), "negative" (red), "neutral" (gray)
    """
    delta_html = ""
    if delta:
        css_class = f"cp-delta-{delta_type}"
        icon = "↑" if delta_type == "positive" else ("↓" if delta_type == "negative" else "•")
        delta_html = f'<div class="cp-metric-delta {css_class}"><span>{icon}</span> {delta}</div>'

    html = f"""
    <div class="cp-metric-card">
        <div class="cp-metric-label">{label}</div>
        <div class="cp-metric-value">{value}</div>
        {delta_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_sidebar_brand():
    """Render brand and live status in the Streamlit sidebar."""
    from database import get_db_info
    db_info = get_db_info()

    if db_info.get("supabase_unreachable"):
        st.sidebar.error(
            "Supabase is configured but unreachable, so data is being saved to a local file "
            "that the MCP server cannot see. Check SUPABASE_URL / SUPABASE_KEY and the server logs."
        )

    badge_color = "#10B981" if db_info["engine"] == "supabase" else "#8B5CF6"
    badge_label = "Supabase PostgreSQL" if db_info["engine"] == "supabase" else "Local SQLite Engine"

    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand-box">
            <div class="sidebar-brand-title">
                <span>⚡ ClientPulse</span>
            </div>
            <div class="sidebar-brand-tag">Agency Performance & Reporting Platform</div>
            <div style="margin-top: 0.75rem; display: flex; align-items: center; gap: 0.4rem; font-size: 0.75rem; color: #4B5563;">
                <span style="display:inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: {badge_color};"></span>
                <span><strong>DB:</strong> {badge_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def get_plotly_layout(title: str = "", height: int = 350) -> Dict[str, Any]:
    """Return unified Plotly layout configured with Purple/Indigo SaaS aesthetic."""
    return {
        "title": {
            "text": title,
            "font": {"family": "Inter, sans-serif", "size": 15, "color": "#1E1B4B", "weight": 700},
            "x": 0.02,
            "y": 0.95
        },
        "font": {"family": "Inter, sans-serif", "color": "#64748B"},
        "paper_bgcolor": "#FFFFFF",
        "plot_bgcolor": "#FFFFFF",
        "height": height,
        "margin": {"l": 40, "r": 20, "t": 45, "b": 40},
        "xaxis": {
            "gridcolor": "#F1F5F9",
            "zerolinecolor": "#E2E8F0",
            "tickfont": {"size": 11, "color": "#64748B"}
        },
        "yaxis": {
            "gridcolor": "#F1F5F9",
            "zerolinecolor": "#E2E8F0",
            "tickfont": {"size": 11, "color": "#64748B"}
        },
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 11}
        }
    }


COMPARISON_METRICS = [("Spend ($)", "spend"), ("Clicks", "clicks"), ("Leads", "leads")]


def build_period_comparison_chart(
    series: list,
    title: str = "",
    height: int = 320
) -> go.Figure:
    """
    Compare spend, clicks, and leads across periods with one panel per metric,
    so each metric is shown on its own true scale.
    series: list of (label, values_dict, color) where values_dict has spend/clicks/leads keys.
    """
    fig = make_subplots(rows=1, cols=len(COMPARISON_METRICS), subplot_titles=[m[0] for m in COMPARISON_METRICS])
    for col_idx, (_, key) in enumerate(COMPARISON_METRICS, start=1):
        for label, values, color in series:
            fig.add_trace(go.Bar(
                name=label, x=[label], y=[float(values.get(key) or 0)],
                marker_color=color, showlegend=col_idx == 1
            ), row=1, col=col_idx)

    layout = get_plotly_layout(title, height=height)
    axis_style = layout.pop("xaxis")
    layout.pop("yaxis")
    layout["margin"] = {"l": 40, "r": 20, "t": 80 if title else 60, "b": 40}
    fig.update_layout(layout)
    fig.update_xaxes(**axis_style, showticklabels=False)
    fig.update_yaxes(**axis_style)
    return fig
