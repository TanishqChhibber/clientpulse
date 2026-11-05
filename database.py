"""
ClientPulse - Database Layer
============================
Provides unified persistence for ClientPulse using Supabase PostgreSQL,
with an automatic fallback to local persistent SQLite when Supabase
credentials are not configured or unreachable.

Both backends share identical function signatures, schema validation,
and return clean Python dictionaries.
"""

import json
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


def _raise_supabase_write_error(operation: str, exc: Exception) -> None:
    """
    Fail loudly when a Supabase write fails. Falling back to the host's local SQLite file would
    silently split data between services (and that file is wiped on redeploy).
    """
    logger.error("Supabase %s failed: %s", operation, exc)
    raise RuntimeError(f"Could not save to the database ({operation}): {exc}") from exc


def _matches(row: Dict[str, Any], term: str, fields) -> bool:
    term = term.lower()
    return any(term in str(row.get(f) or "").lower() for f in fields)


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

        CREATE TABLE IF NOT EXISTS report_breakdowns (
            id TEXT PRIMARY KEY,
            report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            dimension TEXT NOT NULL CHECK (dimension IN ('channel', 'campaign', 'creative', 'week')),
            label TEXT NOT NULL,
            platform TEXT,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            leads INTEGER NOT NULL DEFAULT 0,
            spend REAL NOT NULL DEFAULT 0.0,
            prev_spend REAL,
            prev_leads INTEGER,
            video_completion_rate REAL,
            verdict TEXT CHECK (verdict IS NULL OR verdict IN ('scale', 'keep', 'cut')),
            note TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_breakdowns_report ON report_breakdowns(report_id, dimension);

        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            client_id TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            columns TEXT,
            row_count INTEGER NOT NULL DEFAULT 0,
            csv_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_datasets_client ON datasets(client_id);

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT NOT NULL
        );
        """)
        # Migration for databases created before key_insights existed
        report_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)")}
        if "key_insights" not in report_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN key_insights TEXT")
        for column in ("dashboard_spec", "source_dataset_id", "computation"):
            if column not in report_columns:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {column} TEXT")
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
            _raise_supabase_write_error("create_client", e)
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
            res = query.execute()
            rows = res.data or []
            if search:
                rows = [r for r in rows if _matches(r, search, ("name", "industry", "email"))]
            return rows
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
            _raise_supabase_write_error("update_client", e)

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
            _raise_supabase_write_error("delete_client", e)

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
            _raise_supabase_write_error("create_report", e)
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
            res = query.execute()
            reports = []
            for r in (res.data or []):
                r_dict = dict(r)
                client_info = r_dict.pop("clients", None) or {}
                r_dict["client_name"] = client_info.get("name", "Unknown Client")
                r_dict["client_industry"] = client_info.get("industry", "")
                reports.append(r_dict)
            if search:
                reports = [r for r in reports if _matches(r, search, ("title", "client_name", "summary"))]
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
        "prev_spend", "summary", "recommendations", "status", "key_insights", "dashboard_spec",
        "source_dataset_id", "computation"
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
            _raise_supabase_write_error("update_report", e)

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
            _raise_supabase_write_error("delete_report", e)

    conn = get_sqlite_conn()
    with conn:
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.close()

    log_activity("report_deleted", "report", report_id, f"Report '{title}' deleted.")
    return True


# ==============================================================================
# Report Breakdowns (per channel / campaign / creative / week) & Key Insights
# ==============================================================================

BREAKDOWN_DIMENSIONS = ("channel", "campaign", "creative", "week")
VERDICTS = ("scale", "keep", "cut")
INSIGHT_TONES = ("positive", "negative", "neutral")


def _clean_breakdown_row(row: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Validate one breakdown row and coerce it to storage types."""
    label = str(row.get("label") or "").strip()
    if not label:
        raise ValueError(f"Row {index + 1}: 'label' is required.")

    def number(key, cast, optional=False):
        value = row.get(key)
        if value is None or value == "":
            return None if optional else cast(0)
        value = cast(float(value))
        if value < 0:
            raise ValueError(f"Row {index + 1} ('{label}'): '{key}' cannot be negative.")
        return value

    verdict = row.get("verdict")
    verdict = str(verdict).strip().lower() if verdict not in (None, "") else None
    if verdict is not None and verdict not in VERDICTS:
        raise ValueError(f"Row {index + 1} ('{label}'): verdict must be one of {', '.join(VERDICTS)}.")

    return {
        "label": label,
        "platform": str(row.get("platform") or "").strip() or None,
        "impressions": number("impressions", int),
        "clicks": number("clicks", int),
        "leads": number("leads", int),
        "spend": round(number("spend", float), 2),
        "prev_spend": number("prev_spend", float, optional=True),
        "prev_leads": number("prev_leads", int, optional=True),
        "video_completion_rate": number("video_completion_rate", float, optional=True),
        "verdict": verdict,
        "note": str(row.get("note") or "").strip() or None,
    }


