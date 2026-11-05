"""
ClientPulse - Agency Branding (white-label)
==========================================
Agency name, logo, brand colour and report footer, applied to the sidebar,
the client-facing report page, and exported PDFs.
"""

import base64

import streamlit as st

import database
from utils.pdf_report import build_report_pdf
from utils.ui import apply_custom_theme, clear_branding_cache, esc, get_branding, render_header, render_html

apply_custom_theme()
render_header(
    title="Agency Branding",
    subtitle="White-label ClientPulse: your name, logo and colours on every client report and PDF.",
    badge_text="White-label",
    badge_type="active",
)

brand = get_branding()
form_col, preview_col = st.columns([1, 1.15], gap="large")

with form_col:
    name = st.text_input("Agency name", value=brand["agency_name"])
    tagline = st.text_input("Tagline (sidebar)", value=brand["agency_tagline"])
    color = st.color_picker("Brand colour", value=brand["brand_color"])
    footer = st.text_input("Report footer", value=brand["report_footer"])
    powered = st.toggle("Show “Powered by ClientPulse” on client reports", value=bool(brand["show_powered_by"]))
    logo_file = st.file_uploader("Logo (PNG or JPG, under 500 KB)", type=["png", "jpg", "jpeg"])
    logo_uri = brand.get("logo_data_uri") or ""
    if logo_file is not None:
        if logo_file.size > 500_000:
            st.error("Logo must be under 500 KB.")
        else:
            mime = "image/png" if logo_file.name.lower().endswith("png") else "image/jpeg"
            logo_uri = f"data:{mime};base64,{base64.b64encode(logo_file.getvalue()).decode()}"
    remove_logo = bool(brand.get("logo_data_uri")) and st.checkbox("Remove current logo")
    if remove_logo:
        logo_uri = ""

    values = {"agency_name": name, "agency_tagline": tagline, "brand_color": color, "report_footer": footer,
              "show_powered_by": powered, "logo_data_uri": logo_uri}
    if st.button("💾 Save branding", type="primary"):
        try:
            database.save_branding(values)
        except ValueError as e:
            st.error(str(e))
        else:
            clear_branding_cache()
            st.toast("Branding saved. Client reports and PDFs now use it.", icon="🎨")
            st.rerun()

with preview_col:
    st.markdown("**Preview: client report header**")
    logo_html = f'<img src="{logo_uri}" style="height:34px; max-width:160px; object-fit:contain;">' if logo_uri else ""
    render_html(f"""
        <div style="background:#FFFFFF; border:1px solid #E5E7F0; border-radius:14px; padding:1.2rem 1.4rem;">
            <div style="display:flex; align-items:center; gap:0.6rem; color:{esc(color)}; font-weight:800;
                        letter-spacing:0.08em; text-transform:uppercase; font-size:0.8rem;">
                {logo_html}{esc(name)} &bull; Performance Report
            </div>
            <div style="font-size:1.6rem; font-weight:800; color:#1E1B4B; margin:0.4rem 0;">October 2026 Performance Report</div>
            <div style="height:6px; border-radius:99px; background:{esc(color)}; width:40%; margin:0.6rem 0;"></div>
            <div style="font-size:0.8rem; color:#94A3B8;">{esc(footer)}{" &bull; Powered by <b>ClientPulse</b>" if powered else ""}</div>
        </div>
    """)
    reports = database.get_reports()
    if reports:
        sample = reports[0]
        st.download_button(
            "⬇ Download a sample PDF with this branding",
            data=lambda: build_report_pdf(sample, database.get_report_breakdowns(sample["id"]),
                                          database.get_report_insights(sample), database.get_dashboard_spec(sample),
                                          values),
            file_name="branding-preview.pdf", mime="application/pdf", on_click="ignore",
        )
    st.caption("Saved branding applies to the sidebar, the public client link, and every exported PDF.")
