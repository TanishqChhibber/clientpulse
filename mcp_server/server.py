"""
ClientPulse MCP Server
======================
Remote Model Context Protocol (MCP) server using Streamable HTTP transport.
Enables Claude to perform real database operations for client management,
campaign report generation, updates, and publishing.

Exposed Tools:
1. create_client
2. list_clients
3. create_report
4. list_reports
5. update_report
6. publish_report
7. set_report_breakdown
8. get_report

NO AI API keys or embedded models are used. All reasoning is performed by Claude.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import BaseModel, Field

# Ensure clientpulse root directory is on the path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment configuration
load_dotenv(PROJECT_ROOT / ".env")

import database

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
# Hosting platforms (Render, Railway, Heroku) assign the port through $PORT
MCP_PORT = int(os.getenv("MCP_PORT") or os.getenv("PORT") or "8000")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "").strip()


def _build_auth():
    """Require a bearer token on every MCP request when MCP_AUTH_TOKEN is set."""
    if not MCP_AUTH_TOKEN:
        return None
    from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
    return StaticTokenVerifier(tokens={MCP_AUTH_TOKEN: {"client_id": "clientpulse-agency", "scopes": []}})


# Initialize FastMCP Server
mcp = FastMCP(
    name="ClientPulse Agency Reporting Server",
    instructions=(
        "You are connected to ClientPulse, a multi-tenant client reporting platform for digital marketing agencies. "
        "Use these tools to create clients, list clients, generate detailed campaign performance reports with real ROI metrics, "
        "update report analyses, and publish reports with shareable links for client viewing. "
        "When the user shares raw campaign data (CSV / sheet exports), aggregate it yourself, call create_report "
        "with the period totals, then call set_report_breakdown once with per-channel, per-campaign, per-creative "
        "and weekly rows plus 3-5 key insights, so the dashboard charts and tables are populated."
    ),
    auth=_build_auth()
)


# ==============================================================================
# TOOL 1: create_client
# ==============================================================================
@mcp.tool(
    name="create_client",
    title="Create Client",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    description="Register a new agency client in ClientPulse database. Performs real database insert."
)
def create_client(
    name: str,
    email: str = "",
    industry: str = "",
    website: str = "",
    notes: str = "",
    status: str = "active"
) -> Dict[str, Any]:
    """
    Register a new digital marketing client.

    Args:
        name: Business or company name of the client (required).
        email: Primary contact email for reporting.
        industry: Client industry or market vertical (e.g., 'B2B SaaS', 'DTC Fashion', 'Fintech').
        website: Client website URL.
        notes: Strategic notes, target KPIs, or ad spend ceiling.
        status: Client account status ('active' or 'inactive'). Defaults to 'active'.

    Returns:
        A dictionary containing the newly registered client record with its generated ID.
    """
    if not name or not name.strip():
        return {"error": True, "message": "Client name is required and cannot be empty."}

    try:
        client = database.create_client(
            name=name.strip(),
            email=email.strip(),
            industry=industry.strip(),
            website=website.strip(),
            notes=notes.strip(),
            status=status if status in ("active", "inactive") else "active"
        )
        return {
            "success": True,
            "message": f"Client '{client['name']}' registered successfully.",
            "client": client
        }
    except Exception as e:
        return {"error": True, "message": f"Failed to create client: {str(e)}"}


# ==============================================================================
# TOOL 2: list_clients
# ==============================================================================
@mcp.tool(
    name="list_clients",
    title="List Clients",
    annotations={"readOnlyHint": True, "openWorldHint": False},
    description="Retrieve agency clients from database with optional status filtering and name search."
)
def list_clients(
    status: str = "all",
    search: str = ""
) -> Dict[str, Any]:
    """
    List all agency clients currently in the database.

    Args:
        status: Filter by status ('all', 'active', or 'inactive'). Defaults to 'all'.
        search: Optional search term to filter by client name, industry, or email.

    Returns:
        A dictionary containing client count and list of client records.
    """
    try:
        clients = database.get_clients(
            status=status if status != "all" else None,
            search=search if search.strip() else None
        )
        return {
            "success": True,
            "count": len(clients),
            "clients": clients
        }
    except Exception as e:
        return {"error": True, "message": f"Failed to list clients: {str(e)}"}


# ==============================================================================
# TOOL 3: create_report
# ==============================================================================
@mcp.tool(
    name="create_report",
    title="Create Report",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    description="Create a marketing performance report for a client with campaign metrics, summary, and recommendations."
)
def create_report(
    client_id: str,
    title: str,
    period_start: str,
    period_end: str,
    impressions: int,
    clicks: int,
    leads: int,
    spend: float,
    summary: str,
    recommendations: str,
    prev_impressions: int = 0,
    prev_clicks: int = 0,
    prev_leads: int = 0,
    prev_spend: float = 0.0,
    status: str = "draft"
) -> Dict[str, Any]:
    """
    Create a campaign performance report. Automatically computes CTR, Cost Per Lead (CPL),
    and conversion rates, and assigns a unique public share token.

    Args:
        client_id: The ID of the client for whom this report is created.
        title: Title of the performance report (e.g. 'Q3 2026 Paid Ads Growth & ROI Report').
        period_start: Start date of reporting period in YYYY-MM-DD format.
        period_end: End date of reporting period in YYYY-MM-DD format.
        impressions: Total ad impressions delivered in this period.
        clicks: Total ad clicks generated.
        leads: Total conversions / qualified leads generated.
        spend: Total advertising spend in USD.
        summary: Executive analysis of campaign performance, wins, and channel breakdown.
        recommendations: Actionable strategic recommendations for the next cycle.
        prev_impressions: Ad impressions in previous comparison period (benchmark).
        prev_clicks: Ad clicks in previous comparison period.
        prev_leads: Leads generated in previous comparison period.
        prev_spend: Total ad spend in previous comparison period.
        status: Report status ('draft' or 'published'). Defaults to 'draft'.

    Returns:
        The newly created report record including computed CTR, CPL, and share token.
    """
    # Validate client exists
    client = database.get_client_by_id(client_id)
    if not client:
        return {
            "error": True,
            "message": f"Client ID '{client_id}' not found. Please verify client_id using list_clients."
        }

    if not title or not title.strip():
        return {"error": True, "message": "Report title cannot be empty."}

    try:
        report = database.create_report(
            client_id=client_id,
            title=title.strip(),
            period_start=period_start,
            period_end=period_end,
            impressions=impressions,
            clicks=clicks,
            leads=leads,
            spend=spend,
            summary=summary.strip(),
            recommendations=recommendations.strip(),
            prev_impressions=prev_impressions,
            prev_clicks=prev_clicks,
            prev_leads=prev_leads,
            prev_spend=prev_spend,
            status=status if status in ("draft", "published") else "draft"
        )
        share_url = f"{database.PUBLIC_APP_URL}/?page=public&token={report['share_token']}"
        return {
            "success": True,
            "message": f"Report '{report['title']}' created successfully.",
            "report_id": report["id"],
            "share_token": report["share_token"],
            "public_url": share_url if report["status"] == "published" else None,
            "report": report
        }
    except Exception as e:
        return {"error": True, "message": f"Failed to create report: {str(e)}"}


# ==============================================================================
# TOOL 4: list_reports
# ==============================================================================
@mcp.tool(
    name="list_reports",
    title="List Reports",
    annotations={"readOnlyHint": True, "openWorldHint": False},
    description="Retrieve campaign reports with optional filtering by client_id, status, or search query."
)
def list_reports(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """
    List historical campaign reports.

    Args:
        client_id: Optional client ID filter.
        status: Optional status filter ('all', 'draft', or 'published').
        search: Optional text search across report title and client name.

    Returns:
        List of matching reports with client metadata.
    """
    try:
        reports = database.get_reports(
            client_id=client_id if client_id and client_id != "all" else None,
            status=status if status and status != "all" else None,
            search=search if search and search.strip() else None
        )
        return {
            "success": True,
            "count": len(reports),
            "reports": reports
        }
    except Exception as e:
        return {"error": True, "message": f"Failed to list reports: {str(e)}"}


# ==============================================================================
# TOOL 5: update_report
# ==============================================================================
@mcp.tool(
    name="update_report",
    title="Update Report",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    description="Update an existing campaign report. Recalculates CTR and CPL if metrics change."
)
def update_report(
    report_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    recommendations: Optional[str] = None,
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
    impressions: Optional[int] = None,
    clicks: Optional[int] = None,
    leads: Optional[int] = None,
    spend: Optional[float] = None,
    prev_impressions: Optional[int] = None,
    prev_clicks: Optional[int] = None,
    prev_leads: Optional[int] = None,
    prev_spend: Optional[float] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update fields of an existing report.

    Args:
        report_id: The ID of the report to update.
        title: Optional updated title.
        summary: Optional updated executive summary.
        recommendations: Optional updated strategic recommendations.
        period_start: Optional updated period start date (YYYY-MM-DD).
        period_end: Optional updated period end date (YYYY-MM-DD).
        impressions: Optional updated impressions count.
        clicks: Optional updated clicks count.
        leads: Optional updated leads count.
        spend: Optional updated advertising spend in USD.
        prev_impressions: Optional updated previous-period impressions.
        prev_clicks: Optional updated previous-period clicks.
        prev_leads: Optional updated previous-period leads.
        prev_spend: Optional updated previous-period spend in USD.
        status: Optional updated status ('draft' or 'published').

    Returns:
        The updated report record.
    """
    existing = database.get_report_by_id(report_id)
    if not existing:
        return {"error": True, "message": f"Report with ID '{report_id}' not found."}

    if status is not None and status not in ("draft", "published"):
        return {"error": True, "message": "Status must be 'draft' or 'published'."}
    if title is not None and not title.strip():
        return {"error": True, "message": "Report title cannot be empty."}

    text_fields = {"title": title, "summary": summary, "recommendations": recommendations}
    value_fields = {
        "period_start": period_start, "period_end": period_end,
        "impressions": impressions, "clicks": clicks, "leads": leads, "spend": spend,
        "prev_impressions": prev_impressions, "prev_clicks": prev_clicks,
        "prev_leads": prev_leads, "prev_spend": prev_spend, "status": status,
    }
    update_fields = {k: v.strip() for k, v in text_fields.items() if v is not None}
    update_fields.update({k: v for k, v in value_fields.items() if v is not None})

    try:
        updated = database.update_report(report_id, **update_fields)
        return {
            "success": True,
            "message": f"Report '{report_id}' updated successfully.",
            "report": updated
        }
    except Exception as e:
        return {"error": True, "message": f"Failed to update report: {str(e)}"}


