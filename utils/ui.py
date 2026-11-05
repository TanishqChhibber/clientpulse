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


@st.cache_data(ttl=30, show_spinner=False)
def _branding_cached() -> Dict[str, Any]:
    from database import get_branding
    return get_branding()


def get_branding() -> Dict[str, Any]:
    """Agency white-label settings; cached briefly so every page render does not hit the database."""
    try:
        return _branding_cached()
    except Exception:
        from database import BRANDING_DEFAULTS
        return dict(BRANDING_DEFAULTS)


def clear_branding_cache() -> None:
    _branding_cached.clear()


def render_html(markup: str) -> None:
    """
    Render an HTML block via st.markdown without Markdown misreading it.
    Strips indentation and blank lines: a blank line (e.g. from an empty optional field)
    followed by indented HTML would otherwise be displayed as a raw code block.
    """
    compact = "\n".join(line.strip() for line in markup.splitlines() if line.strip())
    st.markdown(compact, unsafe_allow_html=True)


def apply_custom_theme():
    """Inject premium Purple/Indigo SaaS design styles into the Streamlit session."""
    brand = get_branding().get("brand_color") or "#4F46E5"
    st.markdown(
        f"""<style>
        div.stButton > button[kind="primary"], div.stDownloadButton > button[kind="primary"],
        div.stFormSubmitButton > button {{ background-color: {brand} !important; border-color: {brand} !important; }}
        .stApp a {{ color: {brand}; }}
        </style>""",
        unsafe_allow_html=True,
    )
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

        /* ================= Dashboard (mockup-style) ================= */
        .stApp { background: #F4F6FB; }
        /* Bordered chart cards are keyed "cp_card_*" so only they get the white card style */
        [class*="st-key-cp_card"] { background: #FFFFFF; border-radius: 14px !important; border-color: #E5E7F0 !important;
                                    box-shadow: 0 1px 2px rgba(16,24,40,0.04); }

        /* Dark navy sidebar */
        section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0B1530 0%, #12204A 100%); border-right: none; }
        section[data-testid="stSidebar"] * { color: #CBD5E1; }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a { border-radius: 10px; }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover { background: rgba(255,255,255,0.06); }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] { background: rgba(99,102,241,0.22); border: 1px solid rgba(129,140,248,0.45); }
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] span { color: #FFFFFF; font-weight: 600; }
        .sidebar-brand-box { border-bottom: 1px solid rgba(255,255,255,0.08); }
        .sidebar-brand-title, .sidebar-brand-title span { color: #FFFFFF !important; }
        .sidebar-brand-tag { color: #8EA0C4 !important; text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.65rem !important; }
        .cp-side-heading { font-size: 0.68rem; letter-spacing: 0.12em; text-transform: uppercase; color: #6B7FA8 !important; margin: 1rem 0 0.4rem 0.2rem; font-weight: 700; }
        section[data-testid="stSidebar"] div.stButton > button {
            background: rgba(255,255,255,0.04) !important; border: 1px solid rgba(255,255,255,0.08) !important;
            color: #E2E8F0 !important; justify-content: flex-start; font-weight: 500; padding: 0.5rem 0.75rem;
        }
        section[data-testid="stSidebar"] div.stButton > button > div { justify-content: flex-start; width: 100%; }
        section[data-testid="stSidebar"] div.stButton > button:hover { background: rgba(99,102,241,0.25) !important; box-shadow: none; }
        section[data-testid="stSidebar"] div.stButton > button p { color: #E2E8F0 !important; }

        /* Header */
        .cp-crumbs { font-size: 0.85rem; color: #94A3B8; margin-bottom: 0.15rem; }
        .cp-crumbs b { color: #1E1B4B; }
        .cp-dash-title { font-size: 1.55rem; font-weight: 800; color: #1E1B4B; letter-spacing: -0.02em; margin: 0; }

        /* KPI cards */
        .cp-kpi { background: #FFFFFF; border: 1px solid #E5E7F0; border-radius: 14px; padding: 1rem 1.1rem 0.9rem;
                  position: relative; overflow: hidden; box-shadow: 0 1px 2px rgba(16,24,40,0.04); margin-bottom: 0.75rem; }
        .cp-kpi::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
                          background: linear-gradient(90deg, var(--accent), rgba(255,255,255,0.4)); }
        .cp-kpi-label { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #64748B; }
        .cp-kpi-value { font-size: 1.85rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.25; margin-top: 0.2rem; }
        .cp-kpi-bar { height: 6px; background: #EEF0F6; border-radius: 99px; margin: 0.55rem 0 0.5rem; overflow: hidden; }
        .cp-kpi-bar span { display: block; height: 100%; background: var(--accent); border-radius: 99px; }
        .cp-kpi-delta { font-size: 0.8rem; font-weight: 700; }

        /* Panels */
        .cp-panel { background: #FFFFFF; border: 1px solid #E5E7F0; border-radius: 14px; padding: 1rem 1.1rem;
                    min-height: 205px; margin-bottom: 0.75rem; box-shadow: 0 1px 2px rgba(16,24,40,0.04); }
        .cp-panel-title { font-size: 0.98rem; font-weight: 700; color: #1E1B4B; display: flex; align-items: center; gap: 0.45rem; }
        .cp-panel-sub { font-size: 0.75rem; color: #94A3B8; margin-bottom: 0.35rem; }
        .cp-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        /* Bar rows: name + value on one line, full-width bar underneath (fits narrow panels) */
        .cp-bar-row { display: grid; grid-template-columns: 1fr auto; grid-template-areas: "name val" "track track";
                      column-gap: 0.6rem; row-gap: 0.3rem; margin-top: 0.75rem; font-size: 0.8rem; }
        .cp-bar-row .cp-bar-name { grid-area: name; }
        .cp-bar-row .cp-bar-val { grid-area: val; }
        .cp-bar-row .cp-bar-track { grid-area: track; }
        .cp-spark-row { display: grid; grid-template-columns: 3.2rem 1fr 3.2rem; align-items: center; gap: 0.5rem; margin-top: 0.7rem; font-size: 0.8rem; }
        .cp-spark-row svg { width: 100%; height: 30px; }
        .cp-bar-name { color: #475569; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .cp-bar-track { height: 9px; background: #EEF0F6; border-radius: 99px; overflow: hidden; }
        .cp-bar-track span { display: block; height: 100%; border-radius: 99px; }
        .cp-bar-val { font-weight: 700; color: #1E1B4B; text-align: right; white-space: nowrap; }
        .cp-bar-val em { font-style: normal; font-weight: 600; color: #94A3B8; margin-left: 0.35rem; font-size: 0.72rem; }
        .cp-spark-val { font-weight: 700; text-align: right; min-width: 3rem; }
        .cp-empty { color: #94A3B8; font-size: 0.82rem; padding: 0.8rem 0; }
        .cp-chip { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 99px; font-size: 0.72rem; font-weight: 700; }
        .cp-prose { margin: 0.5rem 0 0; font-size: 0.9rem; line-height: 1.65; color: #334155; white-space: pre-line; }

        /* Tables */
        .cp-table-wrap { overflow-x: auto; background: #FFFFFF; border: 1px solid #E5E7F0; border-radius: 14px; margin-bottom: 0.75rem; }
        .cp-table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
        .cp-table th { text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: #64748B;
                       background: #F8FAFC; padding: 0.6rem 0.8rem; border-bottom: 1px solid #E5E7F0; white-space: nowrap; }
        .cp-table td { padding: 0.6rem 0.8rem; border-bottom: 1px solid #F1F5F9; color: #334155; white-space: nowrap; }
        .cp-table td.cp-note { white-space: normal; min-width: 14rem; color: #64748B; }
        .cp-table tr:last-child td { border-bottom: none; }
        .cp-sub { font-size: 0.72rem; color: #94A3B8; }
        .cp-mini-track { display: inline-block; width: 46px; height: 6px; background: #EEF0F6; border-radius: 99px; vertical-align: middle; overflow: hidden; }
        .cp-mini-track span { display: block; height: 100%; background: #8B5CF6; }

        /* Claude's insights panel */
        .cp-assistant { background: #FFFFFF; border: 1px solid #E5E7F0; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 14px rgba(15,23,42,0.06); }
        .cp-assistant-head { background: linear-gradient(135deg, #0B1530, #1E2A5A); padding: 0.9rem 1rem; display: flex; align-items: center; gap: 0.7rem; }
        .cp-assistant-icon { width: 34px; height: 34px; border-radius: 10px; background: linear-gradient(135deg, #D97757, #F2A27E);
                             display: flex; align-items: center; justify-content: center; color: #FFFFFF; font-size: 1.1rem; font-weight: 800; }
        .cp-assistant-title { color: #FFFFFF; font-weight: 700; font-size: 0.95rem; }
        .cp-assistant-sub { color: #94A3B8; font-size: 0.72rem; }
        .cp-live { margin-left: auto; font-size: 0.7rem; color: #34D399; background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.35); padding: 0.15rem 0.55rem; border-radius: 99px; }
        .cp-assistant-body { padding: 0.9rem 1rem 1rem; }
        .cp-context { font-size: 0.75rem; color: #64748B; margin-bottom: 0.7rem; display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
        .cp-insight { display: flex; gap: 0.5rem; align-items: flex-start; border: 1px solid; border-radius: 10px; padding: 0.55rem 0.7rem;
                      font-size: 0.8rem; color: #1E293B; line-height: 1.45; margin-bottom: 0.5rem; }
        .cp-insight .cp-dot { margin-top: 0.4rem; }
        .cp-insight-impact { margin-left: auto; font-weight: 800; white-space: nowrap; padding-left: 0.4rem; }
        .cp-mini-bars { display: flex; align-items: flex-end; gap: 6px; height: 70px; margin: 0.8rem 0 0.2rem; padding: 0.5rem; background: #F8FAFC; border-radius: 10px; }
        .cp-mini-bars span { flex: 1; background: #4F46E5; border-radius: 4px 4px 0 0; }
        .cp-ask { font-size: 0.72rem; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.9rem; }
        .cp-suggest { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.45rem; }
        .cp-suggest span { font-size: 0.74rem; color: #4338CA; background: #EEF2FF; border: 1px solid #C7D2FE; padding: 0.25rem 0.6rem; border-radius: 99px; }

        /* Tapered conversion funnel */
        .cp-funnel { display: flex; flex-direction: column; align-items: center; margin-top: 0.6rem; }
        .cp-fstage { display: flex; justify-content: space-between; align-items: center; color: #FFFFFF;
                     padding: 0.42rem 0.8rem; border-radius: 10px; box-shadow: 0 2px 6px rgba(79,70,229,0.18);
                     font-size: 0.8rem; min-width: 8.5rem; }
        .cp-fname { font-weight: 600; opacity: 0.92; }
        .cp-fvalue { font-weight: 800; font-size: 0.95rem; margin-left: 0.5rem; }
        .cp-fcost { font-size: 0.68rem; color: #94A3B8; font-weight: 600; margin-top: 0.15rem; }
        .cp-fstep { font-size: 0.72rem; color: #475569; margin: 0.15rem 0 0.3rem; text-align: center; }
        .cp-fstep b { color: #1E1B4B; }
        .cp-fstep span { font-weight: 700; margin-left: 0.25rem; }

        .cp-source { background: #F0FDF4; border: 1px solid #BBF7D0; color: #14532D; border-radius: 12px;
                     padding: 0.6rem 0.9rem; font-size: 0.83rem; margin: 0.2rem 0 0.6rem; }
        .cp-source code { background: #DCFCE7; color: #14532D; }
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

    brand = get_branding()
    logo_block = (f'<div style="margin-bottom:0.55rem;"><img src="{brand["logo_data_uri"]}" '
                  f'style="max-height:44px; max-width:200px; object-fit:contain; background:#FFFFFF; border-radius:8px; padding:4px 8px;"></div>'
                  if brand.get("logo_data_uri") else "")
    icon = "" if brand.get("logo_data_uri") else "⚡"
    st.sidebar.markdown(
        f"""
        <div class="sidebar-brand-box">
            {logo_block}
            <div class="sidebar-brand-title">
                {icon}<span>{esc(brand["agency_name"])}</span>
            </div>
            <div class="sidebar-brand-tag">{esc(brand["agency_tagline"])}</div>
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
