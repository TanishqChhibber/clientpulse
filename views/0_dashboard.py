"""
ClientPulse - Brand Dashboard
=============================
Mockup-style reporting dashboard for one brand (client) and report:
brand switcher, KPI cards, charts, breakdown tables, Claude's insights,
share link, PDF export, and an inline editor whose changes redraw the
charts live before they are saved.
"""

import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import database
from utils.dashboard import render_dashboard_body
from utils.pdf_report import build_report_pdf
from utils.ui import apply_custom_theme, esc, get_branding, render_html

apply_custom_theme()

# ------------------------------------------------------------------------------
# Brand + report selection
# ------------------------------------------------------------------------------
clients = database.get_clients()
if not clients:
    st.info("No brands yet. Ask Claude to create a client, or add one in Client Management.")
    st.stop()

client_names = {c["id"]: c["name"] for c in clients}
client_ids = list(client_names.keys())

# Hand-off from other pages ("Open dashboard" buttons)
handoff_id = st.session_state.pop("dashboard_report_id", None)
if handoff_id:
    handoff = database.get_report_by_id(handoff_id)
    if handoff:
        st.session_state["brand_id"] = handoff["client_id"]
        st.session_state[f"report_for_{handoff['client_id']}"] = handoff_id

def brand_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# Deep link: ?brand=<slug or client id>, e.g. /?brand=my-brand. Applied once per link value,
# so later dropdown changes are not overridden by the stale URL.
link_brand = st.query_params.get("brand")
if link_brand and not handoff_id and st.session_state.get("_brand_link_applied") != link_brand:
    match = next((cid for cid, name in client_names.items() if link_brand in (cid, brand_slug(name))), None)
    st.session_state["_brand_link_applied"] = link_brand
    if match:
        st.session_state["brand_id"] = match
    else:
        st.warning(f"No brand matches '{link_brand}'. Showing the latest report instead.")

if st.session_state.get("brand_id") not in client_ids:
    latest = database.get_reports()
    st.session_state["brand_id"] = latest[0]["client_id"] if latest else client_ids[0]

head_left, head_right = st.columns([3, 1.1], vertical_alignment="bottom")
with head_right:
    brand_id = st.selectbox("Brand", options=client_ids, format_func=lambda cid: client_names[cid], key="brand_id")

# Keep the address bar in sync so the current brand's URL can be bookmarked or shared with the team
current_slug = brand_slug(client_names[brand_id])
if st.query_params.get("brand") != current_slug:
    st.query_params["brand"] = current_slug
    st.session_state["_brand_link_applied"] = current_slug

# ------------------------------------------------------------------------------
# Data & template: raw CSVs for this brand, and one-click reports from the saved template
# ------------------------------------------------------------------------------
def month_bounds(day: date):
    start = day.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return start, end


