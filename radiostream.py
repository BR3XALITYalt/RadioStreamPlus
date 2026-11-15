#!/usr/bin/env python3
"""Launch RadioStream+ and update application files from its GitHub main branch.

This launcher is intentionally excluded from the updater's file allowlist. It
updates the application around itself, then restarts the process when Python
modules change.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import radiostream_server as server


REPOSITORY = "BR3XALITYalt/RadioStreamPlus"
BRANCH = "main"
GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
UPDATE_INTERVAL_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 20
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_UPDATE_BYTES = 20 * 1024 * 1024



UPDATABLE_FILES = {
    "radiostream_core.py",
    "radiostream_server.py",
    "index.html",
    "manage.html",
    "sdr.html",
    "app.js",
    "m.html",
    "maintenance.js",
    "radiostream.example.json",
    "browser-extension/manifest.json",
    "browser-extension/panel-hider.js",
}
PYTHON_FILES = {"radiostream_core.py", "radiostream_server.py"}

LAUNCHER_PATH = Path(__file__).resolve()
APP_DIR = LAUNCHER_PATH.parent
DATA_DIR = server.core.DATA_DIR
UPDATE_STATE_PATH = DATA_DIR / ".radiostream-update.json"
STOP_EVENT = threading.Event()
RESTART_EVENT = threading.Event()
UPDATE_LOCK = threading.Lock()


def log(message: str) -> None:
    print(f"[updater] {message}", flush=True)


def github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RadioStreamPlus-Updater/1.0",
    }


def read_url(url: str, headers: dict[str, str] | None = None, limit: int = MAX_FILE_BYTES) -> bytes:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": "RadioStreamPlus-Updater/1.0"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError(f"Download exceeds the {limit:,}-byte safety limit: {url}")
    return body


def read_json_url(url: str) -> dict[str, Any]:
    body = read_url(url, github_headers(), limit=8 * 1024 * 1024)
    result = json.loads(body.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"GitHub returned an unexpected response for {url}")
    return result


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def read_update_state() -> dict[str, Any]:
    try:
        value = json.loads(UPDATE_STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def write_update_state(commit_sha: str) -> None:
    payload = json.dumps(
        {"repository": REPOSITORY, "branch": BRANCH, "commit": commit_sha},
        indent=2,
    ) + "\n"
    fd, temporary_name = tempfile.mkstemp(
        prefix=".radiostream-update-",
        suffix=".tmp",
        dir=DATA_DIR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, UPDATE_STATE_PATH)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def latest_commit() -> dict[str, Any]:
    return read_json_url(
        f"{GITHUB_API}/repos/{REPOSITORY}/commits/{urllib.parse.quote(BRANCH)}"
    )


def remote_tree(tree_sha: str) -> dict[str, str]:
    payload = read_json_url(
        f"{GITHUB_API}/repos/{REPOSITORY}/git/trees/{tree_sha}?recursive=1"
    )
    if payload.get("truncated"):
        raise RuntimeError("GitHub returned a truncated repository tree")
    entries = payload.get("tree")
    if not isinstance(entries, list):
        raise RuntimeError("GitHub did not return a repository tree")
    return {
        str(item["path"]): str(item["sha"])
        for item in entries
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and item.get("path") in UPDATABLE_FILES
        and isinstance(item.get("sha"), str)
    }


def changed_files_since(previous_sha: str, current_sha: str) -> dict[str, str]:
    compare_url = (
        f"{GITHUB_API}/repos/{REPOSITORY}/compare/"
        f"{urllib.parse.quote(previous_sha)}...{urllib.parse.quote(current_sha)}?per_page=100"
    )
    comparison = read_json_url(compare_url)
    files = comparison.get("files")
    if comparison.get("status") != "ahead" or not isinstance(files, list) or len(files) >= 100:
        raise RuntimeError("Commit comparison is unavailable or incomplete; falling back to the full tree")

    changed: dict[str, str] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        path = item.get("filename")
        blob_sha = item.get("sha")
        status = item.get("status")
        if path in UPDATABLE_FILES and status != "removed" and isinstance(blob_sha, str):
            changed[path] = blob_sha
    return changed


def collect_remote_changes(commit: dict[str, Any], state: dict[str, Any]) -> tuple[str, dict[str, str]]:
    commit_sha = commit.get("sha")
    tree_sha = (commit.get("commit") or {}).get("tree", {}).get("sha")
    if not isinstance(commit_sha, str) or not isinstance(tree_sha, str):
        raise RuntimeError("GitHub's commit response did not contain a commit and tree SHA")

    previous_sha = state.get("commit")
    if isinstance(previous_sha, str) and previous_sha and previous_sha != commit_sha:
        try:
            return commit_sha, changed_files_since(previous_sha, commit_sha)
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
            log(f"Incremental comparison unavailable ({exc}); checking the full tree.")

    return commit_sha, remote_tree(tree_sha)


def download_update_file(path: str, expected_sha: str, commit_sha: str) -> bytes:
    encoded_path = urllib.parse.quote(path, safe="/")
    url = f"{RAW_BASE}/{REPOSITORY}/{commit_sha}/{encoded_path}"
    content = read_url(url, limit=MAX_FILE_BYTES)
    actual_sha = git_blob_sha(content)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Git blob verification failed for {path}: expected {expected_sha}, got {actual_sha}"
        )
    return content


def stage_file(path: str, content: bytes) -> Path:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{Path(path).name}.update-",
        suffix=".tmp",
        dir=APP_DIR,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return Path(temporary_name)


def restore_originals(originals: dict[str, bytes | None]) -> None:
    """Roll back any replacements if the multi-file installation fails."""
    for relative_path, original in originals.items():
        target = APP_DIR / relative_path
        if original is None:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
            continue

        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.rollback-",
            suffix=".tmp",
            dir=APP_DIR,
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def install_update(commit_sha: str, remote_files: dict[str, str]) -> bool:
    """Download, verify, stage, and atomically install changed allowlisted files."""
    downloads: dict[str, bytes] = {}
    total_bytes = 0

    for path, expected_sha in sorted(remote_files.items()):
        if path not in UPDATABLE_FILES:
            continue
        content = download_update_file(path, expected_sha, commit_sha)
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_UPDATE_BYTES:
            raise ValueError("The update exceeds the 20 MB total safety limit.")

        target = APP_DIR / path
        try:
            local_content = target.read_bytes()
        except FileNotFoundError:
            local_content = None
        if local_content is None or git_blob_sha(local_content) != expected_sha:
            downloads[path] = content

    if not downloads:
        write_update_state(commit_sha)
        return False

    log("Update available: " + ", ".join(sorted(downloads)))
    staged: dict[str, Path] = {}
    originals: dict[str, bytes | None] = {}
    changed_python = bool(PYTHON_FILES.intersection(downloads))

    try:
        
        for path, content in downloads.items():
            staged[path] = stage_file(path, content)
            target = APP_DIR / path
            try:
                originals[path] = target.read_bytes()
            except FileNotFoundError:
                originals[path] = None

        server.set_maintenance(
            True,
            f"RadioStream+ is installing update {commit_sha[:12]}.",
        )
        log("Maintenance mode enabled.")
        time.sleep(1.0)

        installed: list[str] = []
        try:
            for path, temporary in staged.items():
                target = APP_DIR / path
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(temporary, target.stat().st_mode if target.exists() else 0o644)
                except OSError:
                    pass
                os.replace(temporary, target)
                installed.append(path)

            write_update_state(commit_sha)
        except Exception:
            log("Installation failed. Restoring original files.")
            try:
                restore_originals({path: originals[path] for path in installed})
            except Exception as rollback_error:
                message = (
                    "The update and automatic rollback both failed. "
                    "Stop RadioStream+ and restore the application files manually."
                )
                server.set_maintenance(True, message)
                STOP_EVENT.set()
                log(f"CRITICAL: rollback failed: {rollback_error}")
                raise RuntimeError(message) from rollback_error
            server.set_maintenance(False, "The update failed. The previous files were restored.")
            raise

        log("Installed " + ", ".join(sorted(installed)))
        if changed_python:
            
            
            
            log("Python modules changed. Reloading RadioStream+ in place.")
            RESTART_EVENT.set()
        else:
            server.set_maintenance(False, "Update complete.")
        return True
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def check_for_updates() -> None:
    with UPDATE_LOCK:
        state = read_update_state()
        commit = latest_commit()
        latest_sha = commit.get("sha")
        if not isinstance(latest_sha, str):
            raise RuntimeError("GitHub did not return the latest commit SHA")
        if state.get("commit") == latest_sha:
            return

        commit_sha, remote_files = collect_remote_changes(commit, state)
        install_update(commit_sha, remote_files)


def updater_loop() -> None:
    log(f"Watching https://github.com/{REPOSITORY}/tree/{BRANCH}")
    while not STOP_EVENT.is_set():
        try:
            check_for_updates()
        except (OSError, urllib.error.URLError, TimeoutError, ValueError, RuntimeError) as exc:
            log(f"Update check failed; will retry: {exc}")
        except Exception as exc:
            log(f"Unexpected updater error; will retry: {type(exc).__name__}: {exc}")

        if STOP_EVENT.wait(UPDATE_INTERVAL_SECONDS):
            break


def start_updater() -> threading.Thread:
    thread = threading.Thread(
        target=updater_loop,
        name="RadioStreamPlus-Updater",
        daemon=True,
    )
    thread.start()
    return thread


if __name__ == "__main__":
    start_updater()
    try:
        while not STOP_EVENT.is_set():
            RESTART_EVENT.clear()
            server.main(STOP_EVENT, RESTART_EVENT)

            if STOP_EVENT.is_set() or not RESTART_EVENT.is_set():
                break

            
            
            import importlib
            log("Reloading updated Python modules.")
            importlib.reload(server.core)
            importlib.reload(server)
    finally:
        STOP_EVENT.set()
