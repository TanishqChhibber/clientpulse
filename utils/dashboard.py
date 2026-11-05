"""
ClientPulse Dashboard Components
================================
Renders the report dashboard (KPI cards, trend line, channel donut, funnel,
CPL-by-channel bars, weekly sparklines, breakdown tables, Claude's insights
panel). Every function takes plain dicts, so the same components render saved
reports and live, unsaved edits.
"""

import math
from datetime import date
from typing import Any, Dict, List, Optional

import plotly.graph_objects as go
import streamlit as st

from utils.ui import esc, get_plotly_layout, render_html

PALETTE = ["#4F46E5", "#10B981", "#8B5CF6", "#F59E0B", "#EF4444", "#0EA5E9", "#EC4899", "#64748B"]
VERDICT_STYLE = {
    "scale": ("#ECFDF5", "#047857", "Scale"),
    "keep": ("#EEF2FF", "#4338CA", "Keep"),
    "cut": ("#FEF2F2", "#B91C1C", "Cut"),
}


# ------------------------------------------------------------------------------
# Metric helpers
# ------------------------------------------------------------------------------
def num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def ratio(a: float, b: float, scale: float = 1.0) -> Optional[float]:
    return a / b * scale if b else None


def pct_change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or not prev:
        return None
    return (cur - prev) / prev * 100


def report_kpis(report: Dict[str, Any]) -> Dict[str, Any]:
    spend, leads = num(report.get("spend")), num(report.get("leads"))
    clicks, imp = num(report.get("clicks")), num(report.get("impressions"))
    p_spend, p_leads = num(report.get("prev_spend")), num(report.get("prev_leads"))
    p_clicks, p_imp = num(report.get("prev_clicks")), num(report.get("prev_impressions"))
    return {
        "spend": spend, "leads": leads, "clicks": clicks, "impressions": imp,
        "cpl": ratio(spend, leads), "ctr": ratio(clicks, imp, 100), "cvr": ratio(leads, clicks, 100),
        "prev_spend": p_spend, "prev_leads": p_leads,
        "prev_cpl": ratio(p_spend, p_leads), "prev_ctr": ratio(p_clicks, p_imp, 100),
    }


def _week_label(label: str) -> str:
    try:
        return date.fromisoformat(str(label)[:10]).strftime("%b %d").replace(" 0", " ")
    except ValueError:
        return str(label)


# ------------------------------------------------------------------------------
# KPI cards
# ------------------------------------------------------------------------------
def render_kpi_cards(report: Dict[str, Any]) -> None:
    k = report_kpis(report)
    cards = [
        ("Ad Spend", f"${k['spend']:,.0f}", pct_change(k["spend"], k["prev_spend"]), None, "#4F46E5"),
        ("Leads", f"{k['leads']:,.0f}", pct_change(k["leads"], k["prev_leads"]), True, "#10B981"),
        ("Cost per Lead", f"${k['cpl']:,.2f}" if k["cpl"] is not None else "–",
         pct_change(k["cpl"], k["prev_cpl"]), False, "#8B5CF6"),
        ("Click-Through Rate", f"{k['ctr']:.2f}%" if k["ctr"] is not None else "–",
         pct_change(k["ctr"], k["prev_ctr"]), True, "#F59E0B"),
    ]
    cols = st.columns(4)
    for col, (label, value, delta, higher_good, accent) in zip(cols, cards):
        if delta is None:
            delta_html = '<div class="cp-kpi-delta cp-delta-neutral">No previous period</div>'
            bar = 100
        else:
            good = None if higher_good is None else ((delta >= 0) == higher_good)
            cls = "cp-delta-neutral" if good is None else ("cp-delta-positive" if good else "cp-delta-negative")
            arrow = "▲" if delta >= 0 else "▼"
            delta_html = f'<div class="cp-kpi-delta {cls}">{arrow} {delta:+.1f}% vs prev</div>'
            bar = max(8, min(100, 50 + delta))
        with col:
            render_html(f"""
                <div class="cp-kpi" style="--accent:{accent};">
                    <div class="cp-kpi-label">{esc(label)}</div>
                    <div class="cp-kpi-value" style="color:{accent};">{esc(value)}</div>
                    <div class="cp-kpi-bar"><span style="width:{bar:.0f}%;"></span></div>
                    {delta_html}
                </div>
            """)


# ------------------------------------------------------------------------------
# Charts
# ------------------------------------------------------------------------------
def _panel_title(title: str, subtitle: str = "") -> None:
    sub = f'<div class="cp-panel-sub">{esc(subtitle)}</div>' if subtitle else ""
    render_html(f'<div class="cp-panel-title">{esc(title)}</div>{sub}')


