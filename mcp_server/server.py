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
9. set_custom_dashboard
10. list_datasets
11. upload_dataset
12. profile_dataset
13. build_report_from_dataset

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
        "and weekly rows plus 3-5 key insights, so the dashboard charts and tables are populated. "
        "If the data is NOT ad performance (e.g. video/content, product, revenue or retention metrics), create the report "
        "with 0 for the ad metrics and call set_custom_dashboard to define the client's own KPI names and values, trend, "
        "split, rankings and table, using the column names and units from their data (e.g. LDAU, ARPU in INR, D30 retention). "
        "PREFERRED for raw data: never add up rows yourself. If the client's data is in ClientPulse (list_datasets) or you can "
        "upload it (upload_dataset), call profile_dataset, then build_report_from_dataset with a recipe describing the "
        "metrics; ClientPulse computes every number deterministically and returns them. Then write the summary, "
        "recommendations (update_report) and key insights (set_report_breakdown) using ONLY the returned numbers. "
        "For a client's next period, call build_report_from_dataset with just dataset_id, title and period: the saved "
        "template is reused so reports stay consistent month to month."
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
    impressions: int = 0,
    clicks: int = 0,
    leads: int = 0,
    spend: float = 0.0,
    summary: str = "",
    recommendations: str = "",
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
        impressions: Total ad impressions delivered in this period (0 if the data is not ad performance).
        clicks: Total ad clicks generated.
        leads: Total conversions / qualified leads generated.
        spend: Total advertising spend in USD.
        summary: Executive analysis. Formatting: short paragraphs; optional CAPS headings on their own line
            (e.g. HEADLINE); numbered points whose first sentence is the key insight (shown in bold); **bold** allowed.
        recommendations: Numbered, actionable recommendations ("1. Do X. Because Y."); the first sentence of each is shown in bold.
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
    spec_source = report
    report = {k: v for k, v in report.items() if k not in ("key_insights", "dashboard_spec")}
    return {
        "success": True,
        "report": report,
        "breakdowns": database.get_report_breakdowns(report_id),
        "key_insights": insights,
        "custom_dashboard": database.get_dashboard_spec(spec_source),
        "public_url": f"{database.PUBLIC_APP_URL}/?page=public&token={report['share_token']}"
        if report.get("status") == "published" else None,
    }


# ==============================================================================
# TOOL 9: set_custom_dashboard
# ==============================================================================
MetricFormat = Literal["number", "currency", "percent", "decimal"]


class CustomKPI(BaseModel):
    label: str = Field(description="KPI name exactly as the client uses it, e.g. 'LDAU', 'ARPU', 'D30 Retention'.")
    value: float = Field(description="Value for the current period.")
    prev: Optional[float] = Field(None, description="Value for the previous period, for the change indicator.")
    format: MetricFormat = Field("number", description="'currency' uses the dashboard currency symbol; 'percent' expects 0-100.")
    higher_is_better: Optional[bool] = Field(True, description="False for cost-like metrics; null for neutral.")


class TrendSeries(BaseModel):
    name: str
    values: List[float] = Field(description="One value per x label.")
    format: MetricFormat = "number"
    axis: Literal["left", "right"] = Field("left", description="Put a second series with a different unit on the right axis.")
    higher_is_better: Optional[bool] = True


class TrendChart(BaseModel):
    title: str = "Trend"
    x: List[str] = Field(description="Ordered x-axis labels, e.g. months '2026-07'... or week start dates.")
    series: List[TrendSeries] = Field(description="1-3 series.")


class LabelledChart(BaseModel):
    title: str
    labels: List[str]
    values: List[float]
    format: MetricFormat = "number"
    higher_is_better: Optional[bool] = True


class TableColumn(BaseModel):
    key: str = Field(description="Key used in each row's values, e.g. 'ldau'.")
    label: str = Field(description="Column header shown to the client, e.g. 'LDAU'.")
    format: MetricFormat = "number"


class TableRow(BaseModel):
    name: str
    values: Dict[str, Optional[float]] = Field(description="Map of column key to value.")
    verdict: Optional[Literal["scale", "keep", "cut"]] = None
    note: Optional[str] = None