# ==============================================================================
# TOOL 6: publish_report
# ==============================================================================
@mcp.tool(
    name="publish_report",
    title="Publish Report",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    description="Publish a report, making it active and returning a unique public shareable URL for the client."
)
def publish_report(report_id: str) -> Dict[str, Any]:
    """
    Publish a report and generate its public URL.

    Args:
        report_id: ID of the report to publish.

    Returns:
        The published report details including the public shareable URL.
    """
    existing = database.get_report_by_id(report_id)
    if not existing:
        return {"error": True, "message": f"Report with ID '{report_id}' not found."}

    try:
        published = database.publish_report(report_id)
        if published:
            return {
                "success": True,
                "message": f"Report '{published['title']}' published successfully.",
                "report_id": published["id"],
                "status": "published",
                "share_token": published["share_token"],
                "public_url": published.get("public_url")
            }
        return {"error": True, "message": "Failed to publish report."}
    except Exception as e:
        return {"error": True, "message": f"Failed to publish report: {str(e)}"}


# ==============================================================================
# TOOL 7: set_report_breakdown
# ==============================================================================
class BreakdownRow(BaseModel):
    label: str = Field(description="Row name: channel (e.g. 'Google Search', 'Meta'), campaign name, ad/creative name, or week start date (YYYY-MM-DD) for weekly rows.")
    platform: Optional[str] = Field(None, description="Ad platform, e.g. 'Google Ads' or 'Meta'.")
    impressions: int = Field(0, ge=0)
    clicks: int = Field(0, ge=0)
    leads: int = Field(0, ge=0)
    spend: float = Field(0.0, ge=0, description="Spend in USD for this row in the current period.")
    prev_spend: Optional[float] = Field(None, ge=0, description="Spend in the previous period, if known.")
    prev_leads: Optional[int] = Field(None, ge=0, description="Leads in the previous period, if known.")
    video_completion_rate: Optional[float] = Field(None, ge=0, le=100, description="Video completion rate in percent (video creatives only).")
    verdict: Optional[Literal["scale", "keep", "cut"]] = Field(None, description="Your recommendation for this row (mainly for creatives and campaigns).")
    note: Optional[str] = Field(None, description="One-line reason for the verdict or a notable observation.")