def render_trend_chart(weeks: List[Dict[str, Any]], report: Dict[str, Any]) -> None:
    _panel_title("Leads vs Spend", "Weekly performance this period" if weeks else "Current vs previous period")
    if not weeks:
        k = report_kpis(report)
        fig = go.Figure()
        for name, color, vals in [("Previous", "#CBD5E1", (k["prev_leads"], k["prev_spend"])),
                                  ("Current", "#4F46E5", (k["leads"], k["spend"]))]:
            fig.add_trace(go.Bar(name=name, x=["Leads"], y=[vals[0]], marker_color=color, yaxis="y"))
        layout = get_plotly_layout("", height=290)
        layout["margin"] = {"l": 40, "r": 20, "t": 30, "b": 30}
        fig.update_layout(layout, barmode="group")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
        st.caption("Ask Claude to add weekly rows (set_report_breakdown) to see the trend line.")
        return

    x = [_week_label(w["label"]) for w in weeks]
    leads = [num(w.get("leads")) for w in weeks]
    spend = [num(w.get("spend")) for w in weeks]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=leads, name="Leads", mode="lines+markers", line=dict(color="#4F46E5", width=3, shape="spline"),
        marker=dict(size=8, color="#FFFFFF", line=dict(color="#4F46E5", width=2)),
        fill="tozeroy", fillcolor="rgba(79,70,229,0.08)",
        hovertemplate="%{x}<br><b>%{y:,.0f} leads</b><extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=x, y=spend, name="Spend ($)", mode="lines", yaxis="y2",
        line=dict(color="#10B981", width=2, dash="dash", shape="spline"),
        hovertemplate="%{x}<br><b>$%{y:,.0f}</b><extra></extra>"
    ))
    layout = get_plotly_layout("", height=290)
    layout["margin"] = {"l": 45, "r": 55, "t": 30, "b": 30}
    layout["yaxis"] = {"gridcolor": "#F1F5F9", "zeroline": False, "tickfont": {"size": 10}}
    layout["yaxis2"] = {"overlaying": "y", "side": "right", "showgrid": False, "tickprefix": "$",
                        "tickfont": {"size": 10, "color": "#10B981"}}
    layout["hovermode"] = "x unified"
    layout["xaxis"] = {"tickangle": 0, "nticks": 7, "tickfont": {"size": 10}, "showgrid": False}
    layout["legend"] = {"orientation": "h", "yanchor": "bottom", "y": 1.0, "xanchor": "right", "x": 1, "font": {"size": 11}}
    fig.update_layout(layout)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def render_channel_donut(channels: List[Dict[str, Any]]) -> None:
    _panel_title("Channel Split", "Share of ad spend")
    if not channels:
        st.caption("No channel breakdown yet. Ask Claude to add one.")
        return
    labels = [c["label"] for c in channels]
    spend = [num(c.get("spend")) for c in channels]
    fig = go.Figure(go.Pie(
        labels=labels, values=spend, hole=0.64, sort=False,
        marker=dict(colors=PALETTE[:len(labels)], line=dict(color="#FFFFFF", width=2)),
        texttemplate="%{percent:.0%}", textposition="inside", insidetextorientation="horizontal",
        insidetextfont=dict(color="#FFFFFF", size=11),
        hovertemplate="%{label}<br><b>$%{value:,.0f}</b> (%{percent})<extra></extra>"
    ))
    total = sum(spend)
    total_txt = f"${total / 1000:,.1f}K" if total >= 10000 else f"${total:,.0f}"
    fig.add_annotation(text=f"<b>{total_txt}</b><br><span style='font-size:10px;color:#94A3B8'>total</span>",
                       showarrow=False, font=dict(size=15, color="#1E1B4B"))
    layout = get_plotly_layout("", height=290)
    layout["margin"] = {"l": 10, "r": 10, "t": 20, "b": 10}
    layout["legend"] = {"orientation": "v", "x": 1.0, "y": 0.5, "font": {"size": 11}}
    layout["uniformtext"] = {"minsize": 10, "mode": "hide"}  # hide labels on slices too small to fit them
    fig.update_layout(layout)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _compact(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 100_000:
        return f"{n / 1_000:.0f}K"
    if n >= 10_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}"


def _rate_change(cur: Optional[float], prev: Optional[float]) -> str:
    """Percentage-point change chip for a conversion rate vs the previous period."""
    if cur is None or prev is None:
        return ""
    diff = cur - prev
    cls = "cp-delta-positive" if diff >= 0 else "cp-delta-negative"
    return f'<span class="{cls}">{"▲" if diff >= 0 else "▼"} {abs(diff):.2f} pts</span>'


