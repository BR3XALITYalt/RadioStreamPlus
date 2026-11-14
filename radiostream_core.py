#!/usr/bin/env python3
"""RadioStream+ receiver directory, geospatial filtering, and tune settings."""
from __future__ import annotations

import html
import ipaddress
import json
import math
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5056
DIRECTORY_URL = "https://cdn.aethersdr.com/kiwi.json"
DIRECTORY_MAX_AGE = 30 * 60
DIRECTORY_MAX_BYTES = 32 * 1024 * 1024
HAMQSL_URL = "https://www.hamqsl.com/solarxml.php"
APP_USER_AGENT = "RadioStreamPlus/1.0 (local KiwiSDR browser-stream manager)"
# Stable pseudonymous KiwiSDR identity for this RadioStream+ process.
RADIOSTREAM_IDENT = "rsplus-" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(4))
CONFIG_PATH = APP_DIR / "radiostream.json"
DIRECTORY_CACHE_PATH = APP_DIR / "kiwi_directory_cache.json"
STATION_PREFERENCES_PATH = APP_DIR / "station_preferences.json"
STATION_PREFERENCES_LOCK = threading.RLock()
station_preferences: dict[str, str] = {}


def load_station_preferences() -> None:
    """Load liked, disliked, and blocked receiver IDs from the local preferences file."""
    global station_preferences
    try:
        payload = json.loads(STATION_PREFERENCES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        with STATION_PREFERENCES_LOCK:
            station_preferences = {}
        return
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[preferences] Could not load station preferences: {exc}", file=sys.stderr)
        return

    raw_stations = payload.get("stations") if isinstance(payload, dict) else None
    if not isinstance(raw_stations, dict):
        print("[preferences] Ignoring invalid station preferences file", file=sys.stderr)
        return

    cleaned: dict[str, str] = {}
    for station_id, preference in raw_stations.items():
        station_id = str(station_id).strip()
        if (
            station_id
            and len(station_id) <= 2048
            and isinstance(preference, str)
            and preference in {"like", "dislike", "block"}
        ):
            cleaned[station_id] = preference
    with STATION_PREFERENCES_LOCK:
        station_preferences = cleaned


def get_station_preference(station_id: str) -> str | None:
    with STATION_PREFERENCES_LOCK:
        return station_preferences.get(str(station_id))


def set_station_preference(station_id: str, preference: str) -> str | None:
    """Persist one station preference. 'none' clears the existing preference."""
    global station_preferences
    station_id = str(station_id or "").strip()
    preference = str(preference or "").strip().lower()
    if not station_id or len(station_id) > 2048:
        raise ValueError("A valid station ID is required")
    if preference not in {"like", "dislike", "block", "none"}:
        raise ValueError("Preference must be like, dislike, block, or none")

    with STATION_PREFERENCES_LOCK:
        updated = dict(station_preferences)
        if preference == "none":
            updated.pop(station_id, None)
        else:
            updated[station_id] = preference
        if len(updated) > 20000:
            raise ValueError("The station preference list is full")

        payload = json.dumps({"schema": 1, "stations": updated}, indent=2) + "\n"
        temporary = STATION_PREFERENCES_PATH.with_suffix(".json.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            temporary.replace(STATION_PREFERENCES_PATH)
        except OSError as exc:
            raise RuntimeError(f"Could not save station preferences: {exc}") from exc

        station_preferences = updated
    return None if preference == "none" else preference

DEFAULT_CONFIG: dict[str, Any] = {
    "center_lat": 20.0,
    "center_lon": 0.0,
    "radius_km": 500,
    "frequency_khz": 4625.0,
    "mode": "usb",
    "zoom": 11,
    "volume": 180,
    "passband_low": 300,
    "passband_high": 2700,
    "rotation_minutes": 14,
    "directory_cache_minutes": 30,
}
# KiwiSDR's built-in passband fallback values, in Hz relative to the tuned carrier.
MODE_DEFAULT_PASSBANDS: dict[str, tuple[int, int]] = {
    "am": (-4900, 4900),
    "lsb": (-2700, -300),
    "usb": (300, 2700),
    "cw": (300, 700),
    "nbfm": (-6000, 6000),
}
VALID_MODES = set(MODE_DEFAULT_PASSBANDS)
CONFIG_LOCK = threading.RLock()
DIRECTORY_LOCK = threading.RLock()

config: dict[str, Any] = dict(DEFAULT_CONFIG)
directory_data: dict[str, Any] | None = None
directory_fetched_monotonic = 0.0
directory_fetched_at: str | None = None
directory_error: str | None = None

RECEIVER_PROBE_TIMEOUT = 2.0
RECEIVER_PROBE_MAX_BYTES = 256 * 1024
RECEIVER_HEALTH_CACHE_SECONDS = 90
MAX_RECEIVER_PROBES = 8
RECEIVER_HEALTH_LOCK = threading.RLock()
RECEIVER_HEALTH_CACHE: dict[str, tuple[float, bool, str]] = {}


def is_offline_receiver_page(page_text: str) -> bool:
    """Recognize KiwiSDR proxy offline and required-identity pages."""
    visible_text = re.sub(r"<[^>]*>", " ", page_text)
    normalized = " ".join(html.unescape(visible_text).casefold().split())
    return any(marker in normalized for marker in (
        "is not online",
        "is currently offline",
        "kiwi is offline",
        "receiver is offline",
        "enter your name or callsign to start kiwisdr",
    ))


def _public_hostname(hostname: str, port: int) -> bool:
    """Reject local and reserved address targets from the public directory."""
    addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    if not addresses:
        return False
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            return False
    return True


class _PublicOnlyRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not follow receiver redirects into private or local address space."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not _public_hostname(parsed.hostname, port):
                return None
        except (OSError, ValueError):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_receiver_online(receiver: dict[str, Any]) -> tuple[bool, str]:
    """Check a receiver's public landing page before sending it to the player.

    The public directory is a cached snapshot. Short-lived health results stop
    the player from repeatedly opening receivers that have gone offline.
    """
    base_url = str(receiver.get("url") or "").rstrip("/")
    if not base_url:
        return False, "Receiver has no URL"

    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "Receiver URL is invalid"

    probe_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path or "/", "", "")
    )
    now = time.monotonic()
    with RECEIVER_HEALTH_LOCK:
        cached = RECEIVER_HEALTH_CACHE.get(probe_url)
        if cached and now - cached[0] < RECEIVER_HEALTH_CACHE_SECONDS:
            return cached[1], cached[2]

    def remember(online: bool, reason: str) -> tuple[bool, str]:
        with RECEIVER_HEALTH_LOCK:
            RECEIVER_HEALTH_CACHE[probe_url] = (time.monotonic(), online, reason)
            if len(RECEIVER_HEALTH_CACHE) > 2000:
                current_time = time.monotonic()
                expired = [
                    key for key, value in RECEIVER_HEALTH_CACHE.items()
                    if current_time - value[0] >= RECEIVER_HEALTH_CACHE_SECONDS
                ]
                for key in expired:
                    RECEIVER_HEALTH_CACHE.pop(key, None)
        return online, reason

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not _public_hostname(parsed.hostname, port):
            return remember(False, "Receiver hostname does not resolve to a public address")
    except (OSError, ValueError) as exc:
        return remember(False, f"Receiver DNS lookup failed: {exc}")

    request_obj = urllib.request.Request(
        probe_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; RadioStreamPlus/1.0)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )
    opener = urllib.request.build_opener(_PublicOnlyRedirectHandler())
    try:
        with opener.open(request_obj, timeout=RECEIVER_PROBE_TIMEOUT) as response:
            body = response.read(RECEIVER_PROBE_MAX_BYTES).decode("utf-8", "replace")
            if is_offline_receiver_page(body):
                return remember(False, "KiwiSDR page reports that it is offline or still requires a visitor name")
            if not 200 <= response.status < 400:
                return remember(False, f"Receiver returned HTTP {response.status}")
        return remember(True, "Receiver responded")
    except (OSError, urllib.error.URLError, TimeoutError, ValueError) as exc:
        return remember(False, f"Receiver could not be reached: {exc}")