class KeyInsight(BaseModel):
    text: str = Field(description="Short insight, e.g. 'UGC testimonial video drove 37% of leads at $6.56 CPL'.")
    impact: str = Field("", description="Optional short metric chip, e.g. '+32%' or '-$41 CPL'.")
    tone: Literal["positive", "negative", "neutral"] = "neutral"


def _as_dicts(items) -> List[Dict[str, Any]]:
    return [i.model_dump() if hasattr(i, "model_dump") else dict(i) for i in items]


@mcp.tool(
    name="set_report_breakdown",
    title="Set Report Breakdown",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    description=(
        "Attach detailed breakdowns to a report so its dashboard shows channel split, per-campaign and per-creative "
        "tables, weekly trend charts, and key insights. Each list you pass REPLACES that section; omit a list to keep it."
    )
)
def set_report_breakdown(
    report_id: str,
    channels: Optional[List[BreakdownRow]] = None,
    campaigns: Optional[List[BreakdownRow]] = None,
    creatives: Optional[List[BreakdownRow]] = None,
    weekly: Optional[List[BreakdownRow]] = None,
    key_insights: Optional[List[KeyInsight]] = None
) -> Dict[str, Any]:
    """
    Set per-channel, per-campaign, per-creative, and weekly breakdown rows plus key insights for a report.

    Args:
        report_id: The report to attach the breakdown to.
        channels: One row per channel (e.g. Google Search, YouTube, Meta Prospecting, Meta Retargeting).
        campaigns: One row per campaign.
        creatives: One row per ad / video creative, ideally with verdict ('scale', 'keep', 'cut') and a note.
        weekly: One row per week in chronological order; label is the week start date (YYYY-MM-DD).
        key_insights: 3-5 headline insights for the dashboard's insights panel.

    Returns:
        Counts of rows stored per section.
    """
    if not database.get_report_by_id(report_id):
        return {"error": True, "message": f"Report with ID '{report_id}' not found."}

    sections = {"channel": channels, "campaign": campaigns, "creative": creatives, "week": weekly}
    if all(v is None for v in sections.values()) and key_insights is None:
        return {"error": True, "message": "Provide at least one of channels, campaigns, creatives, weekly, or key_insights."}

    try:
        stored = {}
        for dimension, rows in sections.items():
            if rows is not None:
                stored[dimension] = len(database.set_report_breakdown(report_id, dimension, _as_dicts(rows)))
        if key_insights is not None:
            stored["key_insights"] = len(database.set_report_insights(report_id, _as_dicts(key_insights)))
        return {"success": True, "message": "Report breakdown saved.", "report_id": report_id, "rows_stored": stored}
    except Exception as e:
        return {"error": True, "message": f"Failed to save breakdown: {str(e)}"}