def render_data_panel(client_id: str, client_name: str) -> None:
    datasets = database.list_datasets(client_id)
    template = database.get_report_template(client_id)
    label = f"📁 Data & template  ·  {len(datasets)} file{'s' if len(datasets) != 1 else ''}" + ("  ·  template saved" if template else "")
    with st.expander(label, expanded=False):
        up_col, build_col = st.columns([1, 1.3], gap="large")
        with up_col:
            st.markdown("**Upload raw data (CSV)**")
            st.caption("Exports from Google Ads, Meta, GA4, your product analytics… ClientPulse stores the rows and "
                       "computes every number itself. Claude only describes the columns.")
            upload = st.file_uploader("CSV file", type=["csv"], key=f"upload_{client_id}", label_visibility="collapsed")
            if upload is not None and st.button("Save dataset", key=f"save_ds_{client_id}"):
                try:
                    ds = database.create_dataset(client_id, upload.name, upload.getvalue().decode("utf-8-sig"))
                    st.toast(f"Saved {ds['name']} ({ds['row_count']} rows).", icon="📁")
                    st.rerun()
                except (ValueError, UnicodeDecodeError) as e:
                    st.error(f"Could not read that file: {e}")
            for ds in datasets:
                st.markdown(f"`{ds['name']}` · {ds['row_count']:,} rows · {str(ds['created_at'])[:10]}")
            if datasets:
                st.caption(f"In Claude: *“Build {client_name}'s report from the uploaded data in ClientPulse.”*")

        with build_col:
            st.markdown("**New report from template**")
            if not template:
                st.caption("No template yet. The first time Claude builds a report from a dataset for this brand, "
                           "its KPIs and charts are saved here, so later reports are one click and no AI.")
            elif not datasets:
                st.caption("Upload a dataset to use the saved template.")
            else:
                metric_names = ", ".join(m.get("label") or m["key"] for m in template.get("metrics", []))
                st.caption(f"Template metrics: {metric_names}")
                ds_names = {d["id"]: d["name"] for d in datasets}
                ds_id = st.selectbox("Dataset", list(ds_names), format_func=ds_names.get, key=f"tpl_ds_{client_id}")
                cur_start, cur_end = month_bounds(date.today().replace(day=1) - timedelta(days=1))
                c1, c2 = st.columns(2)
                period = c1.date_input("Report period", value=(cur_start, cur_end), key=f"tpl_period_{client_id}")
                prev_start, prev_end = month_bounds(cur_start - timedelta(days=1))
                compare = c2.date_input("Compare with", value=(prev_start, prev_end), key=f"tpl_compare_{client_id}")
                title = st.text_input("Title", value=f"{cur_start:%B %Y} Performance Report", key=f"tpl_title_{client_id}")
                if st.button("⚡ Build report from template", type="primary", key=f"tpl_build_{client_id}"):
                    if not (isinstance(period, tuple) and len(period) == 2):
                        st.error("Pick a start and end date for the report period.")
                    else:
                        recipe = dict(template, period={"start": str(period[0]), "end": str(period[1])}, verdicts={})
                        if isinstance(compare, tuple) and len(compare) == 2:
                            recipe["compare_period"] = {"start": str(compare[0]), "end": str(compare[1])}
                        try:
                            result = database.build_report_from_dataset(ds_id, recipe, title=title or "Performance Report")
                        except ValueError as e:
                            st.error(f"Could not build the report: {e}")
                        else:
                            st.session_state["dashboard_report_id"] = result["report"]["id"]
                            st.toast("Report computed from your data. Ask Claude to write the summary.", icon="⚡")
                            st.rerun()


render_data_panel(brand_id, client_names[brand_id])

reports = database.get_reports(client_id=brand_id)
if not reports:
    with head_left:
        render_html(f'<div class="cp-crumbs">Clients / <b>{esc(client_names[brand_id])}</b></div>'
                    f'<div class="cp-dash-title">No reports yet</div>')
    st.info("This brand has no reports yet. In Claude, attach your marketing data and ask it to build a "
            "ClientPulse report for this brand, or create one manually.")
    if st.button("＋ New Report"):
        st.session_state.pop("edit_report_id", None)
        st.switch_page("views/3_create_report.py")
    st.stop()

report_options = {r["id"]: f"{r['title']}  ·  {r['period_start']} → {r['period_end']}" for r in reports}
report_key = f"report_for_{brand_id}"
if st.session_state.get(report_key) not in report_options:
    st.session_state[report_key] = reports[0]["id"]

ctrl_report, ctrl_share, ctrl_pdf, ctrl_edit, ctrl_new = st.columns([3.2, 0.9, 1.1, 0.9, 1.1], vertical_alignment="bottom")
with ctrl_report:
    report_id = st.selectbox("Report", options=list(report_options.keys()),
                             format_func=lambda rid: report_options[rid], key=report_key)

report = database.get_report_by_id(report_id)
if not report:
    st.error("This report no longer exists.")
    st.stop()
breakdowns = database.get_report_breakdowns(report_id)
insights = database.get_report_insights(report)

status = report.get("status", "draft")
status_chip = ('<span class="cp-chip" style="background:#ECFDF5;color:#047857;">Published</span>' if status == "published"
               else '<span class="cp-chip" style="background:#FFFBEB;color:#92400E;">Draft</span>')
with head_left:
    render_html(f"""
        <div class="cp-crumbs">Clients / {esc(client_names[brand_id])} / <b>{esc(report['title'])}</b></div>
        <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap;">
            <span class="cp-dash-title">{esc(report['title'])}</span>{status_chip}
        </div>
        <div class="cp-panel-sub">{esc(report['period_start'])} → {esc(report['period_end'])}</div>
    """)

