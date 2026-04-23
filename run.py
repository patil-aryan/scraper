"""
Pipeline wrapper: clean → scraper → enrich.

Usage:
  python run.py

Flow:
  0. Kills any leftover sessions from a previous run (Chromium, OpenVPN,
     WireGuard tunnels, zombie Pythons)
  1. Runs scraper.py until hashtag queue is empty
  2. Automatically starts enrich.py on creators found
  3. If you Ctrl+C during scraping, asks whether to continue to enrichment

This is the recommended way to run an overnight pass.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
PYTHON = sys.executable
CURRENT_PID = os.getpid()


def banner(text: str):
    line = "━" * 62
    print()
    print(line)
    print(f"  {text}")
    print(line)
    print()


def cleanup_previous_sessions():
    """Kill leftover processes from any previous scraper run."""
    banner("PHASE 0 — CLEANING UP PREVIOUS SESSIONS")

    # Kill leftover Chromium / Playwright browsers (from crashed scrapers)
    for proc_name in ("chrome", "chromium", "playwright"):
        try:
            r = subprocess.run(
                ["taskkill", "/F", "/IM", f"{proc_name}.exe"],
                capture_output=True, text=True, timeout=10,
            )
            killed = "killed" if r.returncode == 0 else "not running"
            print(f"  [cleanup] {proc_name}.exe — {killed}")
        except Exception as e:
            print(f"  [cleanup] {proc_name}.exe — {e}")

    # NOTE: We deliberately do NOT kill python.exe processes — that would risk
    # killing this run.py itself, the API server, the token refresher, and Cursor's
    # internal helpers. If you have zombie scrapers, kill them manually with
    # Task Manager or `taskkill /F /PID <pid>`.

    # Kill OpenVPN (legacy, in case it's still around)
    for name in ("openvpn", "openvpn-gui"):
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{name}.exe"],
            capture_output=True, timeout=10,
        )

    # Tear down any leftover WireGuard tunnels
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Service WireGuardTunnel* -ErrorAction SilentlyContinue | "
             "ForEach-Object { $_.Name -replace '^WireGuardTunnel\\$','' }"],
            capture_output=True, text=True, timeout=10,
        )
        tunnels = [t.strip() for t in r.stdout.splitlines() if t.strip()]
        if tunnels:
            print(f"  [cleanup] Removing {len(tunnels)} WireGuard tunnel(s): {tunnels}")
            wg_exe = r"C:\Program Files\WireGuard\wireguard.exe"
            if Path(wg_exe).exists():
                for t in tunnels:
                    subprocess.run(
                        [wg_exe, "/uninstalltunnelservice", t],
                        capture_output=True, timeout=10,
                    )
        else:
            print("  [cleanup] No leftover WireGuard tunnels")
    except Exception as e:
        print(f"  [cleanup] WireGuard cleanup failed: {e}")

    print("  [cleanup] Done. Pausing 3s for processes to fully exit…")
    time.sleep(3)


def run_step(script_name: str, label: str) -> tuple[int, bool]:
    """Run a script as a subprocess. Returns (exit_code, was_interrupted)."""
    banner(label)
    script_path = ROOT / script_name
    if not script_path.exists():
        print(f"[run.py] Missing {script_path}")
        return 1, False
    try:
        result = subprocess.run([PYTHON, str(script_path)])
        return result.returncode, False
    except KeyboardInterrupt:
        # Ctrl+C while the subprocess was running
        return 130, True


def ask_continue(reason: str) -> bool:
    """Prompt user y/n. Returns True to continue, False to abort."""
    print()
    try:
        resp = input(f"[run.py] {reason} Continue to enrichment? [Y/n] ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return resp != "n"


def main():
    overall_start = time.time()

    # ─── Phase 0: Cleanup ────────────────────────────────────────
    cleanup_previous_sessions()

    # ─── Phase 1: Scrape ─────────────────────────────────────────
    code, interrupted = run_step("scraper.py", "PHASE 1 of 2 — SCRAPING")

    if interrupted:
        if not ask_continue("Scraper interrupted."):
            print("[run.py] Exiting without enrichment.")
            return
    elif code != 0:
        print(f"[run.py] Scraper exited with code {code} — continuing to enrichment anyway.")
        time.sleep(3)
    else:
        print("[run.py] Scraper completed cleanly. Pausing 15s before enrichment…")
        try:
            time.sleep(15)
        except KeyboardInterrupt:
            if not ask_continue("Paused."):
                return

    # ─── Phase 2: Enrich ─────────────────────────────────────────
    code2, interrupted2 = run_step("enrich.py", "PHASE 2 of 2 — ENRICHING")

    if interrupted2:
        print("[run.py] Enrichment interrupted.")

    # ─── Done ────────────────────────────────────────────────────
    elapsed = time.time() - overall_start
    banner(f"PIPELINE COMPLETE — total runtime {elapsed/3600:.2f}h")
    print(f"  Scraper exit: {code}")
    print(f"  Enricher exit: {code2}")
    print()
    print("  Run  python analyze.py  for a filtered CSV export.")
    print("  Or open the UI at http://localhost:5173 to browse.")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[run.py] Interrupted.")
        sys.exit(130)
