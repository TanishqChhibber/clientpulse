"""
ClientPulse PDF Export
======================
Builds a client-ready PDF of a report (KPIs, charts, breakdown tables, insights,
narrative) using fpdf2 for layout and matplotlib for charts. Pure Python, no
browser or system packages required, so it runs on any host.
"""

import io
import os
import re
from typing import Any, Dict, List, Optional

INDIGO = (79, 70, 229)
NAVY = (30, 27, 75)
SLATE = (100, 116, 139)
LIGHT = (241, 245, 249)
GREEN = (5, 150, 105)
RED = (220, 38, 38)
CHART_COLORS = ["#4F46E5", "#10B981", "#8B5CF6", "#F59E0B", "#EF4444", "#0EA5E9", "#EC4899", "#64748B"]


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _safe(text: Any) -> str:
    """Drop characters outside the Basic Multilingual Plane (emoji), which the PDF font cannot draw."""
    return re.sub(r"[^\u0000-\uFFFF]", "", str(text or ""))


def _pct_change(cur: float, prev: float) -> Optional[float]:
    return (cur - prev) / prev * 100 if prev else None


def _font_paths():
    import matplotlib
    base = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
    return os.path.join(base, "DejaVuSans.ttf"), os.path.join(base, "DejaVuSans-Bold.ttf")


def _chart_png(draw, width_in: float, height_in: float) -> io.BytesIO:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=160)
    draw(fig, ax)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf


def _weekly_chart(weeks: List[Dict[str, Any]]) -> io.BytesIO:
    labels = [str(w["label"])[5:] if len(str(w["label"])) >= 10 else str(w["label"]) for w in weeks]
    leads = [_num(w.get("leads")) for w in weeks]
    spend = [_num(w.get("spend")) for w in weeks]

    def draw(fig, ax):
        ax.plot(labels, leads, color="#4F46E5", marker="o", linewidth=2, label="Leads")
        ax.fill_between(range(len(labels)), leads, color="#4F46E5", alpha=0.08)
        ax.set_ylabel("Leads", color="#4F46E5", fontsize=8)
        ax2 = ax.twinx()
        ax2.plot(labels, spend, color="#10B981", linestyle="--", linewidth=1.6, label="Spend ($)")
        ax2.set_ylabel("Spend ($)", color="#10B981", fontsize=8)
        ax2.spines["top"].set_visible(False)
        for a in (ax, ax2):
            a.tick_params(labelsize=7)
        ax.set_title("Weekly Leads & Spend", fontsize=9, loc="left", color="#1E1B4B")
        ax.grid(axis="y", color="#F1F5F9")

    return _chart_png(draw, 6.2, 2.4)


def _channel_donut(channels: List[Dict[str, Any]]) -> io.BytesIO:
    labels = [_safe(c["label"]) for c in channels]
    spend = [_num(c.get("spend")) for c in channels]

    def draw(fig, ax):
        ax.pie(spend, labels=None, colors=CHART_COLORS[:len(spend)], startangle=90,
               wedgeprops={"width": 0.38, "edgecolor": "white"})
        ax.text(0, 0, f"${sum(spend):,.0f}", ha="center", va="center", fontsize=9, fontweight="bold", color="#1E1B4B")
        total = sum(spend) or 1
        ax.legend([f"{l} ({s / total * 100:.0f}%)" for l, s in zip(labels, spend)],
                  loc="center left", bbox_to_anchor=(1, 0.5), fontsize=7, frameon=False)
        ax.set_title("Spend by Channel", fontsize=9, loc="left", color="#1E1B4B")
        ax.axis("equal")

    return _chart_png(draw, 3.6, 2.3)


