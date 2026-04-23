"""
VPN rotation using WireGuard for Windows.

Setup (one-time):
1. Install WireGuard: https://download.wireguard.com/windows-client/wireguard-installer.exe
2. Go to https://account.protonvpn.com → Downloads → WireGuard configuration files
   - Pick "Linux" platform (smaller .conf, works on Windows)
   - Pick non-Free servers (paid tier)
   - Download 8-10 different country configs
3. Place .conf files in: C:\\Users\\<you>\\WireGuard\\config\\
   (or set WG_CONFIG_DIR in .env to your folder)
4. Run scraper as ADMINISTRATOR (required to install/uninstall tunnel services)
   Right-click PowerShell → Run as administrator

Why WireGuard:
- Connects in 1-2 seconds (OpenVPN takes 30-60s)
- Clean CLI via wireguard.exe — no GUI to get stuck
- Each .conf file becomes a Windows service tunnel
- Reliable, no zombie processes

How rotation works:
- wireguard.exe /installtunnelservice <conf-path>   → tunnel UP
- wireguard.exe /uninstalltunnelservice <name>      → tunnel DOWN
- Tunnel name = .conf filename without extension
"""
import logging
import os
import subprocess
import time
import urllib.request
from itertools import cycle
from pathlib import Path

log = logging.getLogger("vpn_rotate")

WIREGUARD_EXE_DEFAULT = r"C:\Program Files\WireGuard\wireguard.exe"
WG_CONFIG_DIR_DEFAULT = str(Path.home() / "WireGuard" / "config")

# Timing — WireGuard is fast, no need for huge waits
POST_DISCONNECT_WAIT = 2     # tunnel teardown is instant
POST_CONNECT_WAIT = 3        # tunnel up + first handshake
VERIFY_ATTEMPTS = 6          # 6 × 3s = 18s max to verify
VERIFY_INTERVAL = 3
MAX_FAILOVER_ATTEMPTS = 3    # if one config fails, try N next configs

_rotation_iter = None
_current_config = None       # full filename of active .conf
_current_tunnel = None       # tunnel name (filename without .conf)
_home_ip = None              # registered via set_home_ip()
_known_configs: set[str] = set()   # to detect when new files are added


def _discover_configs(config_dir, explicit=None):
    """Return a list of .conf filenames to rotate through."""
    if explicit:
        return [f.strip() for f in explicit if f.strip()]
    p = Path(config_dir)
    if not p.exists():
        log.warning(f"WireGuard config dir doesn't exist: {config_dir}")
        return []
    files = sorted(f.name for f in p.glob("*.conf"))

    free_configs = [f for f in files if "free" in f.lower()]
    if free_configs:
        log.warning(
            f"⚠ Free-tier Proton configs detected: {free_configs}. "
            f"These are overcrowded — prefer paid-tier servers."
        )

    if not files:
        log.warning(f"No .conf files found in {config_dir}")
    return files


def _run(cmd, timeout=20):
    """Run a subprocess. Returns True on rc=0."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, shell=False
        )
        log.info(f"WG cmd rc={r.returncode}: {' '.join(str(c) for c in cmd)}")
        if r.stdout:
            log.debug(f"stdout: {r.stdout.strip()[:400]}")
        if r.stderr:
            log.debug(f"stderr: {r.stderr.strip()[:400]}")
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        log.warning(f"WG cmd failed ({type(e).__name__}): {e}")
        return False


def current_ip(timeout=10):
    """Query public IP. Returns 'unknown' on failure."""
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            return r.read().decode().strip() or "unknown"
    except Exception:
        return "unknown"


def set_home_ip(ip: str):
    """Register the user's real home IP for leak detection."""
    global _home_ip
    if ip and ip != "unknown":
        _home_ip = ip
        log.info(f"Home IP registered: {ip} (rotations must land on a different IP)")


def get_home_ip() -> str | None:
    return _home_ip


def cleanup_all_tunnels(cli_path: str = "") -> int:
    """Remove every WireGuardTunnel$* Windows service. Call this at startup
    to make sure no leftover tunnels from previous runs are competing for routes.
    Returns the number of tunnels removed."""
    global _current_config, _current_tunnel
    wg_exe = cli_path or os.getenv("WIREGUARD_EXE") or WIREGUARD_EXE_DEFAULT

    if not Path(wg_exe).exists():
        return 0

    # PowerShell to list all WireGuard tunnel services
    try:
        ps = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Service WireGuardTunnel* -ErrorAction SilentlyContinue | "
             "ForEach-Object { $_.Name -replace '^WireGuardTunnel\\$','' }"],
            capture_output=True, text=True, timeout=10,
        )
        tunnels = [t.strip() for t in ps.stdout.splitlines() if t.strip()]
    except Exception as e:
        log.warning(f"Could not list WireGuard tunnels: {e}")
        return 0

    if not tunnels:
        log.info("No leftover WireGuard tunnels to clean up.")
        return 0

    log.warning(f"Cleaning up {len(tunnels)} leftover WireGuard tunnel(s): {tunnels}")
    for name in tunnels:
        _run([wg_exe, "/uninstalltunnelservice", name])

    _current_tunnel = None
    _current_config = None
    time.sleep(3)
    return len(tunnels)