# ------------------------------------------------------------------------------
# Actions: share, PDF, edit, new
# ------------------------------------------------------------------------------
with ctrl_share:
    with st.popover("🔗 Share", width="stretch"):
        st.markdown("**Agency dashboard link** (login required)")
        st.code(f"{database.PUBLIC_APP_URL}/?brand={current_slug}", language=None)
        if status == "published":
            share_url = f"{database.PUBLIC_APP_URL}/?page=public&token={report['share_token']}"
            st.markdown("**Client link** (no login needed)")
            st.code(share_url, language=None)
            st.link_button("Open client view", share_url, width="stretch")
        else:
            st.markdown("This report is a **draft**. Publish it to get a client link.")
            if st.button("🚀 Publish now", key=f"publish_{report_id}", type="primary"):
                database.publish_report(report_id)
                st.toast("Report published.", icon="🌐")
                st.rerun()

with ctrl_pdf:
    pdf_name = re.sub(r"[^A-Za-z0-9]+", "-", f"{client_names[brand_id]} {report['title']}").strip("-").lower()
    st.download_button(
        "⬇ Export PDF",
        data=lambda: build_report_pdf(report, breakdowns, insights, database.get_dashboard_spec(report), get_branding()),
        file_name=f"{pdf_name}.pdf",
        mime="application/pdf",
        on_click="ignore",
        width="stretch",
    )

edit_key = f"edit_{report_id}"
if st.session_state.pop(f"close_edit_{report_id}", False):
    st.session_state[edit_key] = False
with ctrl_edit:
    editing = st.toggle("✏️ Edit", key=edit_key)

with ctrl_new:
    if st.button("＋ New Report", type="primary", width="stretch"):
        st.session_state.pop("edit_report_id", None)
        st.switch_page("views/3_create_report.py")

# ------------------------------------------------------------------------------
# Live editor: edits feed straight into the charts below, saved only on "Save"
# ------------------------------------------------------------------------------
DIM_COLUMNS = {
    "creative": ["label", "platform", "impressions", "clicks", "leads", "spend", "prev_spend", "prev_leads",
                 "video_completion_rate", "verdict", "note"],
    "campaign": ["label", "platform", "impressions", "clicks", "leads", "spend", "prev_spend", "prev_leads", "verdict", "note"],
    "channel": ["label", "platform", "impressions", "clicks", "leads", "spend", "prev_spend", "prev_leads", "note"],
    "week": ["label", "impressions", "clicks", "leads", "spend"],
}
NUMERIC = {"impressions", "clicks", "leads", "spend", "prev_spend", "prev_leads", "video_completion_rate"}


def rows_to_df(rows, columns):
    df = pd.DataFrame([{c: r.get(c) for c in columns} for r in rows], columns=columns)
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in NUMERIC else df[c].astype("object")
    return df


def df_to_rows(df):
    clean = df.astype(object).where(pd.notna(df), None)
    return [r for r in clean.to_dict("records") if str(r.get("label") or "").strip()]


def column_config(dim):
    cfg = {
        "label": st.column_config.TextColumn("Week start (YYYY-MM-DD)" if dim == "week" else "Name", required=True, width="medium"),
        "platform": st.column_config.TextColumn("Platform"),
        "impressions": st.column_config.NumberColumn("Impr.", min_value=0, step=1, format="%d"),
        "clicks": st.column_config.NumberColumn("Clicks", min_value=0, step=1, format="%d"),
        "leads": st.column_config.NumberColumn("Leads", min_value=0, step=1, format="%d"),
        "spend": st.column_config.NumberColumn("Spend", min_value=0.0, format="$%.2f"),
        "prev_spend": st.column_config.NumberColumn("Prev spend", min_value=0.0, format="$%.2f"),
        "prev_leads": st.column_config.NumberColumn("Prev leads", min_value=0, step=1, format="%d"),
        "video_completion_rate": st.column_config.NumberColumn("Completion %", min_value=0.0, max_value=100.0, format="%.1f"),
        "verdict": st.column_config.SelectboxColumn("Verdict", options=list(database.VERDICTS)),
        "note": st.column_config.TextColumn("Note", width="large"),
    }
    return {c: cfg[c] for c in DIM_COLUMNS[dim]}


working_report, working_breakdowns, working_insights = report, breakdowns, insights
spec = database.get_dashboard_spec(report)
working_spec = spec

FORMAT_COL = lambda label="Format": st.column_config.SelectboxColumn(label, options=list(database.METRIC_FORMATS), default="number")


def clean_records(df):
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