# ==============================================================================
# TOOL 8: get_report
# ==============================================================================
@mcp.tool(
    name="get_report",
    title="Get Report",
    annotations={"readOnlyHint": True, "openWorldHint": False},
    description="Retrieve one report with its metrics, narrative, breakdown rows, and key insights."
)
def get_report(report_id: str) -> Dict[str, Any]:
    """
    Get a full report, e.g. to review or refine it.

    Args:
        report_id: The report ID.

    Returns:
        The report record, its breakdowns grouped by section, key insights, and public URL if published.
    """
    report = database.get_report_by_id(report_id)
    if not report:
        return {"error": True, "message": f"Report with ID '{report_id}' not found."}
    insights = database.get_report_insights(report)
    report = {k: v for k, v in report.items() if k != "key_insights"}
    return {
        "success": True,
        "report": report,
        "breakdowns": database.get_report_breakdowns(report_id),
        "key_insights": insights,
        "public_url": f"{database.PUBLIC_APP_URL}/?page=public&token={report['share_token']}"
        if report.get("status") == "published" else None,
    }


# ==============================================================================
# Server Execution
# ==============================================================================
def run_server():
    """Run FastMCP server with Streamable HTTP transport."""
    print(f"[*] Starting ClientPulse MCP Server on {MCP_HOST}:{MCP_PORT}")
    print(f"[*] Transport: Streamable HTTP ('streamable-http')")
    print(f"[*] Endpoint: http://{MCP_HOST}:{MCP_PORT}/mcp")
    db_info = database.get_db_info()
    print(f"[*] Database: {db_info['status_text']}")
    if db_info.get("supabase_unreachable"):
        print("[!] WARNING: Supabase is configured but unreachable. Writes go to a local SQLite file "
              "that the dashboard cannot see. Check SUPABASE_URL / SUPABASE_KEY.")
    if MCP_AUTH_TOKEN:
        print("[*] Auth: bearer token required (MCP_AUTH_TOKEN)")
    elif MCP_HOST not in ("127.0.0.1", "localhost"):
        print("[!] WARNING: MCP server is reachable from the network with NO authentication. Set MCP_AUTH_TOKEN.")
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT
    )


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        # Local stdio transport, used when Claude Desktop launches the server as a subprocess
        mcp.run(transport="stdio")
    else:
        run_server()
