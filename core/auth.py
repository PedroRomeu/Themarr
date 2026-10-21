"""Server mode login: Jellyfin administrators sign in with their own Jellyfin account"""
import os
import secrets

import requests

from core.config import CONFIG_FOLDER, load_config

SECRET_FILE = os.path.join(CONFIG_FOLDER, 'secret_key')
JELLYFIN_CLIENT_HEADER = 'MediaBrowser Client="Themarr", Device="Themarr Server", DeviceId="themarr-server", Version="1.0"'


def get_secret_key():
    """Session signing key, created once and kept in the config volume so logins survive restarts"""
    if os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, 'r', encoding='utf-8') as f:
            key = f.read().strip()
            if key:
                return key
    key = secrets.token_hex(32)
    with open(SECRET_FILE, 'w', encoding='utf-8') as f:
        f.write(key)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass
    return key


def authenticate_jellyfin_admin(username, password):
    """Checks the credentials against Jellyfin. Returns {"ok": bool, "name"|"message": str}"""
    jelly_url = (load_config().get("jelly_url") or "").rstrip('/')
    if not jelly_url:
        return {"ok": False, "message": "Jellyfin URL is not configured (JELLYFIN_URL)."}

    try:
        res = requests.post(
            f"{jelly_url}/Users/AuthenticateByName",
            json={"Username": username, "Pw": password},
            headers={"X-Emby-Authorization": JELLYFIN_CLIENT_HEADER},
            timeout=15
        )
    except Exception as e:
        print(f"[AUTH] Jellyfin unreachable: {e}")
        return {"ok": False, "message": "Could not reach Jellyfin."}

    if res.status_code != 200:
        return {"ok": False, "message": "Invalid username or password."}

    data = res.json()
    user = data.get("User") or {}

    # Themarr only needed the answer: close the Jellyfin session it just opened
    token = data.get("AccessToken")
    if token:
        try:
            requests.post(f"{jelly_url}/Sessions/Logout", headers={"X-Emby-Token": token}, timeout=10)
        except Exception:
            pass

    if not (user.get("Policy") or {}).get("IsAdministrator"):
        return {"ok": False, "message": "Only Jellyfin administrators can use Themarr."}
    return {"ok": True, "name": user.get("Name", username)}
