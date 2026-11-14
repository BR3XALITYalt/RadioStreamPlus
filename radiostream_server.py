#!/usr/bin/env python3
"""HTTP server and automatic receiver rotation for RadioStream+."""
from __future__ import annotations

import json
import mimetypes
import sys
import ssl
import threading
import xml.etree.ElementTree as ET
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import radiostream_core as core

APP_DIR = core.APP_DIR
HOST = core.HOST
PORT = core.PORT
STATE_LOCK = threading.RLock()
current_receiver: dict[str, Any] | None = None
current_started_at = 0.0
last_receiver_ids: list[str] = []
last_receiver_error: str | None = None
SOLAR_CACHE_PATH = APP_DIR / "solar_xml_cache.xml"
SOLAR_CACHE_MAX_AGE = 14 * 24 * 60 * 60

def create_solar_ssl_context() -> ssl.SSLContext:
    """Use the system trust store, supplemented by certifi when installed."""
    context = ssl.create_default_context()
    try:
        import certifi
    except ImportError:
        return context

    try:
        context.load_verify_locations(cafile=certifi.where())
    except (OSError, ssl.SSLError) as exc:
        print(f"[solar] Could not load certifi CA bundle: {exc}", file=sys.stderr)
    return context


SOLAR_SSL_CONTEXT = create_solar_ssl_context()

MAINTENANCE_LOCK = threading.RLock()
MAINTENANCE_STATE: dict[str, Any] = {
    "active": False,
    "message": "An update is being prepared.",
    "started_at": None,
}


def set_maintenance(active: bool, message: str = "RadioStream+ is updating its files.") -> None:
    """Enable or disable the maintenance gate used by the launcher updater."""
    with MAINTENANCE_LOCK:
        MAINTENANCE_STATE["active"] = bool(active)
        MAINTENANCE_STATE["message"] = str(message)
        MAINTENANCE_STATE["started_at"] = time.time() if active else None


def get_maintenance_state() -> dict[str, Any]:
    with MAINTENANCE_LOCK:
        return dict(MAINTENANCE_STATE)


def pick_next_receiver(force_next: bool = False) -> dict[str, Any] | None:
    global current_receiver, current_started_at, last_receiver_ids, last_receiver_error
    try:
        receivers, _ = core.discover_receivers()
    except RuntimeError as exc:
        core.directory_error = str(exc)
        with STATE_LOCK:
            current_receiver = None
            current_started_at = 0.0
            last_receiver_error = str(exc)
        return None

    candidates = [item for item in receivers if item["available"]]
    if not candidates:
        with STATE_LOCK:
            current_receiver = None
            current_started_at = 0.0
            last_receiver_error = "No receivers in range are marked available by the public directory."
        return None

    with STATE_LOCK:
        current_id = current_receiver["id"] if current_receiver else None
        if current_id and not force_next:
            current = next((item for item in candidates if item["id"] == current_id), None)
            ordered = ([current] if current else []) + [
                item for item in candidates if item["id"] != current_id
            ]
        else:
            recent = set(last_receiver_ids[-max(1, len(candidates) - 1):])
            ordered = [item for item in candidates if item["id"] not in recent]
            if not ordered:
                ordered = list(candidates)
            if current_id and len(ordered) > 1:
                ordered = [item for item in ordered if item["id"] != current_id] or ordered

    failures: list[str] = []
    chosen = None
    for item in ordered[:core.MAX_RECEIVER_PROBES]:
        online, reason = core.check_receiver_online(item)
        if online:
            chosen = item
            break
        failures.append(f"{item['name']}: {reason}")

    with STATE_LOCK:
        if chosen is None:
            current_receiver = None
            current_started_at = 0.0
            checked = min(len(ordered), core.MAX_RECEIVER_PROBES)
            last_receiver_error = (
                f"No reachable receiver was found (checked {checked} of {len(ordered)} candidates). "
                + "; ".join(failures[:3])
            )
            return None

        current_receiver = chosen
        current_started_at = time.monotonic()
        last_receiver_ids.append(chosen["id"])
        last_receiver_ids = last_receiver_ids[-100:]
        last_receiver_error = None
        return dict(chosen)