def clamp_number(value: Any, name: str, low: float, high: float, integer: bool = False) -> float | int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(number) or number < low or number > high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return int(number) if integer else number


def load_config() -> None:
    global config
    if CONFIG_PATH.exists():
        try:
            parsed = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                config = validate_config(parsed, allow_partial=True)
                return
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"[config] Could not load radiostream.json: {exc}", file=sys.stderr)
    config = dict(DEFAULT_CONFIG)
    save_config()


def validate_config(raw: dict[str, Any], allow_partial: bool = False) -> dict[str, Any]:
    base = dict(DEFAULT_CONFIG) if allow_partial else dict(config)
    base.update(raw)
    result = {
        "center_lat": clamp_number(base["center_lat"], "Latitude", -90, 90),
        "center_lon": clamp_number(base["center_lon"], "Longitude", -180, 180),
        "radius_km": clamp_number(base["radius_km"], "Range", 1, 20000),
        "frequency_khz": clamp_number(base["frequency_khz"], "Frequency (kHz)", 10, 30000),
        "mode": str(base["mode"]).lower(),
        "zoom": clamp_number(base["zoom"], "KiwiSDR zoom", 0, 14, integer=True),
        "volume": clamp_number(base["volume"], "Volume", 0, 200, integer=True),
        "passband_low": clamp_number(base["passband_low"], "Passband low", -12000, 12000, integer=True),
        "passband_high": clamp_number(base["passband_high"], "Passband high", -12000, 12000, integer=True),
        "rotation_minutes": clamp_number(base["rotation_minutes"], "Rotation interval", 3, 60),
        "directory_cache_minutes": 30,
    }
    if result["mode"] not in VALID_MODES:
        raise ValueError("Mode must be AM, LSB, USB, CW, or NBFM")
    if result["passband_low"] >= result["passband_high"]:
        raise ValueError("Passband low must be smaller than passband high")
    return result