def kpis_editor(kpis, key):
    df = pd.DataFrame([{c: kp.get(c) for c in ("label", "value", "prev", "format", "higher_is_better")} for kp in kpis],
                      columns=["label", "value", "prev", "format", "higher_is_better"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["prev"] = pd.to_numeric(df["prev"], errors="coerce")
    df["higher_is_better"] = df["higher_is_better"].astype("boolean")
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=key, column_config={
        "label": st.column_config.TextColumn("KPI name", required=True),
        "value": st.column_config.NumberColumn("This period"),
        "prev": st.column_config.NumberColumn("Previous period"),
        "format": FORMAT_COL(),
        "higher_is_better": st.column_config.CheckboxColumn("Higher is better", default=True),
    })
    return df, [r for r in clean_records(edited) if str(r.get("label") or "").strip()], edited


def labelled_editor(block, key):
    df = pd.DataFrame({"label": block.get("labels", []), "value": block.get("values", [])})
    edited = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=key, column_config={
        "label": st.column_config.TextColumn("Label", required=True), "value": st.column_config.NumberColumn("Value")})
    rows = [r for r in clean_records(edited) if str(r.get("label") or "").strip()]
    return {**block, "labels": [str(r["label"]) for r in rows], "values": [r["value"] or 0 for r in rows]}, not edited.equals(df)