def set_report_breakdown(report_id: str, dimension: str, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace all breakdown rows of one dimension for a report."""
    if dimension not in BREAKDOWN_DIMENSIONS:
        raise ValueError(f"dimension must be one of {', '.join(BREAKDOWN_DIMENSIONS)}.")
    if not get_report_by_id(report_id):
        raise ValueError(f"Report with id '{report_id}' does not exist.")

    now_iso = get_current_utc_iso()
    records = []
    for i, row in enumerate(rows or []):
        clean = _clean_breakdown_row(row, i)
        clean.update({
            "id": f"brk_{uuid.uuid4().hex[:12]}",
            "report_id": report_id,
            "dimension": dimension,
            "sort_order": i,
            "created_at": now_iso,
        })
        records.append(clean)

    if _db_mode == "supabase" and _supabase_client:
        try:
            table = _supabase_client.table("report_breakdowns")
            table.delete().eq("report_id", report_id).eq("dimension", dimension).execute()
            if records:
                table.insert(records).execute()
            log_activity("report_breakdown_updated", "report", report_id,
                         f"{dimension.title()} breakdown updated ({len(records)} rows).")
            return records
        except Exception as e:
            _raise_supabase_write_error("set_report_breakdown", e)

    conn = get_sqlite_conn()
    with conn:
        conn.execute("DELETE FROM report_breakdowns WHERE report_id = ? AND dimension = ?", (report_id, dimension))
        conn.executemany("""
            INSERT INTO report_breakdowns (
                id, report_id, dimension, label, platform, impressions, clicks, leads, spend,
                prev_spend, prev_leads, video_completion_rate, verdict, note, sort_order, created_at
            ) VALUES (
                :id, :report_id, :dimension, :label, :platform, :impressions, :clicks, :leads, :spend,
                :prev_spend, :prev_leads, :video_completion_rate, :verdict, :note, :sort_order, :created_at
            )
        """, records)
    conn.close()

    log_activity("report_breakdown_updated", "report", report_id,
                 f"{dimension.title()} breakdown updated ({len(records)} rows).")
    return records


def get_report_breakdowns(report_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Return a report's breakdown rows grouped by dimension (every dimension key is present)."""
    rows: List[Dict[str, Any]] = []
    fetched = False
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = (_supabase_client.table("report_breakdowns").select("*")
                   .eq("report_id", report_id).order("sort_order").execute())
            rows = res.data or []
            fetched = True
        except Exception as e:
            _warn_supabase_fallback("query", e)

    if not fetched:
        conn = get_sqlite_conn()
        cursor = conn.execute(
            "SELECT * FROM report_breakdowns WHERE report_id = ? ORDER BY dimension, sort_order", (report_id,)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

    grouped: Dict[str, List[Dict[str, Any]]] = {d: [] for d in BREAKDOWN_DIMENSIONS}
    for r in rows:
        grouped.setdefault(r["dimension"], []).append(r)
    return grouped


def set_report_insights(report_id: str, insights: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Store the key insight bullets shown in the dashboard's insights panel."""
    clean = []
    for i, item in enumerate(insights or []):
        text = str(item.get("text") or "").strip()
        if not text:
            raise ValueError(f"Insight {i + 1}: 'text' is required.")
        tone = str(item.get("tone") or "neutral").strip().lower()
        if tone not in INSIGHT_TONES:
            raise ValueError(f"Insight {i + 1}: tone must be one of {', '.join(INSIGHT_TONES)}.")
        clean.append({"text": text, "impact": str(item.get("impact") or "").strip(), "tone": tone})
    if update_report(report_id, key_insights=json.dumps(clean)) is None:
        raise ValueError(f"Report with id '{report_id}' does not exist.")
    return clean


def get_report_insights(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse a report's stored key insights (empty list if none or unreadable)."""
    raw = report.get("key_insights")
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


# ==============================================================================
# Custom Dashboard Spec (client-defined KPIs, charts, and table)
# ==============================================================================

METRIC_FORMATS = ("number", "currency", "percent", "decimal")


def _num_or_none(value: Any, where: str) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{where}: '{value}' is not a number.")


def _fmt_check(fmt: Any, where: str) -> str:
    fmt = str(fmt or "number").strip().lower()
    if fmt not in METRIC_FORMATS:
        raise ValueError(f"{where}: format must be one of {', '.join(METRIC_FORMATS)}.")
    return fmt


def _better(value: Any) -> Optional[bool]:
    return None if value is None or value == "" else bool(value)


def validate_dashboard_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalise a custom dashboard spec. Every section is optional:
      currency: symbol for 'currency' metrics (e.g. "$", "₹")
      kpis:     [{label, value, prev, format, higher_is_better}]                     (max 8)
      trend:    {title, x: [labels], series: [{name, values, format, axis}]}          (max 3 series)
      split:    {title, labels: [...], values: [...], format}
      rankings: [{title, labels, values, format, higher_is_better}]                   (max 2)
      table:    {title, columns: [{key, label, format}], rows: [{name, values: {key: n}, verdict, note}]}
    """
    out: Dict[str, Any] = {"currency": str(spec.get("currency") or "$").strip()[:4] or "$"}

    kpis = spec.get("kpis") or []
    if len(kpis) > 8:
        raise ValueError("At most 8 KPIs are supported.")
    out["kpis"] = []
    for i, k in enumerate(kpis):
        where = f"KPI {i + 1}"
        label = str(k.get("label") or "").strip()
        if not label:
            raise ValueError(f"{where}: label is required.")
        value = _num_or_none(k.get("value"), where)
        if value is None:
            raise ValueError(f"{where} ('{label}'): value is required.")
        out["kpis"].append({"label": label, "value": value, "prev": _num_or_none(k.get("prev"), where),
                            "format": _fmt_check(k.get("format"), where), "higher_is_better": _better(k.get("higher_is_better", True))})

    trend = spec.get("trend")
    if trend:
        x = [str(v) for v in (trend.get("x") or [])]
        series = trend.get("series") or []
        if not x or not series:
            raise ValueError("Trend needs 'x' labels and at least one series.")
        if len(series) > 3:
            raise ValueError("Trend supports at most 3 series.")
        clean_series = []
        for j, se in enumerate(series):
            where = f"Trend series {j + 1}"
            values = [_num_or_none(v, where) or 0.0 for v in (se.get("values") or [])]
            if len(values) != len(x):
                raise ValueError(f"{where}: needs {len(x)} values (one per x label), got {len(values)}.")
            axis = "right" if str(se.get("axis") or "").lower() == "right" else "left"
            clean_series.append({"name": str(se.get("name") or f"Series {j + 1}").strip(), "values": values,
                                 "format": _fmt_check(se.get("format"), where), "axis": axis,
                                 "higher_is_better": _better(se.get("higher_is_better", True))})
        out["trend"] = {"title": str(trend.get("title") or "Trend").strip(), "x": x, "series": clean_series}

    def labelled(block: Dict[str, Any], where: str) -> Dict[str, Any]:
        labels = [str(v) for v in (block.get("labels") or [])]
        values = [_num_or_none(v, where) or 0.0 for v in (block.get("values") or [])]
        if not labels or len(labels) != len(values):
            raise ValueError(f"{where}: 'labels' and 'values' must be non-empty and the same length.")
        return {"title": str(block.get("title") or where).strip(), "labels": labels, "values": values,
                "format": _fmt_check(block.get("format"), where), "higher_is_better": _better(block.get("higher_is_better", True))}

    if spec.get("split"):
        out["split"] = labelled(spec["split"], "Split")
    rankings = spec.get("rankings") or []
    if len(rankings) > 2:
        raise ValueError("At most 2 rankings are supported.")
    out["rankings"] = [labelled(r, f"Ranking {i + 1}") for i, r in enumerate(rankings)]

    table = spec.get("table")
    if table:
        columns = []
        for c in table.get("columns") or []:
            key = str(c.get("key") or "").strip()
            if not key:
                raise ValueError("Every table column needs a 'key'.")
            columns.append({"key": key, "label": str(c.get("label") or key).strip(), "format": _fmt_check(c.get("format"), f"Column '{key}'")})
        if not columns or len(columns) > 10:
            raise ValueError("Table needs between 1 and 10 columns.")
        rows = []
        for i, r in enumerate((table.get("rows") or [])[:200]):
            name = str(r.get("name") or "").strip()
            if not name:
                raise ValueError(f"Table row {i + 1}: name is required.")
            verdict = r.get("verdict")
            verdict = str(verdict).strip().lower() if verdict not in (None, "") else None
            if verdict is not None and verdict not in VERDICTS:
                raise ValueError(f"Table row {i + 1}: verdict must be one of {', '.join(VERDICTS)}.")
            values = r.get("values") or {}
            rows.append({"name": name, "values": {c["key"]: _num_or_none(values.get(c["key"]), f"Row '{name}'") for c in columns},
                         "verdict": verdict, "note": str(r.get("note") or "").strip()})
        out["table"] = {"title": str(table.get("title") or "Breakdown").strip(), "columns": columns, "rows": rows}
    return out


def set_dashboard_spec(report_id: str, spec: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Store (or with None, clear) a report's custom dashboard spec."""
    clean = validate_dashboard_spec(spec) if spec else None
    if update_report(report_id, dashboard_spec=json.dumps(clean) if clean else "") is None:
        raise ValueError(f"Report with id '{report_id}' does not exist.")
    return clean


def get_dashboard_spec(report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = report.get("dashboard_spec")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


# ==============================================================================
# App Settings (agency branding, per-client report templates)
# ==============================================================================

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("app_settings").select("value").eq("key", key).limit(1).execute()
            return res.data[0]["value"] if res.data else default
        except Exception as e:
            _warn_supabase_fallback("query", e)
            return default
    conn = get_sqlite_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: Optional[str]) -> None:
    record = {"key": key, "value": value, "updated_at": get_current_utc_iso()}
    if _db_mode == "supabase" and _supabase_client:
        try:
            _supabase_client.table("app_settings").upsert(record).execute()
            return
        except Exception as e:
            _raise_supabase_write_error("set_setting", e)
    conn = get_sqlite_conn()
    with conn:
        conn.execute("""
            INSERT INTO app_settings (key, value, updated_at) VALUES (:key, :value, :updated_at)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, record)
    conn.close()


BRANDING_DEFAULTS = {
    "agency_name": "ClientPulse",
    "agency_tagline": "Agency Performance & Reporting Platform",
    "brand_color": "#4F46E5",
    "logo_data_uri": "",
    "report_footer": "Prepared by your digital marketing agency",
    "show_powered_by": True,
}


def get_branding() -> Dict[str, Any]:
    """Agency white-label settings (name, logo, colour, footer) with defaults."""
    raw = get_setting("branding")
    stored = {}
    if raw:
        try:
            stored = json.loads(raw)
        except ValueError:
            stored = {}
    return {**BRANDING_DEFAULTS, **{k: v for k, v in stored.items() if k in BRANDING_DEFAULTS}}


def save_branding(values: Dict[str, Any]) -> Dict[str, Any]:
    clean = {**get_branding(), **{k: v for k, v in values.items() if k in BRANDING_DEFAULTS}}
    clean["agency_name"] = str(clean["agency_name"] or "").strip() or BRANDING_DEFAULTS["agency_name"]
    color = str(clean["brand_color"] or "").strip()
    if not (len(color) == 7 and color.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
        raise ValueError("Brand colour must be a hex value like #4F46E5.")
    logo = str(clean.get("logo_data_uri") or "")
    if logo and (not logo.startswith("data:image/") or len(logo) > 700_000):
        raise ValueError("Logo must be a PNG or JPG image under 500 KB.")
    clean["show_powered_by"] = bool(clean["show_powered_by"])
    set_setting("branding", json.dumps(clean))
    log_activity("branding_updated", "settings", "branding", f"Agency branding updated ({clean['agency_name']}).")
    return clean


def get_report_template(client_id: str) -> Optional[Dict[str, Any]]:
    raw = get_setting(f"template:{client_id}")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def save_report_template(client_id: str, recipe: Dict[str, Any]) -> None:
    """Remember a client's recipe (minus periods and verdicts) so next month's report is one click."""
    template = {k: v for k, v in recipe.items() if k not in ("period", "compare_period", "verdicts")}
    set_setting(f"template:{client_id}", json.dumps(template))


# ==============================================================================
# Datasets (raw CSV data the app computes reports from)
# ==============================================================================

def create_dataset(client_id: str, name: str, csv_text: str) -> Dict[str, Any]:
    from utils.compute import load_csv
    if not get_client_by_id(client_id):
        raise ValueError(f"Client with id '{client_id}' does not exist.")
    df = load_csv(csv_text)
    record = {
        "id": f"ds_{uuid.uuid4().hex[:12]}",
        "client_id": client_id,
        "name": (name or "data.csv").strip(),
        "columns": json.dumps(list(df.columns)),
        "row_count": int(len(df)),
        "csv_text": csv_text,
        "created_at": get_current_utc_iso(),
    }
    if _db_mode == "supabase" and _supabase_client:
        try:
            _supabase_client.table("datasets").insert(record).execute()
        except Exception as e:
            _raise_supabase_write_error("create_dataset", e)
    else:
        conn = get_sqlite_conn()
        with conn:
            conn.execute("""
                INSERT INTO datasets (id, client_id, name, columns, row_count, csv_text, created_at)
                VALUES (:id, :client_id, :name, :columns, :row_count, :csv_text, :created_at)
            """, record)
        conn.close()
    log_activity("dataset_uploaded", "dataset", record["id"], f"Dataset '{record['name']}' uploaded ({record['row_count']} rows).")
    return {k: v for k, v in record.items() if k != "csv_text"}


def list_datasets(client_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cols = "id, client_id, name, columns, row_count, created_at"
    if _db_mode == "supabase" and _supabase_client:
        try:
            query = _supabase_client.table("datasets").select(cols).order("created_at", desc=True)
            if client_id:
                query = query.eq("client_id", client_id)
            return query.execute().data or []
        except Exception as e:
            _warn_supabase_fallback("query", e)
            return []
    conn = get_sqlite_conn()
    sql, params = f"SELECT {cols} FROM datasets", []
    if client_id:
        sql += " WHERE client_id = ?"
        params.append(client_id)
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC", params).fetchall()]
    conn.close()
    return rows


def get_dataset(dataset_id: str) -> Optional[Dict[str, Any]]:
    if _db_mode == "supabase" and _supabase_client:
        try:
            res = _supabase_client.table("datasets").select("*").eq("id", dataset_id).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            _warn_supabase_fallback("query", e)
            return None
    conn = get_sqlite_conn()
    row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_dataset(dataset_id: str) -> bool:
    if _db_mode == "supabase" and _supabase_client:
        try:
            _supabase_client.table("datasets").delete().eq("id", dataset_id).execute()
            return True
        except Exception as e:
            _raise_supabase_write_error("delete_dataset", e)
    conn = get_sqlite_conn()
    with conn:
        conn.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    conn.close()
    return True


def build_report_from_dataset(
    dataset_id: str,
    recipe: Dict[str, Any],
    title: str,
    status: str = "draft",
    summary: str = "",
    recommendations: str = "",
    report_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute a report from a stored dataset with the deterministic engine (no AI arithmetic),
    then create it (or recompute an existing one) and save the recipe as the client's template.
    """
    from utils.compute import build, load_csv
    dataset = get_dataset(dataset_id)
    if not dataset:
        raise ValueError(f"Dataset '{dataset_id}' does not exist.")
    result = build(load_csv(dataset["csv_text"]), recipe, dataset_name=dataset["name"])
    computation = json.dumps({"recipe": result["recipe"], "audit": result["audit"]}, default=str)
    core = {k: (int(round(v)) if not k.endswith("spend") else round(v, 2)) for k, v in result["core"].items()}

    if report_id:
        report = update_report(report_id, **core)
        if not report:
            raise ValueError(f"Report with id '{report_id}' does not exist.")
    else:
        report = create_report(
            client_id=dataset["client_id"], title=title, period_start=recipe["period"]["start"],
            period_end=recipe["period"]["end"], summary=summary, recommendations=recommendations, status=status,
            **{k: core.get(k, 0) for k in ("impressions", "clicks", "leads", "spend",
                                            "prev_impressions", "prev_clicks", "prev_leads", "prev_spend")},
        )
    set_dashboard_spec(report["id"], result["spec"])
    update_report(report["id"], source_dataset_id=dataset_id, computation=computation)
    save_report_template(dataset["client_id"], result["recipe"])
    log_activity("report_computed", "report", report["id"],
                 f"Computed from '{dataset['name']}' ({result['audit']['rows_current']} rows in period).")
    return {"report": get_report_by_id(report["id"]), "spec": result["spec"], "audit": result["audit"]}


def get_report_computation(report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = report.get("computation")
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return None


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
            _warn_supabase_fallback("log_activity (entry skipped)", e)
            return

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

def _split(total: float, weights: List[float], as_int: bool = True) -> List[float]:
    """Split a total across weights; integer splits put the rounding remainder on the largest share."""
    wsum = sum(weights) or 1
    parts = [total * w / wsum for w in weights]
    if not as_int:
        return [round(p, 2) for p in parts]
    ints = [int(p) for p in parts]
    ints[weights.index(max(weights))] += int(round(total)) - sum(ints)
    return ints


def _demo_breakdowns(report: Dict[str, Any], seed: int) -> Dict[str, Any]:
    """
    Deterministically derive channel / campaign / creative / weekly rows and insights
    from a demo report's totals, so seeded dashboards are fully populated.
    Rows sum to the report totals. Templated text only (no AI).
    """
    import random
    rng = random.Random(seed)

    def rows_for(templates):
        # template: (label, platform, spend_share, cpl_multiplier, ctr_multiplier, extra)
        spend_w = [t[2] * rng.uniform(0.9, 1.1) for t in templates]
        lead_w = [w / t[3] for w, t in zip(spend_w, templates)]
        click_w = [w * t[4] for w, t in zip(spend_w, templates)]
        spend = _split(report["spend"], spend_w, as_int=False)
        leads = _split(report["leads"], lead_w)
        clicks = _split(report["clicks"], click_w)
        imps = _split(report["impressions"], spend_w)
        prev_spend = _split(report["prev_spend"], [w * rng.uniform(0.85, 1.15) for w in spend_w], as_int=False)
        prev_leads = _split(report["prev_leads"], [w * rng.uniform(0.85, 1.15) for w in lead_w])
        out = []
        for i, t in enumerate(templates):
            row = {"label": t[0], "platform": t[1], "impressions": imps[i], "clicks": clicks[i], "leads": leads[i],
                   "spend": spend[i], "prev_spend": prev_spend[i], "prev_leads": prev_leads[i]}
            row.update(t[5] if len(t) > 5 else {})
            out.append(row)
        return out

    channels = rows_for([
        ("Google Search", "Google Ads", 0.40, 1.15, 2.4), ("YouTube", "Google Ads", 0.10, 2.4, 0.4),
        ("Meta Prospecting", "Meta", 0.34, 0.85, 1.0), ("Meta Retargeting", "Meta", 0.16, 0.6, 1.3),
    ])
    campaigns = rows_for([
        ("Search - Brand", "Google Ads", 0.14, 0.45, 3.5), ("Search - Non-Brand", "Google Ads", 0.26, 2.2, 1.8),
        ("YouTube - Awareness", "Google Ads", 0.10, 2.4, 0.4), ("Prospecting - Video", "Meta", 0.34, 0.85, 1.0),
        ("Retargeting", "Meta", 0.16, 0.6, 1.3),
    ])
    creatives = rows_for([
        ("UGC Testimonial 15s", "Meta", 0.24, 0.55, 1.4, {"video_completion_rate": 58.0}),
        ("Before/After Demo 20s", "Meta", 0.18, 0.9, 1.1, {"video_completion_rate": 46.0}),
        ("Free Trial Offer 10s", "Meta", 0.14, 0.7, 1.3, {"video_completion_rate": 63.0}),
        ("Founder Story 45s", "Meta", 0.14, 1.6, 0.7, {"video_completion_rate": 24.0}),
        ("Studio Product Demo 30s", "Meta", 0.18, 2.8, 0.5, {"video_completion_rate": 19.0}),
        ("YouTube Shorts Teaser 15s", "Google Ads", 0.12, 1.9, 0.4, {"video_completion_rate": 44.0}),
    ])
    avg_cpl = report["spend"] / report["leads"] if report["leads"] else 0
    ranked = sorted(creatives, key=lambda r: r["spend"] / r["leads"] if r["leads"] else 1e9)
    for rank, row in enumerate(ranked):
        cpl = row["spend"] / row["leads"] if row["leads"] else 0
        row["verdict"] = "scale" if rank < 2 else ("cut" if rank == len(ranked) - 1 else "keep")
        row["note"] = f"CPL ${cpl:,.2f} vs ${avg_cpl:,.2f} account average."

    start, end = date.fromisoformat(report["period_start"]), date.fromisoformat(report["period_end"])
    week_starts = []
    d = start
    while d <= end:
        week_starts.append(d)
        d = date.fromordinal(d.toordinal() + 7)
    trend = [(1 + 0.04 * i) * rng.uniform(0.92, 1.08) for i in range(len(week_starts))]
    weekly = [{"label": ws.isoformat(), "impressions": im, "clicks": cl, "leads": ld, "spend": sp}
              for ws, im, cl, ld, sp in zip(week_starts, _split(report["impressions"], trend), _split(report["clicks"], trend),
                                            _split(report["leads"], [t * rng.uniform(0.9, 1.1) for t in trend]),
                                            _split(report["spend"], trend, as_int=False))]

    best, worst = ranked[0], ranked[-1]
    best_ch = min(channels, key=lambda r: r["spend"] / r["leads"] if r["leads"] else 1e9)
    lead_delta = (report["leads"] - report["prev_leads"]) / report["prev_leads"] * 100 if report["prev_leads"] else 0
    insights = [
        {"text": f"{best['label']} is the top creative at ${best['spend'] / max(best['leads'], 1):,.2f} CPL. Scale its budget.",
         "impact": f"{best['leads'] / max(report['leads'], 1) * 100:.0f}% of leads", "tone": "positive"},
        {"text": f"{worst['label']} has the highest CPL (${worst['spend'] / max(worst['leads'], 1):,.2f}). Cut it and reallocate.",
         "impact": f"-${worst['spend']:,.0f}", "tone": "negative"},
        {"text": f"{best_ch['label']} is the most efficient channel.",
         "impact": f"${best_ch['spend'] / max(best_ch['leads'], 1):,.2f} CPL", "tone": "positive"},
        {"text": f"Leads changed {lead_delta:+.0f}% versus the previous period.",
         "impact": f"{lead_delta:+.0f}%", "tone": "positive" if lead_delta >= 0 else "negative"},
    ]
    return {"channel": channels, "campaign": campaigns, "creative": creatives, "week": weekly, "insights": insights}


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

    for i, rep in enumerate(demo_reports):
        created = create_report(**rep)
        demo = _demo_breakdowns(created, seed=i + 1)
        for dimension in BREAKDOWN_DIMENSIONS:
            set_report_breakdown(created["id"], dimension, demo[dimension])
        set_report_insights(created["id"], demo["insights"])

    log_activity("database_seeded", "system", "all", "Sample agency demo data loaded successfully.")
    return {
        "clients_created": len(demo_clients),
        "reports_created": len(demo_reports),
        "message": f"Successfully seeded {len(demo_clients)} clients and {len(demo_reports)} campaign reports."
    }