def _cpl_bars(channels: List[Dict[str, Any]]) -> io.BytesIO:
    rows = [(c["label"], _num(c.get("spend")) / _num(c.get("leads"))) for c in channels if _num(c.get("leads")) > 0]
    rows.sort(key=lambda r: r[1])

    def draw(fig, ax):
        names = [_safe(r[0]) for r in rows]
        values = [r[1] for r in rows]
        colors = ["#10B981" if i == 0 else ("#EF4444" if i == len(rows) - 1 and len(rows) > 1 else "#6366F1")
                  for i in range(len(rows))]
        ax.barh(names, values, color=colors)
        ax.invert_yaxis()
        for i, v in enumerate(values):
            ax.text(v, i, f" ${v:,.2f}", va="center", fontsize=7)
        ax.tick_params(labelsize=7)
        ax.set_title("Cost per Lead by Channel", fontsize=9, loc="left", color="#1E1B4B")

    return _chart_png(draw, 3.6, 2.3)


class _ReportPDF:
    def __init__(self):
        from fpdf import FPDF

        regular, bold = _font_paths()
        self.pdf = FPDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=15)
        self.pdf.add_font("DejaVu", "", regular)
        self.pdf.add_font("DejaVu", "B", bold)
        self.pdf.set_margins(14, 14, 14)
        self.pdf.add_page()
        self.width = self.pdf.w - 28

    def font(self, size: float, bold: bool = False, color=NAVY):
        self.pdf.set_font("DejaVu", "B" if bold else "", size)
        self.pdf.set_text_color(*color)

    def section(self, title: str):
        self.pdf.ln(4)
        self.font(11.5, True, INDIGO)
        self.pdf.cell(0, 7, _safe(title), new_x="LMARGIN", new_y="NEXT")
        self.pdf.set_draw_color(224, 231, 255)
        y = self.pdf.get_y()
        self.pdf.line(14, y, 14 + self.width, y)
        self.pdf.ln(2)

    def paragraph(self, text: str, size: float = 9.5):
        self.font(size, False, (51, 65, 85))
        self.pdf.multi_cell(0, 5, _safe(text), new_x="LMARGIN", new_y="NEXT")