if editing:
    ver = st.session_state.setdefault(f"edit_ver_{report_id}", 0)
    k = lambda name: f"{name}_{report_id}_{ver}"
    original_ins = pd.DataFrame([{"text": i.get("text"), "impact": i.get("impact"), "tone": i.get("tone")} for i in insights],
                                columns=["text", "impact", "tone"])
    changed_spec = False

    with st.container(border=True, key=f"cp_card_editor_{report_id}"):
        render_html('<div class="cp-panel-title">✏️ Editing report</div>'
                    '<div class="cp-panel-sub">Every change redraws the dashboard below instantly. Nothing is saved until you press Save.</div>')

        if spec and any(spec.get(key) for key in ("trend", "split", "rankings", "table")):
            # ---- Client-defined dashboard: KPI names, chart data and table cells are all editable
            t_kpi, t_trend, t_split, t_rank, t_table, t_txt = st.tabs(["KPIs", "Trend", "Split", "Rankings", "Table", "Summary & Insights"])
            raw = {"currency": spec.get("currency", "$")}
            with t_kpi:
                new_title = st.text_input("Report title", value=report["title"], key=k("title"))
                raw["currency"] = st.text_input("Currency symbol", value=spec.get("currency", "$"), max_chars=4, key=k("currency"))
                kdf, raw["kpis"], kedited = kpis_editor(spec.get("kpis") or [], k("ed_kpis"))
                changed_spec |= not kedited.equals(kdf) or raw["currency"] != spec.get("currency", "$")
            with t_trend:
                trend = spec.get("trend")
                if trend:
                    names = [se["name"] for se in trend["series"]]
                    tdf = pd.DataFrame({"Period": trend["x"], **{n: se["values"] for n, se in zip(names, trend["series"])}})
                    tedited = st.data_editor(tdf, num_rows="dynamic", hide_index=True, width="stretch", key=k("ed_trend"))
                    rows = [r for r in clean_records(tedited) if str(r.get("Period") or "").strip()]
                    raw["trend"] = {**trend, "x": [str(r["Period"]) for r in rows],
                                    "series": [{**se, "values": [r.get(n) or 0 for r in rows]} for n, se in zip(names, trend["series"])]}
                    changed_spec |= not tedited.equals(tdf)
                else:
                    st.caption("No trend chart. Ask Claude to add one with set_custom_dashboard.")
            with t_split:
                if spec.get("split"):
                    raw["split"], ch = labelled_editor(spec["split"], k("ed_split"))
                    changed_spec |= ch
                else:
                    st.caption("No split chart.")
            with t_rank:
                raw["rankings"] = []
                for i, rk in enumerate(spec.get("rankings") or []):
                    st.caption(rk.get("title") or f"Ranking {i + 1}")
                    block, ch = labelled_editor(rk, k(f"ed_rank_{i}"))
                    raw["rankings"].append(block)
                    changed_spec |= ch
                if not raw["rankings"]:
                    st.caption("No rankings.")
            with t_table:
                table = spec.get("table")
                if table:
                    cols = table["columns"]
                    rows_df = pd.DataFrame([{"name": r["name"], **{c["key"]: r["values"].get(c["key"]) for c in cols},
                                             "verdict": r.get("verdict"), "note": r.get("note")} for r in table["rows"]],
                                           columns=["name"] + [c["key"] for c in cols] + ["verdict", "note"])
                    for c in cols:
                        rows_df[c["key"]] = pd.to_numeric(rows_df[c["key"]], errors="coerce")
                    cfg = {"name": st.column_config.TextColumn("Name", required=True),
                           "verdict": st.column_config.SelectboxColumn("Verdict", options=list(database.VERDICTS)),
                           "note": st.column_config.TextColumn("Note", width="large")}
                    cfg.update({c["key"]: st.column_config.NumberColumn(c["label"]) for c in cols})
                    tbl_edited = st.data_editor(rows_df, num_rows="dynamic", hide_index=True, width="stretch",
                                                key=k("ed_table"), column_config=cfg)
                    raw["table"] = {**table, "rows": [
                        {"name": r["name"], "values": {c["key"]: r.get(c["key"]) for c in cols},
                         "verdict": r.get("verdict"), "note": r.get("note")}
                        for r in clean_records(tbl_edited) if str(r.get("name") or "").strip()]}
                    changed_spec |= not tbl_edited.equals(rows_df)
                else:
                    st.caption("No table.")
            for key_name in ("trend", "split", "table"):
                raw.setdefault(key_name, spec.get(key_name))
            totals = {}
        else:
            # ---- Standard ad-performance report
            t_tot, t_cre, t_cam, t_cha, t_wk, t_kpi, t_txt = st.tabs(
                ["Totals", "Creatives", "Campaigns", "Channels", "Weekly", "Custom KPIs", "Summary & Insights"])
            with t_tot:
                new_title = st.text_input("Report title", value=report["title"], key=k("title"))
                st.caption("Current period")
                c1, c2, c3, c4 = st.columns(4)
                e_spend = c1.number_input("Spend ($)", min_value=0.0, value=float(report["spend"]), step=100.0, key=k("spend"))
                e_imp = c2.number_input("Impressions", min_value=0, value=int(report["impressions"]), step=1000, key=k("imp"))
                e_clicks = c3.number_input("Clicks", min_value=0, value=int(report["clicks"]), step=100, key=k("clicks"))
                e_leads = c4.number_input("Leads", min_value=0, value=int(report["leads"]), step=10, key=k("leads"))
                st.caption("Previous period")
                p1, p2, p3, p4 = st.columns(4)
                e_pspend = p1.number_input("Prev spend ($)", min_value=0.0, value=float(report["prev_spend"]), step=100.0, key=k("pspend"))
                e_pimp = p2.number_input("Prev impressions", min_value=0, value=int(report["prev_impressions"]), step=1000, key=k("pimp"))
                e_pclicks = p3.number_input("Prev clicks", min_value=0, value=int(report["prev_clicks"]), step=100, key=k("pclicks"))
                e_pleads = p4.number_input("Prev leads", min_value=0, value=int(report["prev_leads"]), step=10, key=k("pleads"))
            totals = dict(spend=e_spend, impressions=e_imp, clicks=e_clicks, leads=e_leads,
                          prev_spend=e_pspend, prev_impressions=e_pimp, prev_clicks=e_pclicks, prev_leads=e_pleads)

            original_dfs = {dim: rows_to_df(breakdowns.get(dim) or [], cols) for dim, cols in DIM_COLUMNS.items()}
            edited_dfs = {}
            for tab, dim in [(t_cre, "creative"), (t_cam, "campaign"), (t_cha, "channel"), (t_wk, "week")]:
                with tab:
                    edited_dfs[dim] = st.data_editor(original_dfs[dim], column_config=column_config(dim), num_rows="dynamic",
                                                     hide_index=True, width="stretch", key=k(f"ed_{dim}"))
            working_breakdowns = {dim: df_to_rows(df) for dim, df in edited_dfs.items()}
            with t_kpi:
                st.caption("Add rows to replace the standard KPI cards (Ad Spend, Leads, CPL, CTR) with your client's "
                           "own metric names and numbers. Leave empty to keep the standard cards.")
                kdf, custom_kpis, kedited = kpis_editor((spec or {}).get("kpis") or [], k("ed_kpis"))
                changed_spec = not kedited.equals(kdf)
            raw = {"currency": (spec or {}).get("currency", "$"), "kpis": custom_kpis} if custom_kpis else None
            if raw is None:
                working_spec = None  # all custom KPI rows removed: preview the standard cards

        with t_txt:
            e_summary = st.text_area("Executive summary", value=report.get("summary") or "", height=130, key=k("summary"))
            e_recs = st.text_area("Recommendations", value=report.get("recommendations") or "", height=130, key=k("recs"))
            st.caption("Key insights (shown in the insights panel)")
            edited_ins = st.data_editor(
                original_ins, num_rows="dynamic", hide_index=True, width="stretch", key=k("ed_insights"),
                column_config={
                    "text": st.column_config.TextColumn("Insight", required=True, width="large"),
                    "impact": st.column_config.TextColumn("Impact chip"),
                    "tone": st.column_config.SelectboxColumn("Tone", options=list(database.INSIGHT_TONES), default="neutral"),
                })

        # Live preview of the custom layout; an incomplete row keeps the last valid version on screen
        spec_error = None
        if raw is not None:
            try:
                working_spec = database.validate_dashboard_spec(raw)
            except ValueError as e:
                spec_error = str(e)
                st.warning(f"Preview paused until this is fixed: {spec_error}")

        working_report = {**report, **totals, "title": new_title, "summary": e_summary, "recommendations": e_recs}
        working_insights = [{"text": str(r["text"]).strip(), "impact": r.get("impact") or "", "tone": r.get("tone") or "neutral"}
                            for r in clean_records(edited_ins) if str(r.get("text") or "").strip()]

        s1, s2, _ = st.columns([1, 1, 4])
        if s1.button("💾 Save changes", type="primary", key=k("save"), width="stretch"):
            try:
                if not new_title.strip():
                    raise ValueError("Report title cannot be empty.")
                if spec_error:
                    raise ValueError(spec_error)
                database.update_report(report_id, title=new_title.strip(), summary=e_summary,
                                       recommendations=e_recs, **totals)
                if totals:  # standard ad report editor was used
                    for dim, df in edited_dfs.items():
                        if not df.equals(original_dfs[dim]):
                            database.set_report_breakdown(report_id, dim, working_breakdowns[dim])
                if changed_spec:
                    database.set_dashboard_spec(report_id, raw)
                if not edited_ins.equals(original_ins):
                    database.set_report_insights(report_id, working_insights)
            except ValueError as e:
                st.error(f"Could not save: {e}")
            else:
                st.session_state[f"edit_ver_{report_id}"] = ver + 1
                st.session_state[f"close_edit_{report_id}"] = True
                st.toast("Report saved.", icon="✅")
                st.rerun()
        if s2.button("Discard", key=k("discard"), width="stretch"):
            st.session_state[f"edit_ver_{report_id}"] = ver + 1
            st.session_state[f"close_edit_{report_id}"] = True
            st.rerun()