def render_funnel(report: Dict[str, Any]) -> None:
    """Tapered funnel: each stage narrower than the last, with step conversion rates and stage costs."""
    k = report_kpis(report)
    p_clicks, p_imp = num(report.get("prev_clicks")), num(report.get("prev_impressions"))
    prev_cvr = ratio(k["prev_leads"], p_clicks, 100) if k["prev_leads"] else None
    cpm = ratio(k["spend"], k["impressions"], 1000)
    cpc = ratio(k["spend"], k["clicks"])

    stages = [
        ("Impressions", k["impressions"], f"${cpm:,.2f} CPM" if cpm is not None else "", 100,
         "linear-gradient(90deg, #4F46E5, #6366F1)"),
        ("Clicks", k["clicks"], f"${cpc:,.2f} CPC" if cpc is not None else "", 76,
         "linear-gradient(90deg, #7C3AED, #8B5CF6)"),
        ("Leads", k["leads"], f"${k['cpl']:,.2f} CPL" if k["cpl"] is not None else "", 52,
         "linear-gradient(90deg, #059669, #10B981)"),
    ]
    steps = [
        ("Click-through", k["ctr"], _rate_change(k["ctr"], k["prev_ctr"] if p_imp else None)),
        ("Click → lead", k["cvr"], _rate_change(k["cvr"], prev_cvr)),
    ]

    parts = []
    for i, (name, value, cost, width, bg) in enumerate(stages):
        parts.append(f"""
            <div class="cp-fstage" style="width:{width}%; background:{bg};">
                <span class="cp-fname">{name}</span><span class="cp-fvalue">{_compact(value)}</span>
            </div>
            <div class="cp-fcost">{cost}</div>""")
        if i < len(steps):
            label, rate, change = steps[i]
            rate_txt = f"{rate:.2f}%" if rate is not None else "–"
            parts.append(f'<div class="cp-fstep">↓ <b>{rate_txt}</b> {label} {change}</div>')

    render_html(f"""
        <div class="cp-panel">
            <div class="cp-panel-title"><span class="cp-dot" style="background:#4F46E5"></span>Conversion Funnel</div>
            <div class="cp-funnel">{''.join(parts)}</div>
        </div>
    """)


def render_cpl_by_channel(channels: List[Dict[str, Any]]) -> None:
    rows = [(c["label"], num(c.get("spend")) / num(c.get("leads"))) for c in channels if num(c.get("leads")) > 0]
    rows.sort(key=lambda r: r[1])
    body = '<div class="cp-empty">No channel breakdown yet.</div>'
    if rows:
        worst = rows[-1][1] or 1
        parts = []
        for i, (name, cpl) in enumerate(rows):
            color = "#10B981" if i == 0 else ("#EF4444" if i == len(rows) - 1 and len(rows) > 1 else "#6366F1")
            parts.append(f"""
                <div class="cp-bar-row">
                    <span class="cp-bar-name">{esc(name)}</span>
                    <span class="cp-bar-track"><span style="width:{max(6, cpl / worst * 100):.0f}%; background:{color};"></span></span>
                    <span class="cp-bar-val">${cpl:,.2f}</span>
                </div>""")
        body = "".join(parts)
    render_html(f"""
        <div class="cp-panel">
            <div class="cp-panel-title"><span class="cp-dot" style="background:#10B981"></span>Cost per Lead by Channel</div>
            {body}
        </div>
    """)


def _sparkline(values: List[float], color: str, width: int = 110, height: int = 30) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = width / (len(values) - 1)
    pts = " ".join(f"{i * step:.1f},{height - 3 - (v - lo) / span * (height - 6):.1f}" for i, v in enumerate(values))
    last_x, last_y = pts.split(" ")[-1].split(",")
    return (f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
            f'<circle cx="{last_x}" cy="{last_y}" r="2.6" fill="{color}"/></svg>')


