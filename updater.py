import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests

from config import VERSION, get, is_frozen

log = logging.getLogger(__name__)

# Default GitHub repo for auto-updates (owner/name)
DEFAULT_UPDATE_REPO = "HITESHDAS-01/ai-proofreader-releases"


def current_version() -> str:
    return (VERSION or "0.0.0").strip()


def update_repo() -> str:
    repo = (get("update_repo") or "").strip() or DEFAULT_UPDATE_REPO
    return repo.strip("/")


def _parse_ver(v: str) -> tuple:
    v = (v or "").strip().lstrip("vV")
    parts = []
    for p in re.split(r"[^\d]+", v):
        if p.isdigit():
            parts.append(int(p))
        if len(parts) >= 3:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(remote: str, local: str) -> bool:
    try:
        return _parse_ver(remote) > _parse_ver(local)
    except Exception:
        return False


def check_for_update() -> dict | None:
    """Return {version, url, notes} if a newer release exists, else None.

    Returns {"error": str} on failure is NOT used — raises or returns None.
    """
    repo = update_repo()
    if not repo:
        return None
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    resp = requests.get(
        url,
        timeout=15,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "AI-Proofreader"},
    )
    resp.raise_for_status()
    data = resp.json()
    tag = str(data.get("tag_name") or "")
    if not is_newer(tag, current_version()):
        return None
    assets = data.get("assets") or []
    exe_url = ""
    for a in assets:
        name = (a.get("name") or "").lower()
        if name.endswith(".exe") or name.endswith(".zip"):
            exe_url = a.get("browser_download_url") or ""
            if name.endswith(".exe"):
                break
    if not exe_url:
        html = data.get("html_url") or ""
        return {
            "version": tag,
            "url": html,
            "notes": str(data.get("body") or "")[:2000],
            "needs_manual": True,
        }
    return {
        "version": tag,
        "url": exe_url,
        "notes": str(data.get("body") or "")[:2000],
        "needs_manual": False,
    }


def _target_exe() -> Path:
    if is_frozen() and getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(sys.argv[0]).resolve()


def download_update(info: dict, progress_cb=None) -> Path:
    """Download new exe to temp. Returns path to downloaded file."""
    url = info["url"]
    if info.get("needs_manual"):
        raise RuntimeError("manual download required")
    tmp_dir = Path(tempfile.gettempdir()) / "AIProofreader_update"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    dest = tmp_dir / "AI_Proofreader.exe.new"
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        chunk_size = 1024 * 256
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    try:
                        progress_cb(done, total)
                    except Exception:
                        pass
    if dest.stat().st_size < 1024 * 500:
        dest.unlink(missing_ok=True)
        raise RuntimeError("download looks incomplete")
    return dest


def _write_apply_script(new_exe: Path, target: Path) -> Path:
    """Write a bat that waits for this process to exit, then swaps the exe."""
    scripts_dir = Path(tempfile.gettempdir()) / "AIProofreader_update"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    bat = scripts_dir / "apply_update.bat"
    pid = os.getpid()
    bat_body = (
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "TARGET={target}"\r\n'
        f'set "NEW={new_exe}"\r\n'
        f"set PID={pid}\r\n"
        ":waitloop\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        f'tasklist /FI "PID eq %PID%" 2>nul | findstr /I "%PID%" >nul\r\n'
        "if not errorlevel 1 goto waitloop\r\n"
        'if exist "%TARGET%" del /F /Q "%TARGET%" 2>nul\r\n'
        'copy /Y "%NEW%" "%TARGET%" >nul\r\n'
        'if errorlevel 1 exit /b 1\r\n'
        'start "" "%TARGET%"\r\n'
        'del /F /Q "%~f0"\r\n'
        "endlocal\r\n"
    )
    bat.write_text(bat_body, encoding="utf-8")
    return bat


def apply_update_and_restart(new_exe: Path) -> None:
    """Spawn script, exit current app; script swaps exe and relaunches."""
    target = _target_exe()
    if not is_frozen():
        raise RuntimeError("update apply only in packaged exe")
    bat = _write_apply_script(Path(new_exe).resolve(), target)
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(bat.parent),
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200),
        close_fds=True,
    )
    log.info("update script launched, exiting app for replace")
    time.sleep(0.5)
    os._exit(0)


def check_async(callback) -> None:
    """Run check_for_update off-thread; callback(info|None|Exception)."""

    def _run():
        try:
            callback(check_for_update())
        except Exception as exc:
            callback(exc)

    threading.Thread(target=_run, daemon=True).start()


def open_release_page() -> None:
    import webbrowser

    repo = update_repo()
    if repo:
        webbrowser.open(f"https://github.com/{repo}/releases/latest")