# ------------------------------------------------------------------------------
# Data source & formulas: every number on a computed report is traceable
# ------------------------------------------------------------------------------
computation = database.get_report_computation(report)
if computation and not editing:
    audit, recipe = computation["audit"], computation["recipe"]
    prev_txt = f" vs {audit['rows_previous']:,} rows in the comparison period" if audit.get("compare_period") else ""
    render_html(f"""
        <div class="cp-source">🧮 <b>Computed by ClientPulse</b> from <code>{esc(audit['dataset'])}</code>:
        {audit['rows_current']:,} rows in {esc(audit['period']['start'])} → {esc(audit['period']['end'])}{esc(prev_txt)}.
        Every figure comes from a formula below, not from AI.</div>
    """)
    with st.expander("Formulas & source rows"):
        rnd = lambda v: None if v is None else round(float(v), 2)
        st.dataframe(pd.DataFrame([{"Metric": m["label"], "Formula": m["formula"],
                                    "This period": rnd(m["current"]), "Previous": rnd(m["previous"])} for m in audit["metrics"]]),
                     hide_index=True, width="stretch")
        dataset = database.get_dataset(report.get("source_dataset_id") or "")
        if dataset:
            from utils.compute import load_csv, period_rows
            rows = period_rows(load_csv(dataset["csv_text"]), recipe)
            st.caption(f"Source rows for this period ({len(rows):,})")
            st.dataframe(rows, hide_index=True, width="stretch", height=260)
        else:
            st.caption("The source dataset has been deleted; the stored figures are unchanged.")

# ------------------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------------------
render_dashboard_body(working_report, working_breakdowns, working_insights, show_insights=True,
                      key_suffix=report_id, spec=working_spec)