def render_weekly_trends(weeks: List[Dict[str, Any]]) -> None:
    if len(weeks) < 2:
        body = '<div class="cp-empty">Needs at least two weekly rows.</div>'
    else:
        series = {
            "Spend": ([num(w.get("spend")) for w in weeks], None),
            "Leads": ([num(w.get("leads")) for w in weeks], True),
            "CPL": ([num(w.get("spend")) / num(w.get("leads")) if num(w.get("leads")) else 0 for w in weeks], False),
            "CTR": ([num(w.get("clicks")) / num(w.get("impressions")) * 100 if num(w.get("impressions")) else 0
                     for w in weeks], True),
        }
        parts = []
        for name, (vals, higher_good) in series.items():
            change = pct_change(vals[-1], vals[0])
            if change is None:
                cls, color, txt = "cp-delta-neutral", "#64748B", "–"
            else:
                good = None if higher_good is None else ((change >= 0) == higher_good)
                cls = "cp-delta-neutral" if good is None else ("cp-delta-positive" if good else "cp-delta-negative")
                color = {"cp-delta-neutral": "#6366F1", "cp-delta-positive": "#10B981", "cp-delta-negative": "#EF4444"}[cls]
                txt = f"{change:+.0f}%"
            parts.append(f"""
                <div class="cp-spark-row">
                    <span class="cp-bar-name">{name}</span>
                    {_sparkline(vals, color)}
                    <span class="cp-spark-val {cls}">{txt}</span>
                </div>""")
        body = "".join(parts)
    render_html(f"""
        <div class="cp-panel">
            <div class="cp-panel-title"><span class="cp-dot" style="background:#8B5CF6"></span>Weekly Trends</div>
            {body}
        </div>
    """)


# ------------------------------------------------------------------------------
# Breakdown tables
# ------------------------------------------------------------------------------
def _verdict_chip(verdict: Optional[str]) -> str:
    if not verdict or verdict not in VERDICT_STYLE:
        return ""
    bg, fg, text = VERDICT_STYLE[verdict]
    return f'<span class="cp-chip" style="background:{bg}; color:{fg};">{text}</span>'


def breakdown_table_html(rows: List[Dict[str, Any]], show_completion: bool) -> str:
    if not rows:
        return '<div class="cp-empty">No rows yet. Ask Claude to add this breakdown from your data.</div>'
    ordered = sorted(rows, key=lambda r: (num(r.get("spend")) / num(r.get("leads"))) if num(r.get("leads")) else 1e12)
    head = "<th>Name</th><th>Spend</th><th>Leads</th><th>CPL</th><th>CTR</th>"
    head += "<th>Completion</th>" if show_completion else ""
    head += "<th>Verdict</th><th>Note</th>"
    body = []
    for r in ordered:
        s, l = num(r.get("spend")), num(r.get("leads"))
        c, im = num(r.get("clicks")), num(r.get("impressions"))
        vc = r.get("video_completion_rate")
        completion = ""
        if show_completion:
            if vc not in (None, ""):
                completion = (f'<td><span class="cp-mini-track"><span style="width:{min(100, num(vc)):.0f}%"></span></span>'
                              f' {num(vc):.0f}%</td>')
            else:
                completion = "<td>–</td>"
        platform = f'<div class="cp-sub">{esc(r.get("platform"))}</div>' if r.get("platform") else ""
        body.append(
            f"<tr><td><b>{esc(r.get('label'))}</b>{platform}</td><td>${s:,.0f}</td><td>{l:,.0f}</td>"
            f"<td>{'$' + format(s / l, ',.2f') if l else '–'}</td><td>{f'{c / im * 100:.2f}%' if im else '–'}</td>"
            f"{completion}<td>{_verdict_chip(r.get('verdict'))}</td><td class='cp-note'>{esc(r.get('note') or '')}</td></tr>"
        )
    return f'<div class="cp-table-wrap"><table class="cp-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def render_breakdown_tabs(breakdowns: Dict[str, List[Dict[str, Any]]]) -> None:
    tabs = st.tabs(["🎬 Creatives", "📣 Campaigns", "🧭 Channels"])
    for tab, (dim, completion) in zip(tabs, [("creative", True), ("campaign", False), ("channel", False)]):
        with tab:
            render_html(breakdown_table_html(breakdowns.get(dim) or [], completion))