class CustomTable(BaseModel):
    title: str = "Breakdown"
    columns: List[TableColumn]
    rows: List[TableRow]


@mcp.tool(
    name="set_custom_dashboard",
    title="Set Custom Dashboard",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    description=(
        "Define a report's dashboard around the client's OWN metrics instead of ad spend/leads: KPI cards with custom "
        "names and units, a trend chart, a split (donut) chart, up to 2 ranking bar charts, and a table with custom columns. "
        "Replaces any previous custom dashboard for the report. Pass reset=true to go back to the standard ad layout."
    )
)
def set_custom_dashboard(
    report_id: str,
    currency: str = "$",
    kpis: Optional[List[CustomKPI]] = None,
    trend: Optional[TrendChart] = None,
    split: Optional[LabelledChart] = None,
    rankings: Optional[List[LabelledChart]] = None,
    table: Optional[CustomTable] = None,
    reset: bool = False
) -> Dict[str, Any]:
    """
    Set the client-defined dashboard for a report.

    Args:
        report_id: The report to customise.
        currency: Symbol for 'currency' metrics, e.g. '$', '₹', '€'.
        kpis: 2-8 headline KPI cards with the client's metric names.
        trend: Time series chart (e.g. monthly LDAU and revenue).
        split: Share-of-total donut (e.g. revenue by duration bucket).
        rankings: Up to 2 ranked bar charts (e.g. D30 retention by video).
        table: Per-item table (e.g. one row per video) with custom columns, verdicts and notes.
        reset: If true, remove the custom dashboard and use the standard ad layout.

    Returns:
        Which sections were stored.
    """
    if not database.get_report_by_id(report_id):
        return {"error": True, "message": f"Report with ID '{report_id}' not found."}
    try:
        if reset:
            database.set_dashboard_spec(report_id, None)
            return {"success": True, "message": "Custom dashboard removed; the standard layout is back."}
        dump = lambda m: m.model_dump() if hasattr(m, "model_dump") else m
        spec = {
            "currency": currency,
            "kpis": [dump(k) for k in (kpis or [])],
            "trend": dump(trend) if trend else None,
            "split": dump(split) if split else None,
            "rankings": [dump(r) for r in (rankings or [])],
            "table": dump(table) if table else None,
        }
        stored = database.set_dashboard_spec(report_id, spec)
        sections = [k for k in ("kpis", "trend", "split", "rankings", "table") if stored.get(k)]
        return {"success": True, "message": "Custom dashboard saved.", "report_id": report_id, "sections": sections}
    except Exception as e:
        return {"error": True, "message": f"Failed to save custom dashboard: {str(e)}"}


# ==============================================================================
# TOOLS 10-13: datasets and deterministic report computation
# ==============================================================================
from utils.compute import RecipeError, load_csv, profile as profile_frame


@mcp.tool(
    name="list_datasets",
    title="List Datasets",
    annotations={"readOnlyHint": True, "openWorldHint": False},
    description="List raw data files (CSV) stored in ClientPulse, optionally for one client."
)
def list_datasets(client_id: Optional[str] = None) -> Dict[str, Any]:
    """
    List uploaded datasets.

    Args:
        client_id: Optional client filter.

    Returns:
        Datasets with id, name, row count, columns, and whether the client has a saved report template.
    """
    try:
        rows = database.list_datasets(client_id)
        for r in rows:
            r["has_template"] = database.get_report_template(r["client_id"]) is not None
        return {"success": True, "count": len(rows), "datasets": rows}
    except Exception as e:
        return {"error": True, "message": f"Failed to list datasets: {str(e)}"}


@mcp.tool(
    name="upload_dataset",
    title="Upload Dataset",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    description="Store a raw CSV for a client in ClientPulse so reports can be computed from it. Pass the CSV text exactly as given (max 5 MB)."
)
def upload_dataset(client_id: str, name: str, csv_text: str) -> Dict[str, Any]:
    """
    Upload raw CSV data for a client.

    Args:
        client_id: Client the data belongs to.
        name: File name, e.g. 'meta_google_oct_2026.csv'.
        csv_text: The full CSV including the header row.

    Returns:
        The stored dataset (id, columns, row count).
    """
    try:
        return {"success": True, "dataset": database.create_dataset(client_id, name, csv_text)}
    except Exception as e:
        return {"error": True, "message": f"Failed to upload dataset: {str(e)}"}


