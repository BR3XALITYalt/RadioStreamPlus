#!/usr/bin/env python3
"""RadioStream+ receiver directory, geospatial filtering, and tune settings."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import ipaddress
import json
import math
import os
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
DATA_DIR = Path(os.environ.get("RADIOSTREAM_DATA_DIR") or APP_DIR).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
HOST = "127.0.0.1"
PORT = 5056
DIRECTORY_URL = "https://cdn.aethersdr.com/kiwi.json"
DIRECTORY_MAX_AGE = 30 * 60
DIRECTORY_MAX_BYTES = 32 * 1024 * 1024
RECEIVERBOOK_MAP_URL = "https://www.receiverbook.de/map?type=openwebrx"
RECEIVERBOOK_CACHE_MAX_AGE = 30 * 60
RECEIVERBOOK_MAX_BYTES = 12 * 1024 * 1024
OPENWEBRX_STATUS_TIMEOUT = 2.5
OPENWEBRX_STATUS_MAX_BYTES = 512 * 1024
OPENWEBRX_BAND_CACHE_MAX_AGE = 30 * 60
OPENWEBRX_BAND_PROBE_WORKERS = 16
HAMQSL_URL = "https://www.hamqsl.com/solarxml.php"
APP_USER_AGENT = "RadioStreamPlus/1.0 (local KiwiSDR browser-stream manager)"

RADIOSTREAM_IDENT = "rsplus-" + "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(4))
CONFIG_PATH = DATA_DIR / "radiostream.json"
DIRECTORY_CACHE_PATH = DATA_DIR / "kiwi_directory_cache.json"
STATION_PREFERENCES_PATH = DATA_DIR / "station_preferences.json"
RECEIVERBOOK_CACHE_PATH = DATA_DIR / "receiverbook_cache.json"
OPENWEBRX_CUSTOM_PATH = DATA_DIR / "openwebrx_custom.json"
RADIO_PRESETS_PATH = DATA_DIR / "radio_presets.json"
STATION_PREFERENCES_LOCK = threading.RLock()
OPENWEBRX_CUSTOM_LOCK = threading.RLock()
RADIO_PRESETS_LOCK = threading.RLock()
station_preferences: dict[str, str] = {}
RECEIVERBOOK_LOCK = threading.RLock()
receiverbook_data: list[dict[str, Any]] | None = None
receiverbook_fetched_monotonic = 0.0
receiverbook_fetched_at: str | None = None
receiverbook_error: str | None = None
openwebrx_custom_data: list[dict[str, Any]] = []
radio_presets: list[dict[str, Any]] = []


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
    "overlay_reload_notice": (
        "Every ${M} minutes, the stream will\n"
        "automatically reload the receiver.\n"
        "When that happens, it will go black\n"
        "for a short time, then the waterfall\n"
        "should start building up again."
    ),
    "overlay_black_notice": (
        "If the receiver window stays black, something crashed.\n"
        "This is unlikely but may happen. If so, please wait for\n"
        "the next reload."
    ),
    "directory_cache_minutes": 30,
    "openwebrx_receiverbook_enabled": True,
    "openwebrx_custom_enabled": True,
}

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


def is_password_prompt_page(page_text: str) -> bool:
    """Detect a visible password prompt without matching scripts or source comments."""
    visible_text = re.sub(
        r"(?is)<(script|style)\b[^>]*>.*?</\1\s*>",
        " ",
        page_text,
    )
    visible_text = re.sub(r"(?s)<!--.*?-->", " ", visible_text)
    visible_text = re.sub(r"<[^>]*>", " ", visible_text)
    normalized = " ".join(html.unescape(visible_text).casefold().split())
    return re.search(r"\benter\s+password\s*:", normalized) is not None


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
            if is_password_prompt_page(body):
                return remember(False, "Receiver displays an Enter Password prompt")
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
                previous_default_reload_notice = (
                    "Every 30 minutes, the stream will\n"
                    "automatically reload the receiver.\n"
                    "When that happens, it will go black\n"
                    "for a short time, then the waterfall\n"
                    "should start building up again."
                )
                needs_save = False
                if parsed.get("overlay_reload_notice") == previous_default_reload_notice:
                    parsed["overlay_reload_notice"] = DEFAULT_CONFIG["overlay_reload_notice"]
                    needs_save = True

                config = validate_config(parsed, allow_partial=True)
                new_config_keys = {
                    "overlay_reload_notice",
                    "overlay_black_notice",
                    "openwebrx_receiverbook_enabled",
                    "openwebrx_custom_enabled",
                }
                if not new_config_keys.issubset(parsed):
                    needs_save = True
                if needs_save:
                    save_config()
                return
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"[config] Could not load radiostream.json: {exc}", file=sys.stderr)
    config = dict(DEFAULT_CONFIG)
    save_config()


def validate_overlay_text(value: Any, name: str) -> str:
    """Validate multiline text rendered in the OBS SVG overlay."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(
        char for char in value
        if char in {"\n", "\t"} or ord(char) >= 32
    )
    if len(value) > 800:
        raise ValueError(f"{name} must be 800 characters or fewer")
    if len(value.split("\n")) > 8:
        raise ValueError(f"{name} must contain no more than 8 lines")
    return value


