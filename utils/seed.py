"""
ClientPulse - Explicit Demo Seeder
==================================
Command-line utility and module for populating realistic marketing agency
clients and campaign performance reports.

Usage:
    python utils/seed.py [--force]
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database import seed_demo_data, get_db_info, get_clients, get_reports


def main():
    parser = argparse.ArgumentParser(description="Seed ClientPulse demo clients and reports.")
    parser.add_argument("--force", action="store_true", help="Force re-seeding even if clients already exist.")
    args = parser.parse_args()

    info = get_db_info()
    print(f"[*] Target Database Engine: {info['name']} ({info['status_text']})")

    res = seed_demo_data(force=args.force)
    print(f"[+] Result: {res['message']}")
    print(f"[*] Total Clients in DB: {len(get_clients())}")
    print(f"[*] Total Reports in DB: {len(get_reports())}")


if __name__ == "__main__":
    main()