def get_state() -> dict[str, Any]:
    global current_receiver, current_started_at, last_receiver_error
    with core.CONFIG_LOCK:
        cfg = dict(core.config)
    with STATE_LOCK:
        current = dict(current_receiver) if current_receiver else None
        started = current_started_at
        receiver_error = last_receiver_error

    if current:
        online, reason = core.check_receiver_online(current)
        if not online:
            with STATE_LOCK:
                last_receiver_error = f"{current['name']}: {reason}"
            pick_next_receiver(force_next=True)
            with STATE_LOCK:
                current = dict(current_receiver) if current_receiver else None
                started = current_started_at
                receiver_error = last_receiver_error

    rotation_seconds = float(cfg["rotation_minutes"]) * 60
    elapsed = time.monotonic() - started if started else 0.0
    should_start = current is None
    should_rotate = current is not None and elapsed >= rotation_seconds

    if should_start or should_rotate:
        pick_next_receiver(force_next=should_rotate)
        with STATE_LOCK:
            current = dict(current_receiver) if current_receiver else None
            started = current_started_at
            receiver_error = last_receiver_error
        elapsed = time.monotonic() - started if started else 0.0

    if current:
        current["tune_url"] = core.make_tune_url(current, cfg)

    remaining = max(0, int(rotation_seconds - elapsed)) if current else None
    return {
        "current": current,
        "remaining_seconds": remaining,
        "rotation_minutes": cfg["rotation_minutes"],
        "config": cfg,
        "directory_error": core.directory_error,
        "receiver_error": receiver_error,
    }


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 64 * 1024:
        raise ValueError("Request body is empty or too large")
    parsed = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Request must be a JSON object")
    return parsed


