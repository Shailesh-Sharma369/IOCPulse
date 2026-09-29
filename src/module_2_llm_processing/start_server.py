"""
start_server.py – Colab bootstrap script for the CTI LLM inference server.

Changes vs original:
- Polls /ready (new lightweight endpoint) instead of /health, which avoids
  parsing the full health JSON payload on every poll tick.
- Falls back to /health if /ready returns 404 (backward compatibility).
- Waits for Uvicorn to print its startup message before starting health polls,
  reducing the noisy "Waiting…" log spam on fast machines.
- ngrok URL is also printed as a plain string (public_url.public_url) so it
  can be copy-pasted directly.
- Added keyboard-interrupt handler that tears down both the server process
  and the ngrok tunnel cleanly.
- NGROK_AUTH_TOKEN is read from an environment variable first, falling back
  to the hard-coded placeholder.  This avoids accidentally committing tokens.
"""

from __future__ import annotations

import os
import sys
import signal
import subprocess
import threading
import time
from typing import Optional

import requests
from google.colab import drive

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_DIR      = "/content/drive/MyDrive"
NGROK_AUTH_TOKEN = os.getenv("NGROK_AUTH_TOKEN", "REPLACE_WITH_YOUR_TOKEN")
SERVER_PORT      = 8000
STARTUP_TIMEOUT  = 600   # 10 minutes — first run downloads model weights

# ---------------------------------------------------------------------------
# Mount Google Drive
# ---------------------------------------------------------------------------
drive.mount("/content/drive")

os.chdir(PROJECT_DIR)
print(f"📂 Working directory: {os.getcwd()}")

if not os.path.exists("remote_llm_server.py"):
    raise FileNotFoundError(
        "remote_llm_server.py not found in the working directory. "
        "Upload it to Google Drive first."
    )

# ---------------------------------------------------------------------------
# Start Uvicorn in the background
# ---------------------------------------------------------------------------
print("🚀 Starting FastAPI inference server…")

server_process = subprocess.Popen(
    [
        sys.executable, "-m", "uvicorn",
        "remote_llm_server:app",
        "--host", "0.0.0.0",
        "--port", str(SERVER_PORT),
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

# ---------------------------------------------------------------------------
# Background log reader (non-blocking)
# ---------------------------------------------------------------------------
_server_started_event = threading.Event()

def _log_reader(proc: subprocess.Popen) -> None:
    for line in iter(proc.stdout.readline, ""):
        if not line:
            break
        print(f"[SERVER] {line.rstrip()}")
        # Signal that Uvicorn has at least started binding to the port
        if "Uvicorn running on" in line or "Application startup complete" in line:
            _server_started_event.set()

log_thread = threading.Thread(target=_log_reader, args=(server_process,), daemon=True)
log_thread.start()

# ---------------------------------------------------------------------------
# Wait for model to fully load
# ---------------------------------------------------------------------------
print(f"⏳ Waiting up to {STARTUP_TIMEOUT}s for model to load…")

# Wait a few seconds for Uvicorn to bind before polling
_server_started_event.wait(timeout=30)

start = time.time()
ready = False

while time.time() - start < STARTUP_TIMEOUT:

    # Abort if the process died
    if server_process.poll() is not None:
        raise RuntimeError(
            f"Uvicorn exited unexpectedly (code {server_process.returncode}). "
            "Check [SERVER] log lines above."
        )

    elapsed = int(time.time() - start)
    try:
        # Try /ready first (fast path)
        r = requests.get(f"http://127.0.0.1:{SERVER_PORT}/ready", timeout=3)
        if r.status_code == 200:
            print(f"[{elapsed:03d}s] ✅ Server reports: ready.")
            ready = True
            break
        elif r.status_code == 404:
            # Older server version without /ready — fall back to /health
            r2 = requests.get(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=3)
            if r2.status_code == 200 and r2.json().get("server_ready") is True:
                print(f"[{elapsed:03d}s] ✅ Server reports: ready (via /health).")
                ready = True
                break
            else:
                print(f"[{elapsed:03d}s] Model still loading…")
        elif r.status_code == 503:
            print(f"[{elapsed:03d}s] Model still loading…")
        else:
            print(f"[{elapsed:03d}s] Unexpected status {r.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[{elapsed:03d}s] Waiting for server to bind…")
    except Exception as exc:
        print(f"[{elapsed:03d}s] Poll error: {exc}")

    time.sleep(5)

if not ready:
    server_process.terminate()
    raise TimeoutError(
        f"Server did not become ready within {STARTUP_TIMEOUT}s. "
        "Increase STARTUP_TIMEOUT or check GPU memory."
    )

# ---------------------------------------------------------------------------
# Start ngrok tunnel
# ---------------------------------------------------------------------------
from pyngrok import ngrok

if NGROK_AUTH_TOKEN == "REPLACE_WITH_YOUR_TOKEN":
    raise ValueError(
        "Set NGROK_AUTH_TOKEN in your environment or replace the placeholder "
        "in start_server.py before running."
    )

ngrok.set_auth_token(NGROK_AUTH_TOKEN)
tunnel = ngrok.connect(SERVER_PORT)

# pyngrok returns either a string or an NgrokTunnel object
public_url: str = getattr(tunnel, "public_url", str(tunnel))

print("\n" + "=" * 50)
print("🌐  Public URL (copy this into LLM_SERVER_URL):")
print(f"    {public_url}")
print("=" * 50 + "\n")
print("✅ Server is running in the background.")
print("   To stop everything:  server_process.terminate(); ngrok.kill()")

# ---------------------------------------------------------------------------
# Keyboard-interrupt handler (useful when running as a script)
# ---------------------------------------------------------------------------

def _shutdown(signum, frame):
    print("\n⚠️  Interrupt received — shutting down…")
    server_process.terminate()
    try:
        ngrok.kill()
    except Exception:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)