@mcp.tool(
    name="profile_dataset",
    title="Profile Dataset",
    annotations={"readOnlyHint": True, "openWorldHint": False},
    description="Describe a dataset's columns (type, ranges, top values) and sample rows so you can write a recipe."
)
def profile_dataset(dataset_id: str) -> Dict[str, Any]:
    """
    Profile a stored dataset.

    Args:
        dataset_id: Dataset to describe.

    Returns:
        Row count, per-column type/range/top values, 5 sample rows, and the client's saved template if any.
    """
    ds = database.get_dataset(dataset_id)
    if not ds:
        return {"error": True, "message": f"Dataset '{dataset_id}' not found."}
    try:
        return {"success": True, "dataset_id": dataset_id, "name": ds["name"], **profile_frame(load_csv(ds["csv_text"])),
                "saved_template": database.get_report_template(ds["client_id"])}
    except Exception as e:
        return {"error": True, "message": f"Failed to profile dataset: {str(e)}"}


class Period(BaseModel):
    start: str = Field(description="YYYY-MM-DD, inclusive.")
    end: str = Field(description="YYYY-MM-DD, inclusive.")


class RecipeMetric(BaseModel):
    key: str = Field(description="Short id, e.g. 'spend', 'cpl', 'arpu'. Keys spend/impressions/clicks/leads also fill the report's standard fields.")
    label: str = Field(description="Name shown to the client, e.g. 'Cost per Lead'.")
    agg: Literal["sum", "mean", "weighted_mean", "ratio", "count", "min", "max", "last"] = "sum"
    column: Optional[str] = Field(None, description="Source column (all aggs except ratio and count).")
    weight: Optional[str] = Field(None, description="Weight column for weighted_mean, e.g. 'ldau'.")
    numerator: Optional[str] = Field(None, description="Metric key on top, for ratio.")
    denominator: Optional[str] = Field(None, description="Metric key below, for ratio.")
    scale: float = Field(1.0, description="Multiplier for ratio, e.g. 100 for a percentage.")
    format: Literal["number", "currency", "percent", "decimal"] = "number"
    higher_is_better: Optional[bool] = True


class RecipeTrend(BaseModel):
    granularity: Literal["day", "week", "month"] = "week"
    metrics: List[str] = Field(description="1-3 metric keys.")
    range: Optional[Literal["current", "all"]] = Field(None, description="'current' = report period only; 'all' = history up to period end. Default: all for month, current otherwise.")
    title: Optional[str] = None


class RecipeDimension(BaseModel):
    dimension: str = Field(description="Column to group by, e.g. 'platform', 'duration_bucket'.")
    metric: str = Field(description="Metric key to show.")
    title: Optional[str] = None


class RecipeTable(BaseModel):
    dimension: str = Field(description="Column with one row per item, e.g. 'ad_name' or 'video_title'.")
    metrics: List[str] = Field(description="Metric keys as columns (max 10).")
    sort_by: Optional[str] = None
    title: Optional[str] = None


class RecipeFilter(BaseModel):
    column: str
    values: List[str]


class RowVerdict(BaseModel):
    name: str = Field(description="Exact value in the table dimension column, e.g. the video title.")
    verdict: Literal["scale", "keep", "cut"]
    note: Optional[str] = None