# ------------------------------------------------------------------------------
# Claude's insights panel (replaces an in-app AI assistant: the app has no AI inside)
# ------------------------------------------------------------------------------
def render_insights_panel(report: Dict[str, Any], insights: List[Dict[str, Any]], weeks: List[Dict[str, Any]],
                          client_view: bool = False) -> None:
    tone_style = {
        "positive": ("#ECFDF5", "#047857", "#A7F3D0"),
        "negative": ("#FEF2F2", "#B91C1C", "#FECACA"),
        "neutral": ("#EEF2FF", "#4338CA", "#C7D2FE"),
    }
    if insights:
        items = []
        for it in insights:
            bg, fg, border = tone_style.get(it.get("tone"), tone_style["neutral"])
            impact = f'<span class="cp-insight-impact" style="color:{fg};">{esc(it.get("impact"))}</span>' if it.get("impact") else ""
            items.append(f'<div class="cp-insight" style="background:{bg}; border-color:{border};">'
                         f'<span class="cp-dot" style="background:{fg}"></span><span>{esc(it.get("text"))}</span>{impact}</div>')
        body = "".join(items)
    elif client_view:
        body = '<div class="cp-empty">See the executive summary and recommendations for this period.</div>'
    else:
        body = ('<div class="cp-empty">No insights saved yet. In Claude, ask: '
                '<i>"Analyse this report\'s data and add key insights in ClientPulse."</i></div>')

    bars = ""
    vals = [num(w.get("leads")) for w in weeks]
    if vals:
        hi = max(vals) or 1
        bars = '<div class="cp-mini-bars">' + "".join(
            f'<span style="height:{max(8, v / hi * 100):.0f}%; opacity:{0.45 + 0.55 * (i + 1) / len(vals):.2f};" title="{v:,.0f} leads"></span>'
            for i, v in enumerate(vals)) + '</div><div class="cp-panel-sub" style="text-align:center;">Weekly leads</div>'

    k = report_kpis(report)
    if client_view:
        title, subtitle, badge, footer = "Key Insights", "Prepared by your agency", "", ""
    else:
        title, subtitle = "Claude's Insights", "Written by your Claude via MCP"
        badge = '<span class="cp-live">● Synced</span>'
        footer = """
                <div class="cp-ask">Ask Claude next</div>
                <div class="cp-suggest">
                    <span>Compare to last period</span><span>Which video should I scale?</span><span>Where is budget wasted?</span>
                </div>
                <div class="cp-panel-sub" style="margin-top:0.5rem;">Claude reads and updates this report through the ClientPulse connector. ClientPulse itself contains no AI.</div>"""
    render_html(f"""
        <div class="cp-assistant">
            <div class="cp-assistant-head">
                <div class="cp-assistant-icon">✳</div>
                <div><div class="cp-assistant-title">{title}</div>
                <div class="cp-assistant-sub">{subtitle}</div></div>
                {badge}
            </div>
            <div class="cp-assistant-body">
                <div class="cp-context">Context:
                    <span class="cp-chip" style="background:#EEF2FF;color:#4338CA;">{esc(report.get('client_name'))}</span>
                    <span class="cp-chip" style="background:#ECFDF5;color:#047857;">${k['spend']:,.0f}</span>
                </div>
                {body}
                {bars}
                {footer}
            </div>
        </div>
    """)


def render_narrative(report: Dict[str, Any]) -> None:
    c1, c2 = st.columns(2)
    with c1:
        render_html(f"""<div class="cp-panel"><div class="cp-panel-title"><span class="cp-dot" style="background:#4F46E5"></span>Executive Summary</div>
            <p class="cp-prose">{esc(report.get('summary') or 'No summary yet.')}</p></div>""")
    with c2:
        render_html(f"""<div class="cp-panel"><div class="cp-panel-title"><span class="cp-dot" style="background:#9333EA"></span>Recommendations</div>
            <p class="cp-prose">{esc(report.get('recommendations') or 'No recommendations yet.')}</p></div>""")


def render_dashboard_body(report: Dict[str, Any], breakdowns: Dict[str, List[Dict[str, Any]]],
                          insights: List[Dict[str, Any]], show_insights: bool = True, key_suffix: str = "main",
                          client_view: bool = False) -> None:
    """Full dashboard layout below the header: KPIs, charts, tables, narrative, insights."""
    weeks = breakdowns.get("week") or []
    channels = breakdowns.get("channel") or []

    if show_insights:
        main, side = st.columns([2.35, 1], gap="medium")
    else:
        main, side = st.container(), None

    with main:
        render_kpi_cards(report)
        c1, c2 = st.columns([1.55, 1], gap="small")
        with c1:
            with st.container(border=True, key=f"cp_card_trend_{key_suffix}"):
                render_trend_chart(weeks, report)
        with c2:
            with st.container(border=True, key=f"cp_card_donut_{key_suffix}"):
                render_channel_donut(channels)
        b1, b2, b3 = st.columns(3, gap="small")
        with b1:
            render_funnel(report)
        with b2:
            render_cpl_by_channel(channels)
        with b3:
            render_weekly_trends(weeks)
        render_breakdown_tabs(breakdowns)
        render_narrative(report)

    if side is not None:
        with side:
            render_insights_panel(report, insights, weeks, client_view=client_view)