def save_config() -> None:
    temporary = CONFIG_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_PATH)


def load_disk_directory() -> None:
    global directory_data, directory_fetched_at, directory_fetched_monotonic
    if not DIRECTORY_CACHE_PATH.exists():
        return
    try:
        payload = json.loads(DIRECTORY_CACHE_PATH.read_text(encoding="utf-8"))
        validate_directory(payload)
        directory_data = payload
        directory_fetched_at = payload.get("fetched_at")
        # A disk cache is deliberately considered stale after restart. It is
        # still available immediately while a fresh mirror request is made.
        directory_fetched_monotonic = 0.0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[directory] Ignoring invalid disk cache: {exc}", file=sys.stderr)


def validate_directory(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("KiwiSDR directory has an unsupported schema")
    receivers = payload.get("receivers")
    if not isinstance(receivers, list) or len(receivers) > 20000:
        raise ValueError("KiwiSDR directory has an invalid receiver list")
    return [item for item in receivers if isinstance(item, dict)]


def fetch_directory(force: bool = False) -> dict[str, Any]:
    global directory_data, directory_fetched_monotonic, directory_fetched_at, directory_error
    with DIRECTORY_LOCK:
        age = time.monotonic() - directory_fetched_monotonic
        if directory_data is not None and age < DIRECTORY_MAX_AGE:
            return directory_data
        # A manual Refresh button may request an update, but never bypasses
        # the data provider's 30-minute public cache window.
        request_obj = urllib.request.Request(
            DIRECTORY_URL,
            headers={"User-Agent": APP_USER_AGENT, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=20) as response:
                body = response.read(DIRECTORY_MAX_BYTES + 1)
            if len(body) > DIRECTORY_MAX_BYTES:
                raise ValueError("KiwiSDR directory exceeded the 32 MB safety limit")
            payload = json.loads(body.decode("utf-8"))
            validate_directory(payload)
            directory_data = payload
            directory_fetched_at = payload.get("fetched_at")
            directory_fetched_monotonic = time.monotonic()
            directory_error = None
            try:
                temporary = DIRECTORY_CACHE_PATH.with_suffix(".json.tmp")
                temporary.write_text(json.dumps(payload), encoding="utf-8")
                temporary.replace(DIRECTORY_CACHE_PATH)
            except OSError as exc:
                print(f"[directory] Could not persist cache: {exc}", file=sys.stderr)
            return payload
        except (OSError, urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            directory_error = str(exc)
            if directory_data is not None:
                print(f"[directory] Refresh failed; using cached data: {exc}", file=sys.stderr)
                directory_fetched_monotonic = time.monotonic() - (DIRECTORY_MAX_AGE - 300)
                return directory_data
            raise RuntimeError(f"Could not download the KiwiSDR public directory: {exc}") from exc


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def receiver_id(receiver: dict[str, Any]) -> str:
    return str(receiver.get("id") or receiver.get("url") or "")


def parse_receiver(receiver: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    url = receiver.get("url")
    if not isinstance(url, str):
        return None
    parsed_url = urllib.parse.urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname or parsed_url.username or parsed_url.password:
        return None
    gps = receiver.get("gps")
    if not isinstance(gps, list) or len(gps) != 2:
        return None
    try:
        lat, lon = float(gps[0]), float(gps[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        return None  # KiwiSDR uses [0, 0] to mean no GPS fix.

    distance = haversine_km(cfg["center_lat"], cfg["center_lon"], lat, lon)
    if distance > cfg["radius_km"]:
        return None

    frequency_hz = cfg["frequency_khz"] * 1000
    bands = receiver.get("bands")
    band_ok = True
    if isinstance(bands, list) and len(bands) == 2:
        try:
            low, high = float(bands[0]), float(bands[1])
            band_ok = low <= frequency_hz <= high and high > low
        except (TypeError, ValueError):
            band_ok = True

    try:
        users = max(0, int(receiver.get("users") or 0))
        users_max = max(0, int(receiver.get("users_max") or 0))
    except (TypeError, ValueError):
        users, users_max = 0, 0
    occupancy = (users / users_max * 100.0) if users_max else 0.0
    snr_pair = receiver.get("snr")
    snr_hf = receiver.get("snr_hf", 0)
    if isinstance(snr_pair, list) and len(snr_pair) > 1:
        snr_hf = snr_pair[1]
    try:
        snr_hf = float(snr_hf or 0)
    except (TypeError, ValueError):
        snr_hf = 0.0

    offline = receiver.get("offline") is True or str(receiver.get("offline", "")).strip().casefold() in {"yes", "true", "1", "offline", "down"}
    flagged = receiver.get("flagged") is True or str(receiver.get("flagged", "")).strip().casefold() in {"yes", "true", "1", "flagged"}
    full = users_max > 0 and users >= users_max
    directory_available = not offline and not flagged and not full and band_ok
    station_id = receiver_id(receiver)
    preference = get_station_preference(station_id)
    blocked = preference == "block"
    available = directory_available and not blocked
    score = snr_hf * 1.4 + (100.0 - occupancy) * 0.4
    return {
        "id": station_id,
        "preference": preference,
        "blocked": blocked,
        "directory_available": directory_available,
        "url": url.rstrip("/"),
        "name": str(receiver.get("name") or parsed_url.hostname)[:160],
        "location": str(receiver.get("loc") or "Location not listed")[:160],
        "antenna": str(receiver.get("antenna") or "")[:160],
        "lat": lat,
        "lon": lon,
        "distance_km": round(distance, 1),
        "users": users,
        "users_max": users_max,
        "occupancy": round(occupancy, 1),
        "snr_hf": round(snr_hf, 1),
        "offline": offline,
        "flagged": flagged,
        "band_ok": band_ok,
        "available": available,
        "score": round(score, 2),
        "bands": bands if isinstance(bands, list) else None,
    }


def discover_receivers() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = fetch_directory()
    with CONFIG_LOCK:
        cfg = dict(config)
    found: list[dict[str, Any]] = []
    for raw in validate_directory(payload):
        parsed = parse_receiver(raw, cfg)
        if parsed:
            found.append(parsed)
    found.sort(key=lambda item: (not item["available"], -item["score"], item["distance_km"]))
    meta = {
        "directory_count": len(payload.get("receivers", [])),
        "found_count": len(found),
        "available_count": sum(1 for item in found if item["available"]),
        "blocked_count": sum(1 for item in found if item["blocked"]),
        "fetched_at": directory_fetched_at,
        "cache_error": directory_error,
    }
    return found, meta


def make_tune_url(receiver: dict[str, Any], cfg: dict[str, Any]) -> str:
    """Build a KiwiSDR browser URL using shared receiver settings."""
    frequency = f"{cfg['frequency_khz']:g}"
    tune = f"{frequency}{cfg['mode']}z{cfg['zoom']}"
    query = urllib.parse.urlencode({
        "f": tune,
        "pb": f"{cfg['passband_low']},{cfg['passband_high']}",
        "cmap": "1",
        "vol": str(cfg["volume"]),
        # An empty "ext=" suppresses KiwiSDR's nonessential first-visit readme panel.
        "ext": "",
        # KiwiSDR uses u= to prefill and submit its required visitor identity.
        "u": RADIOSTREAM_IDENT,
        # KiwiSDR's native URL shortcut hides its panel UI, including Readme and Control.
        "keys": "x",
    })
    return f"{receiver['url']}/?{query}"