def validate_config(raw: dict[str, Any], allow_partial: bool = False) -> dict[str, Any]:
    base = dict(DEFAULT_CONFIG) if allow_partial else dict(config)
    base.update(raw)
    receiverbook_enabled = base.get("openwebrx_receiverbook_enabled", True)
    custom_enabled = base.get("openwebrx_custom_enabled", True)
    if not isinstance(receiverbook_enabled, bool):
        raise ValueError("Receiverbook source setting must be true or false")
    if not isinstance(custom_enabled, bool):
        raise ValueError("Custom OpenWebRX source setting must be true or false")
    result = {
        "center_lat": clamp_number(base["center_lat"], "Latitude", -90, 90),
        "center_lon": clamp_number(base["center_lon"], "Longitude", -180, 180),
        "radius_km": clamp_number(base["radius_km"], "Range", 1, 20000),
        "frequency_khz": clamp_number(base["frequency_khz"], "Frequency (kHz)", 0.001, 300000000),
        "mode": str(base["mode"]).lower(),
        "zoom": clamp_number(base["zoom"], "KiwiSDR zoom", 0, 14, integer=True),
        "volume": clamp_number(base["volume"], "Volume", 0, 200, integer=True),
        "passband_low": clamp_number(base["passband_low"], "Passband low", -12000, 12000, integer=True),
        "passband_high": clamp_number(base["passband_high"], "Passband high", -12000, 12000, integer=True),
        "rotation_minutes": clamp_number(base["rotation_minutes"], "Rotation interval", 3, 60),
        "overlay_reload_notice": validate_overlay_text(
            base["overlay_reload_notice"], "Overlay reload notice"
        ),
        "overlay_black_notice": validate_overlay_text(
            base["overlay_black_notice"], "Overlay black-screen notice"
        ),
        "directory_cache_minutes": 30,
        "openwebrx_receiverbook_enabled": receiverbook_enabled,
        "openwebrx_custom_enabled": custom_enabled,
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


def normalize_radio_preset(item: Any) -> dict[str, Any]:
    """Validate and normalize a saved frequency/mode preset."""
    if not isinstance(item, dict):
        raise ValueError("Radio preset must be an object")
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("Enter a name for this preset")
    if len(name) > 80:
        raise ValueError("Preset names must be 80 characters or fewer")

    frequency_khz = clamp_number(
        item.get("frequency_khz"),
        "Preset frequency (kHz)",
        0.001,
        300000000,
    )
    mode = str(item.get("mode") or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError("Preset mode must be AM, LSB, USB, CW, or NBFM")

    passband_low = clamp_number(
        item.get("passband_low"), "Preset passband low", -12000, 12000, integer=True
    )
    passband_high = clamp_number(
        item.get("passband_high"), "Preset passband high", -12000, 12000, integer=True
    )
    if passband_low >= passband_high:
        raise ValueError("Preset passband low must be smaller than passband high")

    preset_id = str(item.get("id") or ("preset-" + secrets.token_hex(8)))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", preset_id):
        raise ValueError("Preset ID is invalid")
    return {
        "id": preset_id,
        "name": name,
        "frequency_khz": frequency_khz,
        "mode": mode,
        "passband_low": passband_low,
        "passband_high": passband_high,
    }


def validate_radio_presets(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Radio preset file has an unsupported schema")
    entries = payload.get("presets")
    if not isinstance(entries, list) or len(entries) > 200:
        raise ValueError("Radio preset file has an invalid preset list")
    cleaned: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for entry in entries:
        preset = normalize_radio_preset(entry)
        name_key = preset["name"].casefold()
        if preset["id"] in seen_ids or name_key in seen_names:
            continue
        seen_ids.add(preset["id"])
        seen_names.add(name_key)
        cleaned.append(preset)
    return cleaned


def _write_radio_presets(presets: list[dict[str, Any]]) -> None:
    payload = json.dumps({"schema": 1, "presets": presets}, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary = RADIO_PRESETS_PATH.with_suffix(".json.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(RADIO_PRESETS_PATH)
    except OSError as exc:
        raise RuntimeError(f"Could not save radio presets: {exc}") from exc


def load_radio_presets() -> None:
    global radio_presets
    try:
        payload = json.loads(RADIO_PRESETS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        with RADIO_PRESETS_LOCK:
            radio_presets = []
        return
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[presets] Could not load radio presets: {exc}", file=sys.stderr)
        return
    try:
        cleaned = validate_radio_presets(payload)
    except ValueError as exc:
        print(f"[presets] Ignoring invalid preset file: {exc}", file=sys.stderr)
        return
    with RADIO_PRESETS_LOCK:
        radio_presets = cleaned


def get_radio_presets() -> list[dict[str, Any]]:
    with RADIO_PRESETS_LOCK:
        return [dict(preset) for preset in radio_presets]


def save_radio_preset(raw: Any) -> list[dict[str, Any]]:
    global radio_presets
    preset = normalize_radio_preset(raw)
    with RADIO_PRESETS_LOCK:
        updated = [dict(item) for item in radio_presets]
        existing_index = next(
            (
                index for index, item in enumerate(updated)
                if item["name"].casefold() == preset["name"].casefold()
            ),
            None,
        )
        if existing_index is not None:
            preset["id"] = updated[existing_index]["id"]
            updated[existing_index] = preset
        else:
            if len(updated) >= 200:
                raise ValueError("The radio preset list is full (200 presets)")
            updated.append(preset)
        _write_radio_presets(updated)
        radio_presets = updated
        return [dict(item) for item in updated]


def remove_radio_preset(preset_id: Any) -> list[dict[str, Any]]:
    global radio_presets
    wanted = str(preset_id or "").strip()
    if not wanted:
        raise ValueError("A radio preset ID is required")
    with RADIO_PRESETS_LOCK:
        updated = [dict(item) for item in radio_presets if item["id"] != wanted]
        if len(updated) == len(radio_presets):
            raise ValueError("That radio preset was not found")
        _write_radio_presets(updated)
        radio_presets = updated
        return [dict(item) for item in updated]


def load_disk_directory() -> None:
    global directory_data, directory_fetched_at, directory_fetched_monotonic
    if not DIRECTORY_CACHE_PATH.exists():
        return
    try:
        payload = json.loads(DIRECTORY_CACHE_PATH.read_text(encoding="utf-8"))
        validate_directory(payload)
        directory_data = payload
        directory_fetched_at = payload.get("fetched_at")
        
        
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
        if directory_data is not None and not force and age < DIRECTORY_MAX_AGE:
            return directory_data
        
        
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



def normalize_receiverbook_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urllib.parse.urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.hostname.casefold() == "localhost" or parsed.hostname.casefold().endswith((".localhost", ".local")):
            return None
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        parsed.port
    except ValueError:
        return None
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def validate_receiverbook_cache(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Receiverbook cache has an unsupported schema")
    entries = payload.get("receivers")
    if not isinstance(entries, list) or len(entries) > 20000:
        raise ValueError("Receiverbook cache has an invalid receiver list")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        url = normalize_receiverbook_url(item.get("url"))
        if not url or url in seen:
            continue
        try:
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (abs(lat) < 1e-9 and abs(lon) < 1e-9):
            continue
        seen.add(url)
        cleaned_item: dict[str, Any] = {
            "id": "receiverbook:" + url,
            "name": str(item.get("name") or urllib.parse.urlsplit(url).hostname)[:160],
            "station": str(item.get("station") or "")[:160],
            "version": str(item.get("version") or "")[:80],
            "type": "openwebrx",
            "url": url,
            "lat": lat,
            "lon": lon,
        }
        raw_ranges = item.get("frequency_ranges")
        checked_at = item.get("frequency_checked_at")
        if isinstance(raw_ranges, list) and len(raw_ranges) <= 4096:
            frequency_ranges: list[dict[str, float]] = []
            for band in raw_ranges:
                if not isinstance(band, dict):
                    continue
                try:
                    low_hz = float(band.get("low_hz"))
                    high_hz = float(band.get("high_hz"))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(low_hz) and math.isfinite(high_hz) and 0 <= low_hz < high_hz:
                    frequency_ranges.append({"low_hz": low_hz, "high_hz": high_hz})
            try:
                checked_at = float(checked_at)
            except (TypeError, ValueError):
                checked_at = None
            if checked_at is not None and math.isfinite(checked_at) and checked_at > 0:
                cleaned_item["frequency_ranges"] = frequency_ranges
                cleaned_item["frequency_checked_at"] = checked_at
        cleaned.append(cleaned_item)
    return cleaned


def normalize_custom_openwebrx_instance(item: Any) -> dict[str, Any]:
    """Validate a user-managed OpenWebRX entry and normalize its public URL/location."""
    if not isinstance(item, dict):
        raise ValueError("OpenWebRX instance must be an object")
    url = normalize_receiverbook_url(item.get("url"))
    if not url:
        raise ValueError("Enter a valid public HTTP or HTTPS OpenWebRX URL")
    try:
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
    except (TypeError, ValueError):
        raise ValueError("Latitude and longitude must be numbers")
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise ValueError("Latitude and longitude must be finite numbers")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Latitude must be between -90 and 90 and longitude between -180 and 180")
    if abs(lat) < 1e-9 and abs(lon) < 1e-9:
        raise ValueError("The map location cannot be 0, 0")
    hostname = urllib.parse.urlsplit(url).hostname or "OpenWebRX"
    name = str(item.get("name") or hostname).strip()[:160] or hostname
    cleaned: dict[str, Any] = {
        "id": "custom:" + url,
        "name": name,
        "station": "",
        "version": str(item.get("version") or "")[:80],
        "type": "openwebrx",
        "url": url,
        "lat": lat,
        "lon": lon,
    }
    raw_ranges = item.get("frequency_ranges")
    checked_at = item.get("frequency_checked_at")
    if isinstance(raw_ranges, list) and len(raw_ranges) <= 4096:
        ranges: list[dict[str, float]] = []
        for band in raw_ranges:
            if not isinstance(band, dict):
                continue
            try:
                low_hz = float(band.get("low_hz"))
                high_hz = float(band.get("high_hz"))
            except (TypeError, ValueError):
                continue
            if math.isfinite(low_hz) and math.isfinite(high_hz) and 0 <= low_hz < high_hz:
                ranges.append({"low_hz": low_hz, "high_hz": high_hz})
        try:
            checked_at = float(checked_at)
        except (TypeError, ValueError):
            checked_at = None
        if checked_at is not None and math.isfinite(checked_at) and checked_at > 0:
            cleaned["frequency_ranges"] = ranges
            cleaned["frequency_checked_at"] = checked_at
    return cleaned


def validate_custom_openwebrx(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema") != 1:
        raise ValueError("Custom OpenWebRX file has an unsupported schema")
    entries = payload.get("instances")
    if not isinstance(entries, list) or len(entries) > 500:
        raise ValueError("Custom OpenWebRX file has an invalid instance list")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        try:
            item = normalize_custom_openwebrx_instance(entry)
        except ValueError:
            continue
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        cleaned.append(item)
    return cleaned


def _write_custom_openwebrx(instances: list[dict[str, Any]]) -> None:
    payload = json.dumps({"schema": 1, "instances": instances}, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary = OPENWEBRX_CUSTOM_PATH.with_suffix(".json.tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(OPENWEBRX_CUSTOM_PATH)
    except OSError as exc:
        raise RuntimeError(f"Could not save custom OpenWebRX instances: {exc}") from exc


def load_custom_openwebrx_instances() -> None:
    global openwebrx_custom_data
    try:
        payload = json.loads(OPENWEBRX_CUSTOM_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        with OPENWEBRX_CUSTOM_LOCK:
            openwebrx_custom_data = []
        return
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[openwebrx] Could not load custom instances: {exc}", file=sys.stderr)
        return
    try:
        cleaned = validate_custom_openwebrx(payload)
    except ValueError as exc:
        print(f"[openwebrx] Ignoring invalid custom instance file: {exc}", file=sys.stderr)
        return
    with OPENWEBRX_CUSTOM_LOCK:
        openwebrx_custom_data = cleaned


def get_custom_openwebrx_instances() -> list[dict[str, Any]]:
    with OPENWEBRX_CUSTOM_LOCK:
        return [dict(item) for item in openwebrx_custom_data]


def save_custom_openwebrx_frequency_cache(checked_instances: list[dict[str, Any]] | None = None) -> None:
    with OPENWEBRX_CUSTOM_LOCK:
        if checked_instances:
            checked_by_url = {
                item.get("url"): item
                for item in checked_instances
                if isinstance(item, dict) and item.get("url")
            }
            for stored in openwebrx_custom_data:
                checked = checked_by_url.get(stored.get("url"))
                if checked and "frequency_checked_at" in checked:
                    stored["frequency_ranges"] = checked.get("frequency_ranges", [])
                    stored["frequency_checked_at"] = checked["frequency_checked_at"]
        try:
            _write_custom_openwebrx(openwebrx_custom_data)
        except RuntimeError as exc:
            print(f"[openwebrx] {exc}", file=sys.stderr)


def add_custom_openwebrx_instance(raw: Any) -> list[dict[str, Any]]:
    global openwebrx_custom_data
    item = normalize_custom_openwebrx_instance(raw)
    with OPENWEBRX_CUSTOM_LOCK:
        updated = [dict(entry) for entry in openwebrx_custom_data]
        existing_index = next(
            (index for index, entry in enumerate(updated) if entry["url"] == item["url"]),
            None,
        )
        if existing_index is not None:
            previous = updated[existing_index]
            if "frequency_checked_at" in previous:
                item["frequency_ranges"] = previous.get("frequency_ranges", [])
                item["frequency_checked_at"] = previous["frequency_checked_at"]
            updated[existing_index] = item
        else:
            if len(updated) >= 500:
                raise ValueError("The custom OpenWebRX list is full (500 instances)")
            updated.append(item)
        _write_custom_openwebrx(updated)
        openwebrx_custom_data = updated
        return [dict(entry) for entry in updated]


def remove_custom_openwebrx_instance(instance_id: Any) -> list[dict[str, Any]]:
    global openwebrx_custom_data
    wanted = str(instance_id or "").strip()
    if not wanted:
        raise ValueError("A custom OpenWebRX instance ID is required")
    with OPENWEBRX_CUSTOM_LOCK:
        updated = [dict(entry) for entry in openwebrx_custom_data if entry["id"] != wanted]
        if len(updated) == len(openwebrx_custom_data):
            raise ValueError("That custom OpenWebRX instance was not found")
        _write_custom_openwebrx(updated)
        openwebrx_custom_data = updated
        return [dict(entry) for entry in updated]


def parse_receiverbook_map(body: str) -> list[dict[str, Any]]:
    match = re.search(r"\b(?:var|let|const)\s+receivers\s*=\s*", body)
    if not match:
        raise ValueError("Receiverbook map page did not contain its receiver data")
    start = match.end()
    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(body[start:].lstrip())
    if not isinstance(payload, list) or len(payload) > 20000:
        raise ValueError("Receiverbook map page contained an invalid receiver list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in payload:
        if not isinstance(group, dict):
            continue
        location = group.get("location")
        coordinates = location.get("coordinates") if isinstance(location, dict) else None
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            continue
        try:
            lon, lat = float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (abs(lat) < 1e-9 and abs(lon) < 1e-9):
            continue
        station = str(group.get("label") or "")[:160]
        receivers = group.get("receivers")
        if not isinstance(receivers, list):
            receivers = [group] if group.get("url") else []
        for receiver in receivers:
            if not isinstance(receiver, dict) or str(receiver.get("type") or "openwebrx").casefold() != "openwebrx":
                continue
            url = normalize_receiverbook_url(receiver.get("url"))
            if not url or url in seen:
                continue
            seen.add(url)
            name = str(receiver.get("label") or station or urllib.parse.urlsplit(url).hostname)[:160]
            normalized.append({
                "id": "receiverbook:" + url,
                "name": name,
                "station": station,
                "version": str(receiver.get("version") or "")[:80],
                "type": "openwebrx",
                "url": url,
                "lat": lat,
                "lon": lon,
            })
    return validate_receiverbook_cache({"schema": 1, "receivers": normalized})


def load_disk_receiverbook_directory() -> None:
    global receiverbook_data, receiverbook_fetched_at, receiverbook_fetched_monotonic
    if not RECEIVERBOOK_CACHE_PATH.exists():
        return
    try:
        payload = json.loads(RECEIVERBOOK_CACHE_PATH.read_text(encoding="utf-8"))
        receiverbook_data = validate_receiverbook_cache(payload)
        receiverbook_fetched_at = payload.get("fetched_at")
        receiverbook_fetched_monotonic = 0.0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"[receiverbook] Ignoring invalid disk cache: {exc}", file=sys.stderr)


def save_receiverbook_cache() -> None:
    """Persist Receiverbook records, including recently checked frequency ranges."""
    with RECEIVERBOOK_LOCK:
        payload = {
            "schema": 1,
            "fetched_at": receiverbook_fetched_at,
            "receivers": receiverbook_data or [],
        }
        try:
            temporary = RECEIVERBOOK_CACHE_PATH.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(RECEIVERBOOK_CACHE_PATH)
        except OSError as exc:
            print(f"[receiverbook] Could not persist cache: {exc}", file=sys.stderr)


def fetch_receiverbook_directory(force: bool = False) -> list[dict[str, Any]]:
    global receiverbook_data, receiverbook_fetched_monotonic, receiverbook_fetched_at, receiverbook_error
    with RECEIVERBOOK_LOCK:
        age = time.monotonic() - receiverbook_fetched_monotonic
        if receiverbook_data is not None and not force and age < RECEIVERBOOK_CACHE_MAX_AGE:
            return receiverbook_data
        request_obj = urllib.request.Request(
            RECEIVERBOOK_MAP_URL,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; RadioStreamPlus/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=15) as response:
                body = response.read(RECEIVERBOOK_MAX_BYTES + 1)
            if len(body) > RECEIVERBOOK_MAX_BYTES:
                raise ValueError("Receiverbook map page exceeded the 12 MB safety limit")
            records = parse_receiverbook_map(body.decode("utf-8"))
            previous_by_url = {
                item.get("url"): item
                for item in (receiverbook_data or [])
                if isinstance(item, dict) and item.get("url")
            }
            for record in records:
                previous = previous_by_url.get(record["url"])
                if previous and "frequency_checked_at" in previous:
                    record["frequency_ranges"] = previous.get("frequency_ranges", [])
                    record["frequency_checked_at"] = previous["frequency_checked_at"]
            fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            receiverbook_data = records
            receiverbook_fetched_at = fetched_at
            receiverbook_fetched_monotonic = time.monotonic()
            receiverbook_error = None
            save_receiverbook_cache()
            return records
        except (OSError, urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            receiverbook_error = str(exc)
            if receiverbook_data is not None:
                print(f"[receiverbook] Refresh failed; using cached data: {exc}", file=sys.stderr)
                receiverbook_fetched_monotonic = time.monotonic() - (RECEIVERBOOK_CACHE_MAX_AGE - 300)
                return receiverbook_data
            raise RuntimeError(f"Could not download the Receiverbook OpenWebRX directory: {exc}") from exc


def _append_frequency_range(
    ranges: list[dict[str, float]],
    low_hz: Any,
    high_hz: Any,
) -> None:
    try:
        low = float(low_hz)
        high = float(high_hz)
    except (TypeError, ValueError):
        return
    if math.isfinite(low) and math.isfinite(high) and 0 <= low < high:
        ranges.append({"low_hz": low, "high_hz": high})


def parse_openwebrx_plus_frequency_ranges(payload: Any) -> list[dict[str, float]]:
    """Read profile frequency coverage from an OpenWebRX+ status.json response."""
    if not isinstance(payload, dict) or not isinstance(payload.get("sdrs"), list):
        return []
    ranges: list[dict[str, float]] = []
    for sdr in payload["sdrs"]:
        if not isinstance(sdr, dict) or not isinstance(sdr.get("profiles"), list):
            continue
        for profile in sdr["profiles"]:
            if not isinstance(profile, dict):
                continue
            center = profile.get("center_freq")
            sample_rate = profile.get("sample_rate", profile.get("samp_rate"))
            try:
                center_hz = float(center)
                width_hz = float(sample_rate)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(center_hz) or not math.isfinite(width_hz) or width_hz <= 0:
                continue
            _append_frequency_range(ranges, center_hz - width_hz / 2, center_hz + width_hz / 2)
    return ranges


def parse_openwebrx_classic_frequency_ranges(status_text: str) -> list[dict[str, float]]:
    """Read the advertised bands field from a classic OpenWebRX /status response."""
    fields: dict[str, str] = {}
    for line in status_text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key.strip().casefold()] = value.strip()
    match = re.fullmatch(r"([0-9]+)-([0-9]+)", fields.get("bands", ""))
    if not match:
        return []
    ranges: list[dict[str, float]] = []
    _append_frequency_range(ranges, match.group(1), match.group(2))
    return ranges


def _fetch_openwebrx_status(receiver_url: str, endpoint: str, accept: str) -> bytes:
    parsed = urllib.parse.urlsplit(receiver_url)
    if not parsed.hostname:
        return b""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not _public_hostname(parsed.hostname, port):
        return b""
    path = (parsed.path.rstrip("/") + "/" + endpoint.lstrip("/")) or ("/" + endpoint.lstrip("/"))
    status_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    request_obj = urllib.request.Request(
        status_url,
        headers={"User-Agent": APP_USER_AGENT, "Accept": accept},
    )
    opener = urllib.request.build_opener(_PublicOnlyRedirectHandler())
    with opener.open(request_obj, timeout=OPENWEBRX_STATUS_TIMEOUT) as response:
        body = response.read(OPENWEBRX_STATUS_MAX_BYTES + 1)
    if len(body) > OPENWEBRX_STATUS_MAX_BYTES:
        raise ValueError("OpenWebRX status response exceeded the size limit")
    return body


def fetch_openwebrx_frequency_ranges(receiver: dict[str, Any]) -> list[dict[str, float]]:
    """Fetch and cache the receiver's published tuning ranges."""
    checked_at = receiver.get("frequency_checked_at")
    try:
        checked_at = float(checked_at)
    except (TypeError, ValueError):
        checked_at = 0.0
    if (
        checked_at > 0
        and math.isfinite(checked_at)
        and time.time() - checked_at < OPENWEBRX_BAND_CACHE_MAX_AGE
        and isinstance(receiver.get("frequency_ranges"), list)
    ):
        return receiver["frequency_ranges"]

    ranges: list[dict[str, float]] = []
    base_url = normalize_receiverbook_url(receiver.get("url"))
    if base_url:
        try:
            body = _fetch_openwebrx_status(base_url, "status.json", "application/json")
            if body:
                ranges = parse_openwebrx_plus_frequency_ranges(json.loads(body.decode("utf-8")))
        except (OSError, urllib.error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            ranges = []

        if not ranges:
            try:
                body = _fetch_openwebrx_status(base_url, "status", "text/plain")
                if body:
                    ranges = parse_openwebrx_classic_frequency_ranges(body.decode("utf-8", "replace"))
            except (OSError, urllib.error.URLError, TimeoutError, UnicodeDecodeError, ValueError):
                ranges = []

    receiver["frequency_ranges"] = ranges
    receiver["frequency_checked_at"] = time.time()
    return ranges


def make_openwebrx_url(receiver: dict[str, Any], cfg: dict[str, Any]) -> str:
    base_url = normalize_receiverbook_url(receiver.get("url"))
    if not base_url:
        raise ValueError("OpenWebRX receiver URL is invalid")
    parsed = urllib.parse.urlsplit(base_url)
    frequency_hz = round(float(cfg["frequency_khz"]) * 1000)
    mode = {"nbfm": "nfm"}.get(str(cfg["mode"]).lower(), str(cfg["mode"]).lower())
    fragment = f"freq={frequency_hz},mod={mode}"
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, fragment)
    )


def discover_openwebrx(force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with CONFIG_LOCK:
        cfg = dict(config)

    receiverbook_enabled = cfg.get("openwebrx_receiverbook_enabled", True)
    if receiverbook_enabled:
        try:
            receiverbook_records = fetch_receiverbook_directory(force=force)
        except RuntimeError as exc:
            receiverbook_records = receiverbook_data or []
            error = receiverbook_error or str(exc)
        else:
            error = receiverbook_error
    else:
        receiverbook_records = []
        error = None

    stored_custom_records = get_custom_openwebrx_instances()
    custom_enabled = cfg.get("openwebrx_custom_enabled", True)
    custom_records = stored_custom_records if custom_enabled else []
    custom_urls = {item["url"] for item in custom_records}
    records: list[tuple[dict[str, Any], str]] = [
        (item, "Receiverbook")
        for item in receiverbook_records
        if item.get("url") not in custom_urls
    ]
    records.extend((item, "Custom") for item in custom_records)

    candidates: list[tuple[dict[str, Any], float, str]] = []
    for item, source in records:
        distance = haversine_km(cfg["center_lat"], cfg["center_lon"], item["lat"], item["lon"])
        if distance <= cfg["radius_km"]:
            candidates.append((item, distance, source))

    if candidates:
        with ThreadPoolExecutor(max_workers=OPENWEBRX_BAND_PROBE_WORKERS) as executor:
            futures = [
                executor.submit(fetch_openwebrx_frequency_ranges, item)
                for item, _distance, _source in candidates
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    print(f"[openwebrx] Could not read receiver frequency range: {exc}", file=sys.stderr)

    frequency_hz = round(float(cfg["frequency_khz"]) * 1000)
    found: list[dict[str, Any]] = []
    for item, distance, source in candidates:
        ranges = item.get("frequency_ranges") or []
        frequency_supported = any(
            band["low_hz"] <= frequency_hz <= band["high_hz"]
            for band in ranges
        )
        if not frequency_supported:
            continue
        found.append({
            **item,
            "distance_km": round(distance, 1),
            "source": source,
            "listed_online": source == "Receiverbook",
            "frequency_supported": True,
            "tune_url": make_openwebrx_url(item, cfg),
        })

    if any(source == "Receiverbook" for _item, _distance, source in candidates):
        save_receiverbook_cache()
    if any(source == "Custom" for _item, _distance, source in candidates):
        save_custom_openwebrx_frequency_cache([item for item, _distance, source in candidates if source == "Custom"])

    found.sort(key=lambda item: (item["distance_km"], item["name"].casefold()))
    meta = {
        "directory_count": len(receiverbook_records) + len(custom_records),
        "receiverbook_count": len(receiverbook_records),
        "receiverbook_enabled": receiverbook_enabled,
        "custom_count": len(custom_records),
        "custom_enabled": custom_enabled,
        "nearby_count": len(candidates),
        "found_count": len(found),
        "frequency_hz": frequency_hz,
        "fetched_at": receiverbook_fetched_at if receiverbook_enabled else None,
        "cache_error": error,
        "directory_url": RECEIVERBOOK_MAP_URL if receiverbook_enabled else None,
    }
    return found, meta


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
        return None  

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
        
        "ext": "",
        
        "u": RADIOSTREAM_IDENT,
        
        "keys": "x",
    })
    return f"{receiver['url']}/?{query}"
