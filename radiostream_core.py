#!/usr/bin/env python3
"""RadioStream+ receiver directory, geospatial filtering, and tune settings."""
from __future__ import annotations

import json
import math
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
CONFIG_PATH = APP_DIR / "radiostream.json"
DIRECTORY_CACHE_PATH = APP_DIR / "kiwi_directory_cache.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "center_lat": 20.0,
    "center_lon": 0.0,
    "radius_km": 500,
    "frequency_khz": 4625.0,
    "mode": "usb",
    "zoom": 11,
    "volume": 180,
    "passband_low": 50,
    "passband_high": 4000,
    "rotation_minutes": 14,
    "directory_cache_minutes": 30,
}
VALID_MODES = {"am", "lsb", "usb", "cw", "nbfm"}
CONFIG_LOCK = threading.RLock()
DIRECTORY_LOCK = threading.RLock()

config: dict[str, Any] = dict(DEFAULT_CONFIG)
directory_data: dict[str, Any] | None = None
directory_fetched_monotonic = 0.0
directory_fetched_at: str | None = None
directory_error: str | None = None


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

    offline = receiver.get("offline") in (True, "yes", "true", 1)
    flagged = receiver.get("flagged") in (True, "yes", "true", 1)
    full = users_max > 0 and users >= users_max
    available = not offline and not flagged and not full and band_ok
    score = snr_hf * 1.4 + (100.0 - occupancy) * 0.4
    return {
        "id": receiver_id(receiver),
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
    })
    return f"{receiver['url']}/?{query}"