@mcp.tool(
    name="build_report_from_dataset",
    title="Build Report From Dataset",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    description=(
        "Create (or recompute) a report whose numbers ClientPulse computes itself from a stored dataset. You describe "
        "the data with a recipe (date column, metrics with aggregations, KPIs, trend, split, rankings, table, verdicts); "
        "you never do the arithmetic. Omit metrics to reuse the client's saved template (same KPIs every month). "
        "Returns the computed KPIs, table rows, and formulas: use only these numbers in the narrative."
    )
)
def build_report_from_dataset(
    dataset_id: str,
    title: str,
    period: Period,
    compare_period: Optional[Period] = None,
    date_column: Optional[str] = None,
    metrics: Optional[List[RecipeMetric]] = None,
    kpis: Optional[List[str]] = None,
    trend: Optional[RecipeTrend] = None,
    split: Optional[RecipeDimension] = None,
    rankings: Optional[List[RecipeDimension]] = None,
    table: Optional[RecipeTable] = None,
    filters: Optional[List[RecipeFilter]] = None,
    currency: str = "$",
    verdicts: Optional[List[RowVerdict]] = None,
    status: Literal["draft", "published"] = "draft",
    summary: str = "",
    recommendations: str = "",
    report_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compute a report from raw data with ClientPulse's deterministic engine.

    Args:
        dataset_id: Dataset to compute from.
        title: Report title.
        period: Current reporting period.
        compare_period: Previous period for change indicators.
        date_column: Column holding dates or months. Required unless a saved template exists.
        metrics: Metric definitions. Omit to reuse the client's saved template.
        kpis: Metric keys for the KPI cards (max 8).
        trend: Trend chart definition.
        split: Donut chart: one metric split by a dimension.
        rankings: Up to 2 ranked bar charts.
        table: Per-item table.
        filters: Keep only rows whose column value is in the list.
        currency: Symbol for currency metrics, e.g. '$', '₹'.
        verdicts: Your Scale/Keep/Cut judgement per table row.
        status: 'draft' or 'published'.
        summary: Optional executive summary (better: write it after seeing the returned numbers, via update_report).
        recommendations: Optional recommendations.
        report_id: Recompute an existing report instead of creating a new one.

    Returns:
        report_id, public_url, computed KPIs, table rows, and the formula behind every metric.
    """
    ds = database.get_dataset(dataset_id)
    if not ds:
        return {"error": True, "message": f"Dataset '{dataset_id}' not found."}
    dump = lambda m: m.model_dump() if hasattr(m, "model_dump") else dict(m)

    recipe: Dict[str, Any] = {}
    if metrics is None:
        template = database.get_report_template(ds["client_id"])
        if not template:
            return {"error": True, "message": "No saved template for this client. Call profile_dataset and pass metrics."}
        recipe.update(template)
    overrides = {
        "date_column": date_column, "metrics": [dump(m) for m in metrics] if metrics is not None else None,
        "kpis": kpis, "trend": dump(trend) if trend else None, "split": dump(split) if split else None,
        "rankings": [dump(r) for r in rankings] if rankings is not None else None,
        "table": dump(table) if table else None, "filters": [dump(f) for f in filters] if filters is not None else None,
    }
    recipe.update({k: v for k, v in overrides.items() if v is not None})
    if metrics is not None or "currency" not in recipe:
        recipe["currency"] = currency
    recipe["period"] = dump(period)
    recipe["compare_period"] = dump(compare_period) if compare_period else None
    recipe["verdicts"] = {v["name"]: {"verdict": v["verdict"], "note": v.get("note")} for v in map(dump, verdicts or [])}

    try:
        result = database.build_report_from_dataset(dataset_id, recipe, title=title, status=status, summary=summary,
                                                     recommendations=recommendations, report_id=report_id)
    except (RecipeError, ValueError) as e:
        return {"error": True, "message": f"Could not compute report: {str(e)}"}
    except Exception as e:
        return {"error": True, "message": f"Failed to build report: {str(e)}"}

    report = result["report"]
    spec = result["spec"]
    return {
        "success": True,
        "report_id": report["id"],
        "public_url": f"{database.PUBLIC_APP_URL}/?page=public&token={report['share_token']}" if report["status"] == "published" else None,
        "kpis": spec.get("kpis"),
        "table_rows": (spec.get("table") or {}).get("rows", [])[:25],
        "rankings": spec.get("rankings"),
        "audit": result["audit"],
        "next_step": "Write the summary and recommendations with update_report and 3-5 key insights with "
                     "set_report_breakdown, quoting only these computed numbers.",
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
