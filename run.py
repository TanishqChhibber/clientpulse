"""
ClientPulse - Application Runner
================================
Convenience launcher for ClientPulse services:
- Streamlit Web Dashboard
- FastMCP Streamable HTTP Server
- Demo Data Seeder

Usage:
    python run.py app       # Start Streamlit Dashboard (Port 8501)
    python run.py mcp       # Start FastMCP Streamable HTTP Server (Port 8000)
    python run.py seed      # Populate demo clients and campaign reports
    python run.py all       # Start both Streamlit and MCP server concurrently
    python run.py test      # Run automated test suite
"""

import sys
import subprocess
import os
import signal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def run_app():
    """Start Streamlit frontend dashboard."""
    print("[*] Launching ClientPulse Streamlit Dashboard on http://localhost:8501 ...")
    cmd = [sys.executable, "-m", "streamlit", "run", str(BASE_DIR / "app.py"), "--server.port", "8501"]
    subprocess.run(cmd)

def run_mcp():
    """Start FastMCP server with Streamable HTTP transport."""
    print("[*] Launching ClientPulse MCP Server on http://0.0.0.0:8000/mcp ...")
    cmd = [sys.executable, str(BASE_DIR / "mcp_server" / "server.py")]
    subprocess.run(cmd)

def run_seed(force=False):
    """Seed demo clients and reports."""
    cmd = [sys.executable, str(BASE_DIR / "utils" / "seed.py")]
    if force:
        cmd.append("--force")
    subprocess.run(cmd)

def run_tests():
    """Execute automated unit tests."""
    cmd = [sys.executable, str(BASE_DIR / "tests" / "test_clientpulse.py")]
    subprocess.run(cmd)

def run_all():
    """Concurrently run both MCP server and Streamlit frontend."""
    print("=" * 65)
    print("⚡ Starting ClientPulse SaaS Platform")
    print("   • Frontend Dashboard: http://localhost:8501")
    print("   • MCP Remote Server:  http://localhost:8000/mcp (Streamable HTTP)")
    print("=" * 65)
    
    # 1. Start MCP Server process
    mcp_proc = subprocess.Popen([sys.executable, str(BASE_DIR / "mcp_server" / "server.py")])
    
    # 2. Start Streamlit process
    streamlit_proc = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", str(BASE_DIR / "app.py"),
        "--server.port", "8501", "--server.headless", "true"
    ])

    def handle_sigint(signum, frame):
        print("\n[*] Shutting down ClientPulse services...")
        mcp_proc.terminate()
        streamlit_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        streamlit_proc.wait()
    except KeyboardInterrupt:
        handle_sigint(None, None)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()
    if action == "app":
        run_app()
    elif action == "mcp":
        run_mcp()
    elif action == "seed":
        force = "--force" in sys.argv
        run_seed(force=force)
    elif action == "test":
        run_tests()
    elif action == "all":
        run_all()
    else:
        print(f"Unknown command: '{action}'")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
