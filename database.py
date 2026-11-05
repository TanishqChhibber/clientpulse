"""
ClientPulse - Database Layer
============================
Provides unified persistence for ClientPulse using Supabase PostgreSQL,
with an automatic fallback to local persistent SQLite when Supabase
credentials are not configured or unreachable.

Both backends share identical function signatures, schema validation,
and return clean Python dictionaries.
"""

import logging
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("clientpulse.database")

# Database file path for local SQLite engine (override with CLIENTPULSE_DB_PATH, e.g. for tests)
BASE_DIR = Path(__file__).resolve().parent
SQLITE_DB_PATH = Path(os.getenv("CLIENTPULSE_DB_PATH") or (BASE_DIR / "clientpulse.db"))

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8501").rstrip("/")

_supabase_client = None
_db_mode = None  # "supabase" or "sqlite"


def get_current_utc_iso() -> str:
    """Return current UTC timestamp in ISO 8601 string format."""
    return datetime.now(timezone.utc).isoformat()


def _warn_supabase_fallback(operation: str, exc: Exception) -> None:
    """Log a Supabase failure so a silent fallback to SQLite is visible in the server logs."""
    logger.warning("Supabase %s failed, falling back to local SQLite: %s", operation, exc)


# ==============================================================================
# Supabase Client Initialization
# ==============================================================================

def init_supabase():
    """Attempt to initialize the Supabase client."""
    global _supabase_client, _db_mode
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL.startswith("http"):
        try:
            from supabase import create_client
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Test connectivity with a lightweight ping
            _supabase_client.table("clients").select("id").limit(1).execute()
            _db_mode = "supabase"
            return _supabase_client
        except Exception as e:
            # Fall back to sqlite if Supabase is misconfigured or tables not yet created
            _warn_supabase_fallback("connection check", e)
            _supabase_client = None
            _db_mode = "sqlite"
            return None
    else:
        _db_mode = "sqlite"
        return None


# ==============================================================================
# SQLite Engine Initialization
# ==============================================================================

