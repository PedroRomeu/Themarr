"""Update check: compares APP_VERSION with the latest GitHub release, like Sonarr's System > Updates.
On the Windows build it can also download the new zip and swap the files (see install_update)."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

import requests

from core.config import APP_VERSION, APP_ROOT_DIR, IS_WINDOWS, SERVER_MODE

RELEASES_URL = "https://api.github.com/repos/themarr-jellyfin/Themarr/releases/latest"
CHECK_EVERY = 6 * 3600

_cache = {"time": 0, "result": None}
_lock = threading.Lock()
install_state = {"stage": "idle", "downloaded": 0, "total": 0, "message": ""}


def parse_version(text):
    """'v1.14.0' or '1.14.0' -> (1, 14, 0). Anything after the numbers is ignored"""
    numbers = re.findall(r'\d+', str(text or '').split('-')[0])
    return tuple(int(n) for n in numbers[:3]) or (0,)


def can_self_update():
    """Only the Windows build can replace its own files. Source checkouts and Docker update another way"""
    return getattr(sys, 'frozen', False) and IS_WINDOWS and not SERVER_MODE


def check_for_update(force=False):
    with _lock:
        if not force and _cache["result"] and time.time() - _cache["time"] < CHECK_EVERY:
            return _cache["result"]
        try:
            # THEMARR_UPDATE_FEED points the check at another release feed, for testing the updater
            res = requests.get(os.environ.get('THEMARR_UPDATE_FEED', RELEASES_URL), timeout=10,
                               headers={"Accept": "application/vnd.github+json", "User-Agent": f"Themarr/{APP_VERSION}"})
            res.raise_for_status()
            release = res.json()
        except Exception as e:
            return {"success": False, "current": APP_VERSION, "message": f"Could not reach GitHub: {e}"}

        latest = str(release.get("tag_name", "")).lstrip('v')
        asset = next((a for a in release.get("assets", []) if str(a.get("name", "")).lower().endswith('.zip')), None)
        result = {
            "success": True,
            "current": APP_VERSION,
            "latest": latest,
            "newer": parse_version(latest) > parse_version(APP_VERSION),
            "name": release.get("name") or f"v{latest}",
            "notes": release.get("body") or "",
            "url": release.get("html_url") or "https://github.com/themarr-jellyfin/Themarr/releases/latest",
            "published": release.get("published_at"),
            "asset_url": asset.get("browser_download_url") if asset else None,
            "asset_size": asset.get("size") if asset else 0,
            "can_self_update": can_self_update(),
            "checked_at": time.time(),
        }
        _cache.update(time=time.time(), result=result)
        return result


# ---------------------------------------------------------------------------
# One-click update of the Windows build
# ---------------------------------------------------------------------------
# A running exe cannot overwrite itself, so Themarr downloads and unpacks the new zip, starts a small
# PowerShell script and exits. The script waits for it to close, swaps _internal and the two exes (keeping
# the old ones until the copy succeeds, and putting them back if it fails), and starts Themarr again.
# Settings live in the user profile and backups/ is never touched.

UPDATER_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$log = '__LOG__'
function Log($text) { Add-Content -Path $log -Value "$(Get-Date -Format s) $text" }
$appDir = '__APP__'
$newDir = '__NEW__'
$exe = '__EXE__'
$exes = @('Themarr_Desktop.exe', 'Themarr_Server.exe')
$internal = Join-Path $appDir '_internal'
$oldInternal = Join-Path $appDir '_internal.old'
try {
    Log "Waiting for Themarr (pid __PID__) to close"
    Wait-Process -Id __PID__ -Timeout 60 -ErrorAction SilentlyContinue
    Get-Process Themarr_Desktop, Themarr_Server -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($appDir) } | Stop-Process -Force
    Start-Sleep -Seconds 1

    if (Test-Path $oldInternal) { Remove-Item $oldInternal -Recurse -Force }
    Rename-Item $internal '_internal.old'
    foreach ($name in $exes) {
        $current = Join-Path $appDir $name
        if (Test-Path "$current.old") { Remove-Item "$current.old" -Force }
        if (Test-Path $current) { Rename-Item $current "$name.old" }
    }

    Copy-Item (Join-Path $newDir '_internal') $appDir -Recurse
    foreach ($name in $exes) { Copy-Item (Join-Path $newDir $name) (Join-Path $appDir $name) }
    Log "New version copied"

    Remove-Item $oldInternal -Recurse -Force
    foreach ($name in $exes) { Remove-Item (Join-Path $appDir "$name.old") -Force -ErrorAction SilentlyContinue }
} catch {
    Log "Update failed, restoring the previous version: $_"
    if (Test-Path $oldInternal) {
        if (Test-Path $internal) { Remove-Item $internal -Recurse -Force }
        Rename-Item $oldInternal '_internal'
    }
    foreach ($name in $exes) {
        $current = Join-Path $appDir $name
        if (Test-Path "$current.old") {
            if (Test-Path $current) { Remove-Item $current -Force }
            Rename-Item "$current.old" $name
        }
    }
}
Log "Starting $exe"
Start-Process -FilePath $exe -WorkingDirectory $appDir
# The download and this script live in their own temp folder: remove all of it
Set-Location $env:TEMP
Remove-Item $PSScriptRoot -Recurse -Force -ErrorAction SilentlyContinue
'''


def _ps_quote(text):
    return str(text).replace("'", "''")


def install_update():
    if not can_self_update():
        return {"success": False, "message": "This copy of Themarr cannot update itself. Download the new version instead."}
    if install_state["stage"] in ("downloading", "preparing", "restarting"):
        return {"success": False, "message": "The update is already running."}
    info = check_for_update(force=True)
    if not info.get("success"):
        return {"success": False, "message": info.get("message", "Could not check for updates.")}
    if not info.get("newer") or not info.get("asset_url"):
        return {"success": False, "message": "There is no newer version to install."}

    install_state.update(stage="downloading", downloaded=0, total=info.get("asset_size") or 0, message="")
    threading.Thread(target=_install_thread, args=(info,), daemon=True).start()
    return {"success": True}


def _install_thread(info):
    work = tempfile.mkdtemp(prefix="themarr_update_")
    try:
        print(f"[UPDATE] Downloading Themarr {info['latest']}...")
        zip_path = os.path.join(work, "update.zip")
        with requests.get(info["asset_url"], stream=True, timeout=30, headers={"User-Agent": f"Themarr/{APP_VERSION}"}) as res:
            res.raise_for_status()
            install_state["total"] = int(res.headers.get("Content-Length") or install_state["total"] or 0)
            with open(zip_path, "wb") as f:
                for chunk in res.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    install_state["downloaded"] += len(chunk)

        install_state["stage"] = "preparing"
        extract_dir = os.path.join(work, "new")
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if name.startswith(('/', '\\')) or '..' in re.split(r'[\\/]', name) or ':' in name:
                    raise ValueError(f"Unexpected path in the update: {name}")
            archive.extractall(extract_dir)
        os.remove(zip_path)

        # The release zip holds one folder, Themarr_vX.Y.Z/, with both exes and _internal
        entries = os.listdir(extract_dir)
        new_root = os.path.join(extract_dir, entries[0]) if len(entries) == 1 else extract_dir
        if not (os.path.isfile(os.path.join(new_root, "Themarr_Desktop.exe")) and
                os.path.isfile(os.path.join(new_root, "Themarr_Server.exe")) and
                os.path.isdir(os.path.join(new_root, "_internal"))):
            raise ValueError("The downloaded file is not a Themarr build.")

        script_path = os.path.join(work, "update.ps1")
        script = (UPDATER_SCRIPT
                  .replace('__LOG__', _ps_quote(os.path.join(tempfile.gettempdir(), "themarr_update.log")))
                  .replace('__APP__', _ps_quote(os.path.normpath(APP_ROOT_DIR)))
                  .replace('__NEW__', _ps_quote(os.path.normpath(new_root)))
                  .replace('__EXE__', _ps_quote(sys.executable))
                  .replace('__PID__', str(os.getpid())))
        with open(script_path, "w", encoding="utf-8-sig") as f:
            f.write(script)

        install_state["stage"] = "restarting"
        print(f"[UPDATE] Installing {info['latest']}: Themarr closes and opens again in a few seconds.")
        # A hidden console of its own: with DETACHED_PROCESS PowerShell gets no console from the windowed exe and quits
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path],
                         creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Give the page a moment to read the "restarting" state, then exit so the files can be replaced
        threading.Timer(2.0, lambda: os._exit(0)).start()
    except Exception as e:
        print(f"[UPDATE] ❌ Update failed: {e}")
        install_state.update(stage="error", message=str(e))
        shutil.rmtree(work, ignore_errors=True)
