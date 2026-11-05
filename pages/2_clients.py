"""
ClientPulse - Client Management
===============================
Manage agency clients: Add new clients, view details, edit profiles,
and safely delete clients with confirmation.
"""

import streamlit as st
import database
from utils.ui import apply_custom_theme, render_header, esc

apply_custom_theme()

render_header(
    title="Client Management",
    subtitle="Add, edit, inspect, and organize your agency clients.",
    badge_text="Directory",
    badge_type="active"
)

# Tabs for organization
tab_dir, tab_add, tab_details = st.tabs(["📋 Client Directory", "➕ Add New Client", "🔍 Client Deep Dive"])

# ------------------------------------------------------------------------------
# TAB 1: Client Directory
# ------------------------------------------------------------------------------
with tab_dir:
    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        search_query = st.text_input("🔍 Search Clients", placeholder="Search by name, industry, or email...")
    with filter_col2:
        status_filter = st.selectbox("Status Filter", ["all", "active", "inactive"])

    clients = database.get_clients(status=status_filter, search=search_query)

    # Count reports per client with a single query instead of one query per client
    report_counts = {}
    for r in database.get_reports():
        report_counts[r["client_id"]] = report_counts.get(r["client_id"], 0) + 1

    if not clients:
        st.info("No clients found matching the search criteria. Try adding one in the 'Add New Client' tab.")
    else:
        st.markdown(f"**Showing {len(clients)} client{'s' if len(clients) != 1 else ''}:**")
        for client in clients:
            cid = client["id"]
            c_name = client["name"]
            # Raw stored values (used to pre-fill the edit form) vs display fallbacks
            c_industry = client.get("industry") or ""
            c_email = client.get("email") or ""
            c_website = client.get("website") or ""
            c_status = client.get("status", "active")
            c_notes = client.get("notes") or ""
            report_count = report_counts.get(cid, 0)

            status_badge_color = "#3730A3" if c_status == "active" else "#64748B"
            status_badge_bg = "#EEF2FF" if c_status == "active" else "#F1F5F9"

            with st.container():
                st.markdown(
                    f"""
                    <div style="background:#FFFFFF; border:1px solid #E0E7FF; border-radius:12px; padding:1.25rem; margin-bottom:1rem; box-shadow:0 1px 3px rgba(0,0,0,0.03);">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                            <div>
                                <div style="display:flex; align-items:center; gap:0.6rem;">
                                    <h4 style="margin:0; font-size:1.15rem; color:#1E1B4B; font-weight:700;">{esc(c_name)}</h4>
                                    <span style="background:{status_badge_bg}; color:{status_badge_color}; padding:0.2rem 0.5rem; border-radius:9999px; font-size:0.7rem; font-weight:700; text-transform:uppercase;">
                                        {esc(c_status)}
                                    </span>
                                </div>
                                <div style="font-size:0.85rem; color:#6366F1; font-weight:600; margin-top:0.2rem;">{esc(c_industry or 'General')}</div>
                                <div style="font-size:0.85rem; color:#64748B; margin-top:0.3rem;">
                                    ✉️ {esc(c_email or 'No email provided')} &nbsp;|&nbsp; 🌐 {esc(c_website or 'No website')}
                                </div>
                                {f'<div style="font-size:0.85rem; color:#475569; margin-top:0.4rem; background:#F8FAFC; padding:0.4rem 0.6rem; border-radius:6px;">📌 <em>{esc(c_notes)}</em></div>' if c_notes else ''}
                            </div>
                            <div style="text-align:right;">
                                <span style="font-size:0.85rem; color:#475569; background:#F5F3FF; padding:0.3rem 0.6rem; border-radius:6px; font-weight:600;">
                                    📊 {report_count} Report{'s' if report_count != 1 else ''}
                                </span>
                                <div style="font-size:0.75rem; color:#94A3B8; margin-top:0.4rem;">ID: <code>{esc(cid)}</code></div>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Edit and Delete controls
                exp_col1, exp_col2 = st.columns([1, 1])
                with exp_col1:
                    with st.expander(f"✏️ Quick Edit '{c_name}'"):
                        with st.form(key=f"edit_form_{cid}"):
                            new_name = st.text_input("Client Name", value=c_name)
                            new_industry = st.text_input("Industry", value=c_industry)
                            new_email = st.text_input("Contact Email", value=c_email)
                            new_website = st.text_input("Website URL", value=c_website)
                            new_notes = st.text_area("Target Metrics / Notes", value=c_notes)
                            new_status = st.selectbox(
                                "Status",
                                ["active", "inactive"],
                                index=0 if c_status == "active" else 1
                            )
                            submit_edit = st.form_submit_button("Save Changes")
                            if submit_edit and not new_name.strip():
                                st.error("Client Name is required.")
                            elif submit_edit:
                                database.update_client(
                                    cid,
                                    name=new_name.strip(),
                                    industry=new_industry,
                                    email=new_email,
                                    website=new_website,
                                    notes=new_notes,
                                    status=new_status
                                )
                                st.toast(f"Updated client '{new_name}' successfully!", icon="✅")
                                st.rerun()

                with exp_col2:
                    with st.expander(f"🗑️ Delete '{c_name}'"):
                        st.warning(f"Deleting **{c_name}** will permanently remove the client and all its **{report_count}** linked campaign reports.")
                        confirm_delete = st.checkbox(f"Yes, permanently delete {c_name}", key=f"del_chk_{cid}")
                        if st.button("Confirm Delete", key=f"del_btn_{cid}", disabled=not confirm_delete):
                            database.delete_client(cid)
                            st.toast(f"Client '{c_name}' deleted.", icon="🗑️")
                            st.rerun()

# ------------------------------------------------------------------------------
# TAB 2: Add New Client
# ------------------------------------------------------------------------------
with tab_add:
    st.markdown("##### ➕ Register New Agency Client")
    with st.form(key="add_client_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            client_name = st.text_input("Client Business Name *", placeholder="e.g. Apex Health Technologies")
            industry = st.text_input("Industry / Vertical", placeholder="e.g. HealthTech, SaaS, DTC Fashion")
            status = st.selectbox("Client Status", ["active", "inactive"])
        with col_b:
            email = st.text_input("Primary Contact Email", placeholder="e.g. contact@apexhealth.com")
            website = st.text_input("Website URL", placeholder="https://apexhealth.com")
        
        notes = st.text_area(
            "Account Notes & Target Objectives",
            placeholder="e.g. Monthly ad spend ceiling $25,000. Core KPI: CPL < $40 on Google Ads and Meta."
        )

        submit_add = st.form_submit_button("Register Client")
        if submit_add:
            if not client_name.strip():
                st.error("Client Name is required.")
            else:
                new_c = database.create_client(
                    name=client_name,
                    email=email,
                    industry=industry,
                    website=website,
                    notes=notes,
                    status=status
                )
                # A toast survives the rerun; st.success would vanish before it is seen
                st.toast(f"Client '{client_name}' registered (ID: {new_c['id']})", icon="✅")
                st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: Client Deep Dive
# ------------------------------------------------------------------------------
with tab_details:
    st.markdown("##### 🔍 Client Performance & Historical Reports")
    all_clients = database.get_clients()
    if not all_clients:
        st.info("No clients registered yet.")
    else:
        client_options = {c["id"]: f"{c['name']} ({c.get('industry') or 'General'})" for c in all_clients}
        selected_client_id = st.selectbox(
            "Select Client to Inspect",
            options=list(client_options.keys()),
            format_func=lambda x: client_options[x]
        )

        selected_client = database.get_client_by_id(selected_client_id)
        if selected_client:
            client_reports = database.get_reports(client_id=selected_client_id)
            total_client_spend = sum(float(r.get("spend") or 0.0) for r in client_reports)
            total_client_leads = sum(int(r.get("leads") or 0) for r in client_reports)
            avg_client_cpl = (total_client_spend / total_client_leads) if total_client_leads > 0 else 0.0

            dcol1, dcol2, dcol3, dcol4 = st.columns(4)
            dcol1.metric("Lifetime Spend", f"${total_client_spend:,.2f}")
            dcol2.metric("Total Leads Generated", f"{total_client_leads:,}")
            dcol3.metric("Lifetime CPL", f"${avg_client_cpl:.2f}")
            dcol4.metric("Reports Generated", str(len(client_reports)))

            st.markdown("---")
            st.markdown("###### Client Campaign Reports")
            if client_reports:
                for rep in client_reports:
                    st.markdown(
                        f"""
                        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:0.85rem 1rem; margin-bottom:0.5rem; display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <div style="font-weight:700; color:#1E1B4B; font-size:0.95rem;">{esc(rep['title'])}</div>
                                <div style="font-size:0.8rem; color:#64748B;">
                                    Period: {esc(rep['period_start'])} to {esc(rep['period_end'])} &nbsp;|&nbsp; 
                                    Spend: <strong>${rep['spend']:,.2f}</strong> &nbsp;|&nbsp; 
                                    Leads: <strong>{rep['leads']:,}</strong> &nbsp;|&nbsp; 
                                    CTR: <strong>{float(rep['ctr']):.2f}%</strong>
                                </div>
                            </div>
                            <div>
                                <span style="background:{'#ECFDF5' if rep['status']=='published' else '#FFFBEB'}; color:{'#065F46' if rep['status']=='published' else '#92400E'}; padding:0.25rem 0.5rem; border-radius:9999px; font-size:0.75rem; font-weight:600;">
                                    {esc(rep['status']).upper()}
                                </span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            else:
                st.info("No reports created for this client yet.")