def build_report_pdf(
    report: Dict[str, Any],
    breakdowns: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    insights: Optional[List[Dict[str, Any]]] = None
) -> bytes:
    """Return the PDF bytes for a report."""
    breakdowns = breakdowns or {}
    insights = insights or []
    doc = _ReportPDF()
    pdf = doc.pdf

    # Header band
    pdf.set_fill_color(*INDIGO)
    pdf.rect(0, 0, pdf.w, 34, style="F")
    pdf.set_xy(14, 8)
    doc.font(8, True, (199, 210, 254))
    pdf.cell(0, 5, "CLIENTPULSE  |  CAMPAIGN PERFORMANCE REPORT", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(14)
    doc.font(16, True, (255, 255, 255))
    pdf.multi_cell(doc.width, 8, _safe(report.get("title")), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(14)
    doc.font(9, False, (224, 231, 255))
    pdf.cell(0, 5, _safe(f"{report.get('client_name', '')}  |  {report.get('period_start')} to {report.get('period_end')}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), 34) + 6)

    # KPI boxes
    spend, leads = _num(report.get("spend")), _num(report.get("leads"))
    clicks, impressions = _num(report.get("clicks")), _num(report.get("impressions"))
    p_spend, p_leads = _num(report.get("prev_spend")), _num(report.get("prev_leads"))
    p_clicks, p_imp = _num(report.get("prev_clicks")), _num(report.get("prev_impressions"))
    cpl = spend / leads if leads else 0
    p_cpl = p_spend / p_leads if p_leads else 0
    ctr = clicks / impressions * 100 if impressions else 0
    p_ctr = p_clicks / p_imp * 100 if p_imp else 0
    kpis = [
        ("AD SPEND", f"${spend:,.0f}", _pct_change(spend, p_spend), None),
        ("LEADS", f"{leads:,.0f}", _pct_change(leads, p_leads), True),
        ("COST PER LEAD", f"${cpl:,.2f}", _pct_change(cpl, p_cpl), False),
        ("CTR", f"{ctr:.2f}%", _pct_change(ctr, p_ctr), True),
    ]
    box_w, gap, top = (doc.width - 9) / 4, 3, pdf.get_y()
    for i, (label, value, delta, higher_good) in enumerate(kpis):
        x = 14 + i * (box_w + gap)
        pdf.set_fill_color(*LIGHT)
        pdf.rect(x, top, box_w, 22, style="F")
        pdf.set_xy(x + 3, top + 2.5)
        doc.font(7, True, SLATE)
        pdf.cell(box_w - 6, 4, label)
        pdf.set_xy(x + 3, top + 7.5)
        doc.font(13, True, NAVY)
        pdf.cell(box_w - 6, 7, value)
        pdf.set_xy(x + 3, top + 15.5)
        if delta is None:
            doc.font(7, False, SLATE)
            pdf.cell(box_w - 6, 4, "no previous period")
        else:
            good = None if higher_good is None else ((delta >= 0) == higher_good)
            doc.font(7, True, SLATE if good is None else (GREEN if good else RED))
            pdf.cell(box_w - 6, 4, f"{delta:+.1f}% vs previous")
    pdf.set_y(top + 26)

    # Charts
    weeks, channels = breakdowns.get("week") or [], breakdowns.get("channel") or []
    if weeks:
        pdf.image(_weekly_chart(weeks), x=14, w=doc.width)
    if channels:
        y = pdf.get_y() + 2
        if y + 58 > pdf.h - 15:
            pdf.add_page()
            y = pdf.get_y()
        half = (doc.width - 4) / 2
        pdf.image(_channel_donut(channels), x=14, y=y, w=half)
        pdf.image(_cpl_bars(channels), x=14 + half + 4, y=y, w=half)
        pdf.set_y(y + half * 2.3 / 3.6 + 2)

    # Key insights
    if insights:
        doc.section("Key Insights")
        for item in insights:
            tone = item.get("tone", "neutral")
            color = GREEN if tone == "positive" else (RED if tone == "negative" else SLATE)
            doc.font(9.5, False, color)
            impact = f"[{item.get('impact')}] " if item.get("impact") else ""
            pdf.multi_cell(0, 5.2, _safe(f"• {impact}{item.get('text', '')}"), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(0.8)

    # Breakdown tables
    def table(title: str, rows: List[Dict[str, Any]], with_completion: bool):
        if not rows:
            return
        doc.section(title)
        headers = ["Name", "Spend", "Leads", "CPL", "CTR"] + (["Compl."] if with_completion else []) + ["Verdict"]
        widths = (55, 22, 16, 18, 15) + ((16,) if with_completion else ()) + (20,)
        doc.font(8, False, NAVY)
        with pdf.table(col_widths=widths, text_align="LEFT", line_height=5.5,
                       borders_layout="HORIZONTAL_LINES") as t:
            head = t.row()
            for h in headers:
                head.cell(h)
            for r in sorted(rows, key=lambda r: (_num(r.get("spend")) / _num(r.get("leads"))) if _num(r.get("leads")) else 1e9):
                s, l = _num(r.get("spend")), _num(r.get("leads"))
                c, im = _num(r.get("clicks")), _num(r.get("impressions"))
                cells = [_safe(r.get("label")), f"${s:,.0f}", f"{l:,.0f}",
                         f"${s / l:,.2f}" if l else "-", f"{c / im * 100:.2f}%" if im else "-"]
                if with_completion:
                    vc = r.get("video_completion_rate")
                    cells.append(f"{_num(vc):.0f}%" if vc not in (None, "") else "-")
                cells.append((r.get("verdict") or "").upper())
                row = t.row()
                for value in cells:
                    row.cell(value)

    table("Creative Performance", breakdowns.get("creative") or [], True)
    table("Campaign Performance", breakdowns.get("campaign") or [], False)

    # Narrative
    if report.get("summary"):
        doc.section("Executive Summary")
        doc.paragraph(report["summary"])
    if report.get("recommendations"):
        doc.section("Recommendations")
        doc.paragraph(report["recommendations"])

    pdf.ln(6)
    doc.font(7.5, False, SLATE)
    pdf.cell(0, 5, "Prepared with ClientPulse", align="C")
    return bytes(pdf.output())