class RadioStreamHandler(BaseHTTPRequestHandler):
    server_version = "RadioStreamPlus/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def send_bytes(self, body: bytes, content_type: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, value: Any, status: int = 200) -> None:
        self.send_bytes(
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def send_file(self, filename: str, content_type: str | None = None) -> None:
        path = (APP_DIR / filename).resolve()
        if path.parent != APP_DIR.resolve() or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        guessed = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        charset = "; charset=utf-8" if guessed.startswith(
            ("text/", "application/javascript", "image/svg+xml")
        ) else ""
        self.send_bytes(data, guessed + charset)

    def ensure_local_request(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0].strip("[]").lower()
        origin = self.headers.get("Origin")
        if host not in {"127.0.0.1", "localhost"}:
            self.send_error(403, "RadioStream+ only accepts local requests")
            return False
        if origin:
            parsed = urllib.parse.urlsplit(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                self.send_error(403, "Cross-origin requests are not allowed")
                return False
        return True

    def redirect_to_maintenance(self) -> None:
        target = "/m.html?" + urllib.parse.urlencode({"return": self.path})
        self.send_response(302)
        self.send_header("Location", target)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not self.ensure_local_request():
            return
        route = urllib.parse.urlsplit(self.path).path

        # This endpoint and the maintenance document stay available while all
        # normal application routes are locked.
        if route == "/api/maintenance":
            self.send_json(get_maintenance_state())
            return
        if route == "/m.html":
            self.send_file("m.html", "text/html")
            return

        maintenance = get_maintenance_state()
        if maintenance["active"]:
            if route in {"/", "/manage", "/overlay", "/sdr"}:
                self.redirect_to_maintenance()
            elif route.startswith("/api/"):
                self.send_json({
                    "maintenance": True,
                    "message": maintenance["message"],
                }, 503)
            else:
                self.send_bytes(
                    maintenance["message"].encode("utf-8"),
                    "text/plain; charset=utf-8",
                    503,
                    {"Retry-After": "3"},
                )
            return
        if route == "/maintenance.js":
            self.send_file("maintenance.js", "application/javascript")
            return
        if route in {"/", "/manage"}:
            self.send_file("manage.html", "text/html")
        elif route == "/overlay":
            self.send_file("index.html", "text/html")
        elif route == "/sdr":
            self.send_file("sdr.html", "text/html")
        elif route == "/app.js":
            self.send_file("app.js", "application/javascript")
        elif route == "/favicon.ico":
            self.send_bytes(
                b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="5" fill="#20262b"/><path d="M7 12h18M7 17h13M7 22h8" stroke="#8cc7ff" stroke-width="2.4" stroke-linecap="round"/><circle cx="24" cy="22" r="3" fill="#72cf9a"/></svg>',
                "image/svg+xml",
            )
        elif route == "/api/state":
            try:
                self.send_json(get_state())
            except Exception as exc:
                self.send_json({"error": str(exc)}, 503)
        elif route == "/api/discover":
            try:
                receivers, meta = core.discover_receivers()
                with core.CONFIG_LOCK:
                    cfg = dict(core.config)
                self.send_json({"receivers": receivers, "meta": meta, "config": cfg})
            except Exception as exc:
                self.send_json({"error": str(exc)}, 503)
        elif route == "/api/solar":
            error_text = "No solar feed response was received"
            body = None
            for solar_url in (
                "https://www.hamqsl.com/solarxml.php",
                "https://hamqsl.com/solarxml.php",
            ):
                try:
                    request_obj = urllib.request.Request(
                        solar_url,
                        headers={
                            "User-Agent": "Mozilla/5.0 (compatible; RadioStreamPlus/1.0)",
                            "Accept": "application/xml,text/xml,*/*;q=0.8",
                        },
                    )
                    with urllib.request.urlopen(request_obj, timeout=12, context=SOLAR_SSL_CONTEXT) as response:
                        candidate = response.read(1024 * 1024 + 1)
                    if len(candidate) > 1024 * 1024:
                        raise ValueError("HamQSL response exceeded 1 MB")
                    root = ET.fromstring(candidate)
                    if root.tag.casefold() != "solar":
                        raise ValueError("HamQSL returned an unexpected XML document")
                    body = candidate
                    break
                except (OSError, urllib.error.URLError, TimeoutError, ValueError, ET.ParseError) as exc:
                    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
                    if isinstance(reason, ssl.SSLCertVerificationError):
                        error_text = (
                            f"{solar_url}: TLS certificate verification failed: {reason}. "
                            "Update the system/Python CA certificates, check the system clock, "
                            "or install/update certifi with 'py -m pip install --upgrade certifi'. "
                            "HamQSL may also be missing an intermediate certificate. "
                            "RadioStream+ does not disable HTTPS verification."
                        )
                    else:
                        error_text = f"{solar_url}: {exc}"
                    print(f"[solar] {error_text}", file=sys.stderr)

            if body is not None:
                try:
                    temporary = SOLAR_CACHE_PATH.with_suffix(".xml.tmp")
                    temporary.write_bytes(body)
                    temporary.replace(SOLAR_CACHE_PATH)
                except OSError as cache_error:
                    print(f"[solar] Could not save XML cache: {cache_error}", file=sys.stderr)
                self.send_bytes(
                    body,
                    "application/xml; charset=utf-8",
                    headers={"X-RadioStream-Cache": "fresh"},
                )
            else:
                try:
                    cache_age = time.time() - SOLAR_CACHE_PATH.stat().st_mtime
                    if 0 <= cache_age <= SOLAR_CACHE_MAX_AGE:
                        cached_body = SOLAR_CACHE_PATH.read_bytes()
                        root = ET.fromstring(cached_body)
                        if root.tag.casefold() == "solar":
                            self.send_bytes(
                                cached_body,
                                "application/xml; charset=utf-8",
                                headers={"X-RadioStream-Cache": "stale"},
                            )
                            return
                except (OSError, ET.ParseError) as cache_error:
                    print(f"[solar] No usable cached XML: {cache_error}", file=sys.stderr)
                self.send_json({"error": f"HamQSL request failed: {error_text}"}, 502)
        elif route == "/api/health":
            self.send_json({
                "ok": True,
                "version": "1.0",
                "directory_cached": core.directory_data is not None,
            })
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        global current_receiver, current_started_at, last_receiver_ids, last_receiver_error
        if not self.ensure_local_request():
            return
        maintenance = get_maintenance_state()
        if maintenance["active"]:
            self.send_json({
                "maintenance": True,
                "message": maintenance["message"],
            }, 503)
            return
        route = urllib.parse.urlsplit(self.path).path
        try:
            data = read_json_body(self)
            if route == "/api/config":
                with core.CONFIG_LOCK:
                    core.config = core.validate_config(data)
                    core.save_config()
                with STATE_LOCK:
                    current_receiver = None
                    current_started_at = 0.0
                    last_receiver_ids = []
                    last_receiver_error = None
                self.send_json({"ok": True, "config": dict(core.config)})

            elif route == "/api/select":
                wanted_id = str(data.get("id", ""))
                receivers, _ = core.discover_receivers()
                chosen = next(
                    (item for item in receivers
                     if item["id"] == wanted_id and item["available"]),
                    None,
                )
                if not chosen:
                    self.send_json(
                        {"error": "That receiver is no longer available in this range"},
                        404,
                    )
                    return
                online, reason = core.check_receiver_online(chosen)
                if not online:
                    with STATE_LOCK:
                        last_receiver_error = f"{chosen['name']}: {reason}"
                    self.send_json({"error": f"Receiver is not reachable: {reason}"}, 503)
                    return
                with STATE_LOCK:
                    current_receiver = chosen
                    current_started_at = time.monotonic()
                    last_receiver_ids.append(chosen["id"])
                    last_receiver_ids = last_receiver_ids[-100:]
                    last_receiver_error = None
                self.send_json({"ok": True, "state": get_state()})

            elif route == "/api/next":
                chosen = pick_next_receiver(force_next=True)
                self.send_json({"ok": bool(chosen), "state": get_state()})

            elif route == "/api/refresh-directory":
                payload = core.fetch_directory()
                self.send_json({
                    "ok": True,
                    "fetched_at": payload.get("fetched_at"),
                    "count": len(payload.get("receivers", [])),
                })
            else:
                self.send_error(404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 500)


def main() -> None:
    core.load_config()
    core.load_disk_directory()
    server = ThreadingHTTPServer((HOST, PORT), RadioStreamHandler)
    server.daemon_threads = True
    print("RadioStream+ is running.")
    print(f"Management: http://localhost:{PORT}/")
    print(f"Overlay:    http://localhost:{PORT}/overlay")
    print(f"KiwiSDR:    http://localhost:{PORT}/sdr")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopping RadioStream+...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
