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
    publish_report
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


if __name__ == "__main__":
    unittest.main()