def detect_home_ip(cli_path: str = "") -> str | None:
    """Disconnect any active tunnel and detect the user's true home IP."""
    cleanup_all_tunnels(cli_path)

    ip = current_ip()
    if ip != "unknown":
        set_home_ip(ip)
        return ip
    log.warning("Could not detect home IP (ipify unreachable)")
    return None


def _try_one_config(wg_exe: str, config_dir: str, conf_name: str, old_ip: str) -> tuple[bool, str]:
    """Switch to one config. Returns (ok, observed_ip)."""
    global _current_config, _current_tunnel

    # Tear down current tunnel
    if _current_tunnel:
        _run([wg_exe, "/uninstalltunnelservice", _current_tunnel])
        time.sleep(POST_DISCONNECT_WAIT)

    conf_path = str(Path(config_dir) / conf_name)
    tunnel_name = Path(conf_name).stem

    if not _run([wg_exe, "/installtunnelservice", conf_path]):
        log.error(
            f"Failed to install tunnel {tunnel_name}. "
            f"Are you running as Administrator?"
        )
        return False, "unknown"

    log.info(f"Waiting {POST_CONNECT_WAIT}s for {tunnel_name} to establish…")
    time.sleep(POST_CONNECT_WAIT)

    new_ip = "unknown"
    for attempt in range(1, VERIFY_ATTEMPTS + 1):
        new_ip = current_ip()

        if new_ip == "unknown":
            log.info(f"[verify {attempt}/{VERIFY_ATTEMPTS}] Cannot reach ipify yet")
            time.sleep(VERIFY_INTERVAL)
            continue

        if _home_ip and new_ip == _home_ip:
            log.warning(f"[verify {attempt}/{VERIFY_ATTEMPTS}] LEAK — got home IP ({new_ip})")
            time.sleep(VERIFY_INTERVAL)
            continue

        if new_ip == old_ip:
            log.info(f"[verify {attempt}/{VERIFY_ATTEMPTS}] Still on old IP ({new_ip})")
            time.sleep(VERIFY_INTERVAL)
            continue

        _current_config = conf_name
        _current_tunnel = tunnel_name
        log.warning(f"✓ Connected to {tunnel_name} — new IP: {new_ip}")
        return True, new_ip

    _current_config = conf_name
    _current_tunnel = tunnel_name
    return False, new_ip


def rotate(cli_path: str = "") -> bool:
    """Rotate to the next WireGuard config, with failover.
    Returns True iff verified non-home IP achieved."""
    global _rotation_iter

    wg_exe = cli_path or os.getenv("WIREGUARD_EXE") or WIREGUARD_EXE_DEFAULT
    config_dir = os.getenv("WG_CONFIG_DIR") or WG_CONFIG_DIR_DEFAULT
    explicit_files = (
        os.getenv("WG_FILES", "").split(",") if os.getenv("WG_FILES") else None
    )

    if not Path(wg_exe).exists():
        log.error(f"WireGuard not found at: {wg_exe}")
        log.error("Install from https://download.wireguard.com/windows-client/")
        return False

    configs = _discover_configs(config_dir, explicit_files)
    if not configs:
        log.error(f"No .conf files in {config_dir}")
        return False

    # Rebuild iterator if config set changed (new files added)
    global _known_configs
    config_set = set(configs)
    if _rotation_iter is None or config_set != _known_configs:
        if _known_configs and config_set != _known_configs:
            new = config_set - _known_configs
            removed = _known_configs - config_set
            if new:
                log.info(f"⟳ Detected {len(new)} new config(s): {sorted(new)}")
            if removed:
                log.info(f"⟳ Removed {len(removed)} config(s): {sorted(removed)}")
        _rotation_iter = cycle(configs)
        _known_configs = config_set

    old_ip = current_ip()
    starting = _current_tunnel

    for attempt_n in range(1, MAX_FAILOVER_ATTEMPTS + 1):
        next_conf = next(_rotation_iter)
        log.warning(
            f"VPN rotation [{attempt_n}/{MAX_FAILOVER_ATTEMPTS}]: "
            f"{starting or 'none'} → {Path(next_conf).stem} "
            f"(old IP: {old_ip}, home IP: {_home_ip or 'not set'})"
        )

        ok, observed_ip = _try_one_config(wg_exe, config_dir, next_conf, old_ip)
        if ok:
            return True

        log.warning(
            f"✗ {next_conf} did not establish (final IP: {observed_ip}). "
            f"{'Trying next config…' if attempt_n < MAX_FAILOVER_ATTEMPTS else 'Giving up.'}"
        )

    log.error(
        f"✗ VPN rotation FAILED after {MAX_FAILOVER_ATTEMPTS} attempts. "
        f"Worker will pause and retry on next rotation cycle."
    )
    return False


def disconnect_all(cli_path: str = ""):
    """Tear down the active tunnel."""
    global _current_config, _current_tunnel
    wg_exe = cli_path or os.getenv("WIREGUARD_EXE") or WIREGUARD_EXE_DEFAULT
    if _current_tunnel and Path(wg_exe).exists():
        _run([wg_exe, "/uninstalltunnelservice", _current_tunnel])
        _current_tunnel = None
        _current_config = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("Detecting home IP…")
    home = detect_home_ip()
    print(f"Home IP: {home}")
    for i in range(3):
        print(f"\n=== Rotation {i+1} ===")
        ok = rotate()
        print(f"Result: {'OK' if ok else 'FAILED'}")
        time.sleep(3)
    disconnect_all()