def get_sqlite_conn() -> sqlite3.Connection:
    """Create and return a thread-safe connection to the local SQLite database."""
    conn = sqlite3.connect(str(SQLITE_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_sqlite_schema():
    """Create SQLite tables if they do not exist."""
    conn = get_sqlite_conn()
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            industry TEXT,
            website TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reports (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            period_start TEXT NOT NULL,
            period_end TEXT NOT NULL,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            leads INTEGER NOT NULL DEFAULT 0,
            spend REAL NOT NULL DEFAULT 0.0,
            ctr REAL NOT NULL DEFAULT 0.0,
            cpl REAL NOT NULL DEFAULT 0.0,
            conversion_rate REAL NOT NULL DEFAULT 0.0,
            prev_impressions INTEGER NOT NULL DEFAULT 0,
            prev_clicks INTEGER NOT NULL DEFAULT 0,
            prev_leads INTEGER NOT NULL DEFAULT 0,
            prev_spend REAL NOT NULL DEFAULT 0.0,
            summary TEXT,
            recommendations TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
            share_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS activity_logs (
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
        CREATE INDEX IF NOT EXISTS idx_reports_client_id ON reports(client_id);
        CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
        CREATE INDEX IF NOT EXISTS idx_reports_share_token ON reports(share_token);
        CREATE INDEX IF NOT EXISTS idx_activity_created_at ON activity_logs(created_at DESC);
        """)
    conn.close()


# Ensure SQLite schema is prepared at module import
init_sqlite_schema()
init_supabase()


def get_db_info() -> Dict[str, Any]:
    """Return database engine status for UI badges and diagnostics."""
    if _db_mode == "supabase" and _supabase_client is not None:
        return {
            "engine": "supabase",
            "name": "Supabase PostgreSQL",
            "url": SUPABASE_URL,
            "connected": True,
            "badge_color": "green",
            "status_text": "Supabase PostgreSQL (Live)"
        }
    return {
        "engine": "sqlite",
        "name": "Local SQLite Engine",
        "path": str(SQLITE_DB_PATH),
        "connected": True,
        "badge_color": "purple",
        "status_text": "Local Engine (Ready for Supabase)",
        # True when Supabase credentials exist but the connection failed (silent split-brain risk)
        "supabase_unreachable": bool(SUPABASE_URL and SUPABASE_KEY)
    }


# ==============================================================================
# Metric Computation Helper
# ==============================================================================

def calculate_derived_metrics(impressions: int, clicks: int, leads: int, spend: float) -> Dict[str, float]:
    """
    Compute derived performance metrics:
    - CTR (%): (clicks / impressions) * 100
    - CPL ($): (spend / leads)
    - Conversion Rate (%): (leads / clicks) * 100
    """
    ctr = round((clicks / impressions * 100.0), 2) if impressions > 0 else 0.0
    cpl = round((spend / leads), 2) if leads > 0 else 0.0
    conversion_rate = round((leads / clicks * 100.0), 2) if clicks > 0 else 0.0
    return {
        "ctr": ctr,
        "cpl": cpl,
        "conversion_rate": conversion_rate
    }


def _validate_report_fields(fields: Dict[str, Any]) -> None:
    """Reject negative metrics, unknown statuses, and reporting periods that end before they start."""
    for key in ("impressions", "clicks", "leads", "spend",
                "prev_impressions", "prev_clicks", "prev_leads", "prev_spend"):
        if key in fields and fields[key] is not None and float(fields[key]) < 0:
            raise ValueError(f"'{key}' cannot be negative.")

    if "status" in fields and fields["status"] not in ("draft", "published"):
        raise ValueError("Report status must be 'draft' or 'published'.")

    parsed = {}
    for key in ("period_start", "period_end"):
        if fields.get(key) is not None:
            try:
                parsed[key] = date.fromisoformat(str(fields[key]))
            except ValueError:
                raise ValueError(f"'{key}' must be a date in YYYY-MM-DD format.")
    if len(parsed) == 2 and parsed["period_end"] < parsed["period_start"]:
        raise ValueError("Reporting period end date cannot be before the start date.")


# ==============================================================================
# Client Management CRUD
# ==============================================================================

def create_client(
    name: str,
    email: Optional[str] = "",
    industry: Optional[str] = "",
    website: Optional[str] = "",
    notes: Optional[str] = "",
    status: str = "active"
) -> Dict[str, Any]:
    """
    Add a new agency client.
    Performs real database insert and logs activity.
    """
    client_id = f"cli_{uuid.uuid4().hex[:12]}"
    now_iso = get_current_utc_iso()
    client_data = {
        "id": client_id,
        "name": (name or "").strip(),
        "email": (email or "").strip(),
        "industry": (industry or "").strip(),
        "website": (website or "").strip(),
        "notes": (notes or "").strip(),
        "status": status if status in ("active", "inactive") else "active",
        "created_at": now_iso,
        "updated_at": now_iso
    }

    if not client_data["name"]:
        raise ValueError("Client name is required and cannot be empty.")

    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("clients").insert(client_data).execute()
            if res.data:
                client_data = res.data[0]
        except Exception as e:
            # Fallback to sqlite if remote execution fails
            _warn_supabase_fallback("create_client", e)
            _insert_client_sqlite(client_data)
    else:
        _insert_client_sqlite(client_data)

    log_activity("client_created", "client", client_id, f"Client '{client_data['name']}' added.")
    return client_data


def _insert_client_sqlite(client_data: Dict[str, Any]):
    conn = get_sqlite_conn()
    with conn:
        conn.execute("""
            INSERT INTO clients (id, name, email, industry, website, notes, status, created_at, updated_at)
            VALUES (:id, :name, :email, :industry, :website, :notes, :status, :created_at, :updated_at)
        """, client_data)
    conn.close()


def get_clients(status: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all clients with optional filtering by status and search query."""
    if _db_mode == "supabase" and _supabase_client:
        try:
            query = _supabase_client.table("clients").select("*").order("created_at", desc=True)
            if status and status != "all":
                query = query.eq("status", status)
            if search:
                query = query.ilike("name", f"%{search}%")
            res = query.execute()
            return res.data or []
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    base_query = "SELECT * FROM clients WHERE 1=1"
    params: List[Any] = []

    if status and status != "all":
        base_query += " AND status = ?"
        params.append(status)

    if search:
        base_query += " AND (name LIKE ? OR industry LIKE ? OR email LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    base_query += " ORDER BY created_at DESC"
    cursor = conn.execute(base_query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_client_by_id(client_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single client by ID."""
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("clients").select("*").eq("id", client_id).limit(1).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    cursor = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_client(client_id: str, **fields) -> Optional[Dict[str, Any]]:
    """Update fields for a specific client."""
    allowed = {"name", "email", "industry", "website", "notes", "status"}
    update_data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not update_data:
        return get_client_by_id(client_id)

    update_data["updated_at"] = get_current_utc_iso()

    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("clients").update(update_data).eq("id", client_id).execute()
            if res.data:
                log_activity("client_updated", "client", client_id, f"Client {client_id} updated.")
                return res.data[0]
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
    params = list(update_data.values()) + [client_id]
    with conn:
        conn.execute(f"UPDATE clients SET {set_clause} WHERE id = ?", params)
    conn.close()

    log_activity("client_updated", "client", client_id, f"Client {client_id} updated.")
    return get_client_by_id(client_id)


def delete_client(client_id: str) -> bool:
    """Delete a client and cascade-delete its reports."""
    client = get_client_by_id(client_id)
    if not client:
        return False

    client_name = client.get("name", client_id)

    if _db_mode == "supabase" and _supabase_client:
        try:
            # Delete child reports first if foreign key cascade is not enabled
            _supabase_client.table("reports").delete().eq("client_id", client_id).execute()
            _supabase_client.table("clients").delete().eq("id", client_id).execute()
            log_activity("client_deleted", "client", client_id, f"Client '{client_name}' and reports deleted.")
            return True
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    with conn:
        conn.execute("DELETE FROM reports WHERE client_id = ?", (client_id,))
        conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    conn.close()

    log_activity("client_deleted", "client", client_id, f"Client '{client_name}' and reports deleted.")
    return True


# ==============================================================================
# Report Management CRUD
# ==============================================================================

def create_report(
    client_id: str,
    title: str,
    period_start: str,
    period_end: str,
    impressions: int,
    clicks: int,
    leads: int,
    spend: float,
    summary: str = "",
    recommendations: str = "",
    prev_impressions: int = 0,
    prev_clicks: int = 0,
    prev_leads: int = 0,
    prev_spend: float = 0.0,
    status: str = "draft"
) -> Dict[str, Any]:
    """
    Create a campaign marketing performance report.
    Automatically calculates CTR, CPL, and conversion rates.
    Generates a unique share token for public viewing.
    """
    # Verify client exists
    client = get_client_by_id(client_id)
    if not client:
        raise ValueError(f"Client with id '{client_id}' does not exist.")

    _validate_report_fields({
        "impressions": impressions, "clicks": clicks, "leads": leads, "spend": spend,
        "prev_impressions": prev_impressions, "prev_clicks": prev_clicks,
        "prev_leads": prev_leads, "prev_spend": prev_spend,
        "period_start": period_start, "period_end": period_end,
    })

    report_id = f"rep_{uuid.uuid4().hex[:12]}"
    share_token = uuid.uuid4().hex[:16]
    now_iso = get_current_utc_iso()

    # Derived metrics
    derived = calculate_derived_metrics(
        impressions=int(impressions or 0),
        clicks=int(clicks or 0),
        leads=int(leads or 0),
        spend=float(spend or 0.0)
    )

    report_data = {
        "id": report_id,
        "client_id": client_id,
        "title": (title or "Campaign Performance Report").strip(),
        "period_start": str(period_start),
        "period_end": str(period_end),
        "impressions": int(impressions or 0),
        "clicks": int(clicks or 0),
        "leads": int(leads or 0),
        "spend": round(float(spend or 0.0), 2),
        "ctr": derived["ctr"],
        "cpl": derived["cpl"],
        "conversion_rate": derived["conversion_rate"],
        "prev_impressions": int(prev_impressions or 0),
        "prev_clicks": int(prev_clicks or 0),
        "prev_leads": int(prev_leads or 0),
        "prev_spend": round(float(prev_spend or 0.0), 2),
        "summary": (summary or "").strip(),
        "recommendations": (recommendations or "").strip(),
        "status": status if status in ("draft", "published") else "draft",
        "share_token": share_token,
        "created_at": now_iso,
        "updated_at": now_iso
    }

    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("reports").insert(report_data).execute()
            if res.data:
                report_data = res.data[0]
        except Exception as e:
            _warn_supabase_fallback("create_report", e)
            _insert_report_sqlite(report_data)
    else:
        _insert_report_sqlite(report_data)

    log_activity(
        "report_created",
        "report",
        report_id,
        f"Created {report_data['status']} report '{report_data['title']}' for {client.get('name')}."
    )
    return report_data


def _insert_report_sqlite(report_data: Dict[str, Any]):
    conn = get_sqlite_conn()
    with conn:
        conn.execute("""
            INSERT INTO reports (
                id, client_id, title, period_start, period_end,
                impressions, clicks, leads, spend, ctr, cpl, conversion_rate,
                prev_impressions, prev_clicks, prev_leads, prev_spend,
                summary, recommendations, status, share_token, created_at, updated_at
            ) VALUES (
                :id, :client_id, :title, :period_start, :period_end,
                :impressions, :clicks, :leads, :spend, :ctr, :cpl, :conversion_rate,
                :prev_impressions, :prev_clicks, :prev_leads, :prev_spend,
                :summary, :recommendations, :status, :share_token, :created_at, :updated_at
            )
        """, report_data)
    conn.close()


def get_reports(
    client_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve reports with attached client name, filtered by client, status, and search query.
    """
    if _db_mode == "supabase" and _supabase_client:
        try:
            query = _supabase_client.table("reports").select("*, clients(name, industry)").order("created_at", desc=True)
            if client_id and client_id != "all":
                query = query.eq("client_id", client_id)
            if status and status != "all":
                query = query.eq("status", status)
            if search:
                query = query.ilike("title", f"%{search}%")
            res = query.execute()
            reports = []
            for r in (res.data or []):
                r_dict = dict(r)
                client_info = r_dict.pop("clients", None) or {}
                r_dict["client_name"] = client_info.get("name", "Unknown Client")
                r_dict["client_industry"] = client_info.get("industry", "")
                reports.append(r_dict)
            return reports
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    query = """
        SELECT r.*, c.name as client_name, c.industry as client_industry
        FROM reports r
        JOIN clients c ON r.client_id = c.id
        WHERE 1=1
    """
    params: List[Any] = []

    if client_id and client_id != "all":
        query += " AND r.client_id = ?"
        params.append(client_id)

    if status and status != "all":
        query += " AND r.status = ?"
        params.append(status)

    if search:
        query += " AND (r.title LIKE ? OR c.name LIKE ? OR r.summary LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])

    query += " ORDER BY r.created_at DESC"
    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_report_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve single report by ID along with client details."""
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("reports").select("*, clients(name, email, industry, website)").eq("id", report_id).limit(1).execute()
            if res.data:
                r_dict = dict(res.data[0])
                client_info = r_dict.pop("clients", None) or {}
                r_dict["client_name"] = client_info.get("name", "Unknown Client")
                r_dict["client_email"] = client_info.get("email", "")
                r_dict["client_industry"] = client_info.get("industry", "")
                r_dict["client_website"] = client_info.get("website", "")
                return r_dict
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    cursor = conn.execute("""
        SELECT r.*, c.name as client_name, c.email as client_email,
               c.industry as client_industry, c.website as client_website
        FROM reports r
        JOIN clients c ON r.client_id = c.id
        WHERE r.id = ?
    """, (report_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_report_by_share_token(share_token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve published report by public share token.
    Enforces that unpublished reports cannot be accessed via public token.
    """
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("reports").select("*, clients(name, email, industry, website)").eq("share_token", share_token).eq("status", "published").limit(1).execute()
            if res.data:
                r_dict = dict(res.data[0])
                client_info = r_dict.pop("clients", None) or {}
                r_dict["client_name"] = client_info.get("name", "Client")
                r_dict["client_email"] = client_info.get("email", "")
                r_dict["client_industry"] = client_info.get("industry", "")
                r_dict["client_website"] = client_info.get("website", "")
                return r_dict
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    cursor = conn.execute("""
        SELECT r.*, c.name as client_name, c.email as client_email,
               c.industry as client_industry, c.website as client_website
        FROM reports r
        JOIN clients c ON r.client_id = c.id
        WHERE r.share_token = ? AND r.status = 'published'
    """, (share_token,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_report(report_id: str, **fields) -> Optional[Dict[str, Any]]:
    """
    Update a report. Recalculates CTR and CPL if numerical metrics change.
    """
    current = get_report_by_id(report_id)
    if not current:
        return None

    allowed = {
        "title", "period_start", "period_end", "impressions", "clicks",
        "leads", "spend", "prev_impressions", "prev_clicks", "prev_leads",
        "prev_spend", "summary", "recommendations", "status"
    }
    update_data = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not update_data:
        return current

    _validate_report_fields({
        **update_data,
        "period_start": update_data.get("period_start", current["period_start"]),
        "period_end": update_data.get("period_end", current["period_end"]),
    })

    # Recompute metrics if impressions, clicks, leads, or spend are being updated
    impressions = int(update_data.get("impressions", current["impressions"]))
    clicks = int(update_data.get("clicks", current["clicks"]))
    leads = int(update_data.get("leads", current["leads"]))
    spend = float(update_data.get("spend", current["spend"]))

    derived = calculate_derived_metrics(impressions, clicks, leads, spend)
    update_data["ctr"] = derived["ctr"]
    update_data["cpl"] = derived["cpl"]
    update_data["conversion_rate"] = derived["conversion_rate"]
    update_data["updated_at"] = get_current_utc_iso()

    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("reports").update(update_data).eq("id", report_id).execute()
            if res.data:
                log_activity("report_updated", "report", report_id, f"Report '{report_id}' updated.")
                return get_report_by_id(report_id)
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
    params = list(update_data.values()) + [report_id]
    with conn:
        conn.execute(f"UPDATE reports SET {set_clause} WHERE id = ?", params)
    conn.close()

    log_activity("report_updated", "report", report_id, f"Report '{report_id}' updated.")
    return get_report_by_id(report_id)


def publish_report(report_id: str) -> Optional[Dict[str, Any]]:
    """
    Mark a report as published and return public shareable link.
    """
    report = get_report_by_id(report_id)
    if not report:
        return None

    updated = update_report(report_id, status="published")
    if updated:
        share_url = f"{PUBLIC_APP_URL}/?page=public&token={updated['share_token']}"
        updated["public_url"] = share_url
        log_activity(
            "report_published",
            "report",
            report_id,
            f"Published report '{updated['title']}'. Public URL generated."
        )
        return updated
    return None


def delete_report(report_id: str) -> bool:
    """Delete a report by ID."""
    report = get_report_by_id(report_id)
    if not report:
        return False

    title = report.get("title", report_id)

    if _db_mode == "supabase" and _supabase_client:
        try:
            _supabase_client.table("reports").delete().eq("id", report_id).execute()
            log_activity("report_deleted", "report", report_id, f"Report '{title}' deleted.")
            return True
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    with conn:
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.close()

    log_activity("report_deleted", "report", report_id, f"Report '{title}' deleted.")
    return True


# ==============================================================================
# Activity Logs
# ==============================================================================

def log_activity(action: str, entity_type: str, entity_id: str, details: str) -> None:
    """Record an operational activity in the audit feed."""
    log_id = f"act_{uuid.uuid4().hex[:12]}"
    now_iso = get_current_utc_iso()
    log_data = {
        "id": log_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "created_at": now_iso
    }

    if _db_mode == "supabase" and _supabase_client:
        try:
            _supabase_client.table("activity_logs").insert(log_data).execute()
            return
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    with conn:
        conn.execute("""
            INSERT INTO activity_logs (id, action, entity_type, entity_id, details, created_at)
            VALUES (:id, :action, :entity_type, :entity_id, :details, :created_at)
        """, log_data)
    conn.close()


def get_recent_activity(limit: int = 8) -> List[Dict[str, Any]]:
    """Retrieve the most recent agency activity events."""
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("activity_logs").select("*").order("created_at", desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            _warn_supabase_fallback("query", e)

    conn = get_sqlite_conn()
    cursor = conn.execute(
        "SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


# ==============================================================================
# Dashboard Analytics Aggregations
# ==============================================================================

def get_dashboard_metrics() -> Dict[str, Any]:
    """
    Calculate top-level business and reporting metrics for the Overview Dashboard.
    """
    clients = get_clients()
    reports = get_reports()

    total_clients = len(clients)
    active_clients = len([c for c in clients if c.get("status") == "active"])

    total_reports = len(reports)
    published_reports = len([r for r in reports if r.get("status") == "published"])
    draft_reports = len([r for r in reports if r.get("status") == "draft"])

    total_spend = sum(float(r.get("spend", 0.0)) for r in reports)
    total_leads = sum(int(r.get("leads", 0)) for r in reports)
    total_impressions = sum(int(r.get("impressions", 0)) for r in reports)
    total_clicks = sum(int(r.get("clicks", 0)) for r in reports)

    avg_ctr = round((total_clicks / total_impressions * 100), 2) if total_impressions > 0 else 0.0
    avg_cpl = round((total_spend / total_leads), 2) if total_leads > 0 else 0.0

    return {
        "total_clients": total_clients,
        "active_clients": active_clients,
        "total_reports": total_reports,
        "published_reports": published_reports,
        "draft_reports": draft_reports,
        "total_spend": total_spend,
        "total_leads": total_leads,
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "avg_ctr": avg_ctr,
        "avg_cpl": avg_cpl,
    }


# ==============================================================================
# Explicit Demo Seeder
# ==============================================================================

def seed_demo_data(force: bool = False) -> Dict[str, int]:
    """
    Populate realistic demo agency clients and campaign reports.
    Only seeds if the database is currently empty unless force=True.
    When force=True, existing records are cleared first to prevent duplicate bloat.
    """
    existing_clients = get_clients()
    if existing_clients and not force:
        return {"clients_created": 0, "reports_created": 0, "message": "Database already contains clients. Use force=True to re-seed."}

    if force:
        if _db_mode == "supabase" and _supabase_client:
            try:
                _supabase_client.table("reports").delete().neq("id", "0").execute()
                _supabase_client.table("clients").delete().neq("id", "0").execute()
                _supabase_client.table("activity_logs").delete().neq("id", "0").execute()
            except Exception as e:
                _warn_supabase_fallback("query", e)
        conn = get_sqlite_conn()
        with conn:
            conn.execute("DELETE FROM reports;")
            conn.execute("DELETE FROM clients;")
            conn.execute("DELETE FROM activity_logs;")
        conn.close()

    demo_clients = [
        {
            "name": "TechFlow Cloud",
            "email": "sarah.chen@techflowcloud.io",
            "industry": "B2B SaaS / DevOps",
            "website": "https://techflowcloud.io",
            "notes": "Target CPL under $35. Focused on Google Search and LinkedIn Sponsored Content.",
            "status": "active"
        },
        {
            "name": "Aurora Luxury Apparel",
            "email": "marketing@aurora-apparel.com",
            "industry": "DTC Fashion / E-Commerce",
            "website": "https://aurora-apparel.com",
            "notes": "Scaling Meta Advantage+ and TikTok Shop campaigns. Key KPI is blended ROAS > 3.4x.",
            "status": "active"
        },
        {
            "name": "Nexus Telehealth",
            "email": "growth@nexustelehealth.com",
            "industry": "Digital Health & Telemedicine",
            "website": "https://nexustelehealth.com",
            "notes": "HIPAA compliant ad creative. Primary goal is booked initial consultations.",
            "status": "active"
        },
        {
            "name": "Vanguard Private Wealth",
            "email": "inquiries@vanguardwealth-demo.com",
            "industry": "Fintech / Wealth Management",
            "website": "https://vanguardwealth-demo.com",
            "notes": "High Net Worth (HNW) investor acquisitions via Google Ads & Bloomberg programmatic.",
            "status": "inactive"
        }
    ]

    created_client_ids = []
    for c in demo_clients:
        res = create_client(**c)
        created_client_ids.append(res["id"])

    demo_reports = [
        {
            "client_id": created_client_ids[0],
            "title": "Q3 2026 SaaS Pipeline Generation & Growth Report",
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "impressions": 580000,
            "clicks": 18450,
            "leads": 920,
            "spend": 24800.00,
            "prev_impressions": 490000,
            "prev_clicks": 14200,
            "prev_leads": 680,
            "prev_spend": 21500.00,
            "summary": "Q3 performance delivered exceptional bottom-funnel expansion. LinkedIn InMail and Google Intent Search generated 920 qualified enterprise leads, representing a 35.3% growth in lead volume over Q2. CPL dropped from $31.62 to $26.96 due to high-converting landing page variants and negative keyword pruning.",
            "recommendations": "1. Scale budget by 20% on top 3 high-intent Google Search clusters ('Kubernetes observability tools').\n2. Introduce interactive ROI calculator on primary demo landing page to boost conversion rate beyond 5.0%.\n3. Roll out quarterly thought leadership carousel ads featuring customer case studies.",
            "status": "published"
        },
        {
            "client_id": created_client_ids[0],
            "title": "October 2026 Sprint: Enterprise Retargeting",
            "period_start": "2026-10-01",
            "period_end": "2026-10-31",
            "impressions": 165000,
            "clicks": 5400,
            "leads": 285,
            "spend": 8200.00,
            "prev_impressions": 145000,
            "prev_clicks": 4600,
            "prev_leads": 220,
            "prev_spend": 7400.00,
            "summary": "Mid-funnel retargeting achieved a strong 3.27% CTR. Video testimonials drove 64% of all demo requests. Sales velocity for influenced pipeline increased by 11 days.",
            "recommendations": "Expand audience segment to include webinar attendees from Q3 with customized booking offers.",
            "status": "draft"
        },
        {
            "client_id": created_client_ids[1],
            "title": "Fall Season Paid Social & ROAS Performance Report",
            "period_start": "2026-09-01",
            "period_end": "2026-09-30",
            "impressions": 840000,
            "clicks": 31200,
            "leads": 1640,
            "spend": 32500.00,
            "prev_impressions": 720000,
            "prev_clicks": 25100,
            "prev_leads": 1280,
            "prev_spend": 29000.00,
            "summary": "September seasonal campaign broke previous customer acquisition records. Meta Advantage+ catalog ads produced an estimated 3.8x ROAS. TikTok creator UGC outperformed static lifestyle images by 4.1x in engagement and drove 720 direct purchase conversions.",
            "recommendations": "1. Double down on creator UGC whitelisting for Black Friday prep.\n2. Implement Klaviyo abandoned-cart SMS trigger to recapture 15% more warm checkout traffic.\n3. Test dynamic bundle discounts for order values > $150.",
            "status": "published"
        },
        {
            "client_id": created_client_ids[2],
            "title": "Q3 2026 Telehealth Patient Acquisition Report",
            "period_start": "2026-07-01",
            "period_end": "2026-09-30",
            "impressions": 420000,
            "clicks": 13900,
            "leads": 710,
            "spend": 19500.00,
            "prev_impressions": 390000,
            "prev_clicks": 11800,
            "prev_leads": 560,
            "prev_spend": 18200.00,
            "summary": "Patient intake campaigns saw consistent improvements across metropolitan target geos. Cost per consultation scheduled decreased by 15.4% while maintaining patient qualification score of 91%. Localized Google Local Services Ads proved to be the most cost-effective channel at $18.40 CPL.",
            "recommendations": "1. Expand Spanish language ad sets in Florida and Texas markets.\n2. Enhance post-click booking calendar to reduce drop-off on mobile devices.\n3. Launch doctor video spotlights to build patient trust in mental health categories.",
            "status": "published"
        }
    ]

    for rep in demo_reports:
        create_report(**rep)

    log_activity("database_seeded", "system", "all", "Sample agency demo data loaded successfully.")
    return {
        "clients_created": len(demo_clients),
        "reports_created": len(demo_reports),
        "message": f"Successfully seeded {len(demo_clients)} clients and {len(demo_reports)} campaign reports."
    }
