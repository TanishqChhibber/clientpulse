"""
ClientPulse Automated Test Suite
================================
Validates Database operations, derived metric calculations, input validation,
and all 6 MCP tool handlers.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Run against a throwaway SQLite file so setUp's force re-seed never wipes real data.
# Empty Supabase settings take precedence over .env (load_dotenv does not override).
_TEST_DB_DIR = tempfile.mkdtemp(prefix="clientpulse-test-")
os.environ["CLIENTPULSE_DB_PATH"] = os.path.join(_TEST_DB_DIR, "test.db")
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""

import database
from mcp_server.server import (
    create_client,
    list_clients,
    create_report,
    list_reports,
    update_report,
    publish_report,
    set_report_breakdown,
    get_report,
    set_custom_dashboard,
    build_report_from_dataset
)


class TestClientPulseCore(unittest.TestCase):

    def setUp(self):
        # Seed fresh demo data before tests
        database.seed_demo_data(force=True)

    def test_derived_metrics_calculation(self):
        """Test calculation of CTR, CPL, and conversion rate."""
        metrics = database.calculate_derived_metrics(
            impressions=100000,
            clicks=4000,
            leads=200,
            spend=5000.0
        )
        self.assertEqual(metrics["ctr"], 4.0)       # (4000 / 100000) * 100
        self.assertEqual(metrics["cpl"], 25.0)      # 5000 / 200
        self.assertEqual(metrics["conversion_rate"], 5.0)  # (200 / 4000) * 100

    def test_client_crud(self):
        """Test client creation, retrieval, update, and deletion."""
        # Create
        c = database.create_client(
            name="Quantum Metrics Corp",
            email="ops@quantummetrics.io",
            industry="Data Analytics",
            website="https://quantummetrics.io",
            notes="Enterprise B2B account",
            status="active"
        )
        self.assertIsNotNone(c["id"])
        self.assertEqual(c["name"], "Quantum Metrics Corp")

        # Read
        fetched = database.get_client_by_id(c["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["email"], "ops@quantummetrics.io")

        # Update
        updated = database.update_client(c["id"], industry="Enterprise AI Analytics")
        self.assertEqual(updated["industry"], "Enterprise AI Analytics")

        # Delete
        del_result = database.delete_client(c["id"])
        self.assertTrue(del_result)
        self.assertIsNone(database.get_client_by_id(c["id"]))

    def test_client_validation(self):
        """Test that client creation rejects empty name."""
        with self.assertRaises(ValueError):
            database.create_client(name="")

    def test_report_crud_and_publishing(self):
        """Test report creation, live metrics, and publishing workflow."""
        clients = database.get_clients()
        self.assertTrue(len(clients) > 0)
        client_id = clients[0]["id"]

        # Create Report
        rep = database.create_report(
            client_id=client_id,
            title="Q3 Strategic Growth Audit",
            period_start="2026-07-01",
            period_end="2026-09-30",
            impressions=500000,
            clicks=20000,
            leads=1000,
            spend=20000.0,
            summary="Strong pipeline velocity.",
            recommendations="Increase brand search share.",
            status="draft"
        )
        self.assertIsNotNone(rep["id"])
        self.assertIsNotNone(rep["share_token"])
        self.assertEqual(rep["ctr"], 4.0)
        self.assertEqual(rep["cpl"], 20.0)
        self.assertEqual(rep["status"], "draft")

        # Verify not accessible via public token while draft
        pub_check = database.get_report_by_share_token(rep["share_token"])
        self.assertIsNone(pub_check)

        # Publish Report
        pub_rep = database.publish_report(rep["id"])
        self.assertIsNotNone(pub_rep)
        self.assertEqual(pub_rep["status"], "published")

        # Now accessible via public token
        pub_accessible = database.get_report_by_share_token(rep["share_token"])
        self.assertIsNotNone(pub_accessible)
        self.assertEqual(pub_accessible["title"], "Q3 Strategic Growth Audit")

        # Cleanup
        database.delete_report(rep["id"])
        self.assertIsNone(database.get_report_by_id(rep["id"]))

    def test_mcp_create_and_list_tools(self):
        """Test MCP tools create_client, list_clients, create_report, list_reports."""
        # 1. create_client
        res_c = create_client(
            name="Apex Horizon Labs",
            email="founder@apexhorizon.com",
            industry="Biotech SaaS"
        )
        self.assertTrue(res_c.get("success"))
        cid = res_c["client"]["id"]

        # 2. list_clients
        res_list_c = list_clients()
        self.assertTrue(res_list_c.get("success"))
        self.assertGreaterEqual(res_list_c.get("count"), 1)

        # 3. create_report
        res_r = create_report(
            client_id=cid,
            title="Biotech Ad Campaign Launch",
            period_start="2026-08-01",
            period_end="2026-08-31",
            impressions=100000,
            clicks=5000,
            leads=250,
            spend=7500.0,
            summary="Launch sprint achieved 5.0% CTR.",
            recommendations="Expand retargeting audiences."
        )
        self.assertTrue(res_r.get("success"))
        rid = res_r["report_id"]

        # 4. list_reports
        res_list_r = list_reports(client_id=cid)
        self.assertTrue(res_list_r.get("success"))
        self.assertEqual(res_list_r.get("count"), 1)

        # 5. update_report
        res_u = update_report(report_id=rid, spend=8000.0, leads=400)
        self.assertTrue(res_u.get("success"))
        self.assertEqual(res_u["report"]["cpl"], 20.0)

        # 6. publish_report
        res_p = publish_report(report_id=rid)
        self.assertTrue(res_p.get("success"))
        self.assertEqual(res_p["status"], "published")
        self.assertIn("public_url", res_p)

    def test_report_validation(self):
        """Test that invalid metrics, dates, and statuses are rejected."""
        client_id = database.get_clients()[0]["id"]
        base = dict(client_id=client_id, title="Validation", period_start="2026-07-01",
                    period_end="2026-07-31", impressions=1000, clicks=10, leads=1, spend=100.0)

        with self.assertRaises(ValueError):
            database.create_report(**{**base, "spend": -5.0})
        with self.assertRaises(ValueError):
            database.create_report(**{**base, "period_end": "2026-06-01"})

        rep = database.create_report(**base)
        with self.assertRaises(ValueError):
            database.update_report(rep["id"], status="archived")
        with self.assertRaises(ValueError):
            database.update_report(rep["id"], period_start="2026-08-15")

        # MCP tool surfaces validation errors instead of raising
        res = update_report(report_id=rep["id"], status="archived")
        self.assertTrue(res.get("error"))

    def test_mcp_update_report_period_fields(self):
        """Test that the MCP update tool can change the period and benchmark fields."""
        rep = database.get_reports()[0]
        res = update_report(report_id=rep["id"], period_start="2026-01-01",
                            period_end="2026-01-31", prev_leads=10, prev_spend=500.0)
        self.assertTrue(res.get("success"))
        self.assertEqual(res["report"]["period_start"], "2026-01-01")
        self.assertEqual(res["report"]["prev_leads"], 10)

    def test_seeded_reports_have_breakdowns(self):
        """Demo reports come with breakdown rows that add up to the report totals."""
        rep = database.get_reports()[0]
        bd = database.get_report_breakdowns(rep["id"])
        for dim in database.BREAKDOWN_DIMENSIONS:
            self.assertTrue(bd[dim], f"no {dim} rows")
        self.assertEqual(sum(r["leads"] for r in bd["channel"]), rep["leads"])
        self.assertAlmostEqual(sum(r["spend"] for r in bd["week"]), rep["spend"], places=0)
        self.assertEqual(len(database.get_report_insights(rep)), 4)

    def test_breakdown_validation_and_replace(self):
        """Breakdown rows are validated, replaced per dimension, and removed with the report."""
        rep = database.get_reports()[0]
        with self.assertRaises(ValueError):
            database.set_report_breakdown(rep["id"], "channel", [{"label": "X", "spend": -1}])
        with self.assertRaises(ValueError):
            database.set_report_breakdown(rep["id"], "creative", [{"label": "X", "verdict": "maybe"}])
        with self.assertRaises(ValueError):
            database.set_report_breakdown(rep["id"], "region", [{"label": "X"}])

        database.set_report_breakdown(rep["id"], "channel", [{"label": "Only Channel", "spend": 10, "leads": 2}])
        bd = database.get_report_breakdowns(rep["id"])
        self.assertEqual([r["label"] for r in bd["channel"]], ["Only Channel"])
        self.assertTrue(bd["creative"])  # other dimensions untouched

        database.delete_report(rep["id"])
        self.assertEqual(database.get_report_breakdowns(rep["id"])["creative"], [])

    def test_mcp_breakdown_and_get_report(self):
        """MCP set_report_breakdown stores rows and insights; get_report returns them."""
        rep = database.get_reports()[0]
        res = set_report_breakdown(
            report_id=rep["id"],
            creatives=[{"label": "Video A", "platform": "Meta", "spend": 100, "leads": 20, "verdict": "scale",
                        "video_completion_rate": 55}],
            key_insights=[{"text": "Video A wins", "impact": "+20%", "tone": "positive"}],
        )
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["rows_stored"], {"creative": 1, "key_insights": 1})

        full = get_report(report_id=rep["id"])
        self.assertEqual(full["breakdowns"]["creative"][0]["label"], "Video A")
        self.assertEqual(full["key_insights"][0]["tone"], "positive")
        self.assertTrue(full["breakdowns"]["channel"])  # untouched sections kept

        self.assertTrue(set_report_breakdown(report_id=rep["id"]).get("error"))
        self.assertTrue(set_report_breakdown(report_id="missing", weekly=[]).get("error"))

    def test_custom_dashboard_spec(self):
        """Client-defined KPIs/charts/table are validated, stored, cleared, and exported."""
        from utils.pdf_report import build_report_pdf
        rep = database.get_reports()[0]
        spec = {
            "currency": "₹",
            "kpis": [{"label": "LDAU", "value": 72200, "prev": 67200},
                     {"label": "D30 Retention", "value": 12.5, "prev": 12.0, "format": "percent"}],
            "trend": {"title": "LDAU", "x": ["2026-09", "2026-10"], "series": [{"name": "LDAU", "values": [67200, 72200]}]},
            "split": {"title": "CTV by duration", "labels": ["<1 min", "10+ min"], "values": [29600, 79730], "format": "currency"},
            "rankings": [{"title": "D30 by duration", "labels": ["<1 min", "10+ min"], "values": [7, 21.3], "format": "percent"}],
            "table": {"title": "Videos", "columns": [{"key": "ldau", "label": "LDAU"}],
                      "rows": [{"name": "Full Episode 2", "values": {"ldau": 4400}, "verdict": "scale"}]},
        }
        res = set_custom_dashboard(report_id=rep["id"], **spec)
        self.assertTrue(res.get("success"), res)
        stored = database.get_dashboard_spec(database.get_report_by_id(rep["id"]))
        self.assertEqual(stored["kpis"][1]["label"], "D30 Retention")
        self.assertEqual(stored["currency"], "₹")
        self.assertEqual(get_report(report_id=rep["id"])["custom_dashboard"]["table"]["rows"][0]["verdict"], "scale")

        pdf = build_report_pdf(database.get_report_by_id(rep["id"]), {}, [], stored)
        self.assertTrue(pdf.startswith(b"%PDF"))

        for bad in ({"kpis": [{"label": "", "value": 1}]},
                    {"trend": {"x": ["a", "b"], "series": [{"name": "s", "values": [1]}]}},
                    {"split": {"labels": ["a"], "values": [1, 2]}}):
            with self.assertRaises(ValueError):
                database.validate_dashboard_spec(bad)

        self.assertTrue(set_custom_dashboard(report_id=rep["id"], reset=True).get("success"))
        self.assertIsNone(database.get_dashboard_spec(database.get_report_by_id(rep["id"])))

    def test_create_report_without_ad_metrics(self):
        """Non-ad reports can be created without impressions/clicks/leads/spend."""
        cid = database.get_clients()[0]["id"]
        res = create_report(client_id=cid, title="Content report", period_start="2026-10-01", period_end="2026-10-31")
        self.assertTrue(res.get("success"), res)
        self.assertEqual(res["report"]["spend"], 0)

    def test_compute_engine_from_dataset(self):
        """ClientPulse computes report numbers itself from raw rows, and reuses the template next period."""
        csv_text = (
            "date,channel,spend,leads,clicks,impressions\n"
            "2026-09-03,Google,100,4,50,1000\n2026-09-10,Meta,50,5,40,2000\n"
            "2026-10-02,Google,120,6,60,1200\n2026-10-09,Meta,80,10,70,2500\n2026-10-20,Meta,20,4,10,500\n"
        )
        cid = database.get_clients()[0]["id"]
        ds = database.create_dataset(cid, "test.csv", csv_text)
        recipe = {
            "date_column": "date", "currency": "$",
            "period": {"start": "2026-10-01", "end": "2026-10-31"},
            "compare_period": {"start": "2026-09-01", "end": "2026-09-30"},
            "metrics": [
                {"key": "spend", "label": "Spend", "agg": "sum", "column": "spend", "format": "currency"},
                {"key": "leads", "label": "Leads", "agg": "sum", "column": "leads"},
                {"key": "clicks", "label": "Clicks", "agg": "sum", "column": "clicks"},
                {"key": "impressions", "label": "Impressions", "agg": "sum", "column": "impressions"},
                {"key": "cpl", "label": "CPL", "agg": "ratio", "numerator": "spend", "denominator": "leads",
                 "format": "currency", "higher_is_better": False},
            ],
            "kpis": ["spend", "leads", "cpl"],
            "table": {"dimension": "channel", "metrics": ["spend", "leads", "cpl"], "sort_by": "cpl"},
            "verdicts": {"Meta": {"verdict": "scale"}},
        }
        res = database.build_report_from_dataset(ds["id"], recipe, title="Oct")
        rep, kpis = res["report"], {k["label"]: k for k in res["spec"]["kpis"]}
        self.assertEqual(kpis["Spend"]["value"], 220)
        self.assertEqual(kpis["Spend"]["prev"], 150)
        self.assertAlmostEqual(kpis["CPL"]["value"], 220 / 20)
        self.assertEqual((rep["spend"], rep["leads"], rep["prev_leads"]), (220, 20, 9))
        rows = res["spec"]["table"]["rows"]
        self.assertEqual([r["name"] for r in rows], ["Meta", "Google"])  # sorted by CPL, lower first
        self.assertEqual(rows[0]["verdict"], "scale")
        self.assertEqual(res["audit"]["rows_current"], 3)
        self.assertIn("Spend ÷ Leads", [m["formula"] for m in res["audit"]["metrics"]])
        self.assertEqual(database.get_report_computation(database.get_report_by_id(rep["id"]))["audit"]["rows_previous"], 2)

        # Next period from the saved template only (MCP tool, no metrics passed)
        nxt = build_report_from_dataset(dataset_id=ds["id"], title="Sep",
                                        period={"start": "2026-09-01", "end": "2026-09-30"})
        self.assertTrue(nxt.get("success"), nxt)
        self.assertEqual({k["label"]: k["value"] for k in nxt["kpis"]}["Spend"], 150)

        bad = build_report_from_dataset(dataset_id=ds["id"], title="x", period={"start": "2026-10-01", "end": "2026-10-31"},
                                        date_column="nope", metrics=[{"key": "s", "label": "S", "column": "spend"}])
        self.assertTrue(bad.get("error"))

    def test_branding(self):
        """White-label settings are validated, stored, and used in the PDF."""
        from utils.pdf_report import build_report_pdf
        saved = database.save_branding({"agency_name": "Northwind Digital", "brand_color": "#0EA5E9",
                                        "show_powered_by": False})
        self.assertEqual(database.get_branding()["agency_name"], "Northwind Digital")
        self.assertFalse(saved["show_powered_by"])
        with self.assertRaises(ValueError):
            database.save_branding({"brand_color": "blue"})
        with self.assertRaises(ValueError):
            database.save_branding({"logo_data_uri": "http://example.com/logo.png"})
        rep = database.get_reports()[0]
        pdf = build_report_pdf(rep, {}, [], None, database.get_branding())
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_narrative_formatting(self):
        """Claude's plain-text narrative becomes headings, bold key points, and real tables; HTML is escaped."""
        from utils.narrative import parse, to_html
        text = ("HEADLINE\nOctober was the best month.\n"
                "MONTHLY TREND (weighted by LDAU)\n"
                "Sep 2026 | LDAU 67,200 | D30 12.0%\nOct 2026 | LDAU 72,200 | D30 12.5%\n"
                "1. Back the long episodes. They retain best.\nBest value: Full Episode 1 <script>x</script>")
        kinds = [b[0] for b in parse(text)]
        self.assertEqual(kinds, ["heading", "para", "heading", "note", "table", "item", "para"])
        table = parse(text)[4]
        self.assertEqual(table[1], ["", "LDAU", "D30"])
        self.assertEqual(table[2][1], ["Oct 2026", "72,200", "12.5%"])
        out = to_html(text)
        self.assertIn("<b>Back the long episodes.</b>", out)
        self.assertIn("<b>Best value:</b>", out)
        self.assertNotIn("<script>", out)

    def test_pdf_export(self):
        """PDF export produces a valid PDF, including non-Latin text and emoji."""
        from utils.pdf_report import build_report_pdf
        rep = database.get_reports()[0]
        rep = dict(rep, summary="Growth “up” — ₹ budget 🚀")
        pdf = build_report_pdf(rep, database.get_report_breakdowns(rep["id"]), database.get_report_insights(rep))
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 20000)


if __name__ == "__main__":
    unittest.main()
