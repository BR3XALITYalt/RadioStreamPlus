#!/usr/bin/env python3
"""Bootstrap the current RadioStream+ source using a bundled Python runtime."""
from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import sys
import tempfile
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile


REPOSITORY = "BR3XALITYalt/RadioStreamPlus"
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/commits/{BRANCH}"
ARCHIVE_URL = f"https://codeload.github.com/{REPOSITORY}/zip/"
USER_AGENT = "RadioStreamPlus-Bootstrap/1.0"
REQUEST_TIMEOUT_SECONDS = 25
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_EXTRACTED_BYTES = 96 * 1024 * 1024
MAX_FILE_BYTES = 24 * 1024 * 1024
MAX_ARCHIVE_FILES = 4096
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

REQUIRED_SOURCE_FILES = (
    "radiostream.py",
    "radiostream_server.py",
    "radiostream_core.py",
    "index.html",
    "manage.html",
    "sdr.html",
    "app.js",
    "m.html",
    "maintenance.js",
    "radiostream.example.json",
)

MIGRATABLE_DATA_FILES = (
    "radiostream.json",
    "kiwi_directory_cache.json",
    "station_preferences.json",
    "receiverbook_cache.json",
    "openwebrx_custom.json",
    "radio_presets.json",
    "solar_xml_cache.xml",
    ".solar_last_attempt",
)


class BootstrapError(RuntimeError):
    """Raised when no usable application source can be selected."""


class AlreadyRunningError(BootstrapError):
    """Raised when another launcher already owns the local application."""


def log(message: str) -> None:
    print(f"[RadioStream+] {message}", flush=True)


def install_root() -> Path:
    override = os.environ.get("RADIOSTREAM_HOME")
    if override:
        return Path(override).expanduser().resolve()

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_DATA_HOME")
        if not base:
            base = str(Path.home() / ".local" / "share")

    return (Path(base) / "RadioStreamPlus").expanduser().resolve()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


@contextmanager
def instance_lock(path: Path):
    """Hold a one-byte process lock for the full server lifetime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    lock_backend = None

    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if handle.read(1) == b"":
                handle.seek(0)
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise AlreadyRunningError(
                    "RadioStream+ is already running."
                ) from exc
            locked = True
            lock_backend = msvcrt
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise AlreadyRunningError(
                    "RadioStream+ is already running."
                ) from exc
            locked = True
            lock_backend = fcntl

        yield
    finally:
        if locked:
            try:
                if os.name == "nt":
                    handle.seek(0)
                    lock_backend.locking(handle.fileno(), lock_backend.LK_UNLCK, 1)
                else:
                    lock_backend.flock(handle.fileno(), lock_backend.LOCK_UN)
            except OSError:
                pass
        handle.close()


def read_url(url: str, limit: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json, application/zip",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        final_url = response.geturl()
        if not final_url.startswith("https://"):
            raise BootstrapError("GitHub returned a non-HTTPS download URL.")
        body = response.read(limit + 1)

    if len(body) > limit:
        raise BootstrapError(f"Download exceeded the {limit:,}-byte limit.")
    return body


def latest_commit() -> str:
    payload = json.loads(read_url(API_URL, 512 * 1024).decode("utf-8"))
    commit = payload.get("sha") if isinstance(payload, dict) else None
    if not isinstance(commit, str) or not COMMIT_PATTERN.fullmatch(commit):
        raise BootstrapError("GitHub did not return a valid commit ID.")
    return commit


def download_source_archive(commit: str) -> bytes:
    if not COMMIT_PATTERN.fullmatch(commit):
        raise BootstrapError("Refusing to download an invalid commit ID.")
    return read_url(ARCHIVE_URL + urllib.parse.quote(commit, safe=""), MAX_ARCHIVE_BYTES)


def extract_source_archive(archive_data: bytes, destination: Path) -> None:
    """Extract a GitHub source ZIP while rejecting unsafe paths and file types."""
    destination.mkdir(parents=True, exist_ok=True)
    if len(archive_data) > MAX_ARCHIVE_BYTES:
        raise BootstrapError("The source archive exceeds the download size limit.")

    try:
        archive = zipfile.ZipFile(BytesIO(archive_data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise BootstrapError("GitHub returned an invalid source archive.") from exc

    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ARCHIVE_FILES:
            raise BootstrapError("The source archive has an invalid file count.")

        roots: set[str] = set()
        extracted_names: set[str] = set()
        extracted_total = 0
        extracted_files = 0

        for info in entries:
            name = info.filename
            if not name or name.startswith("/") or "\\" in name or "\x00" in name:
                raise BootstrapError("The source archive contains an unsafe path.")

            parts = name.split("/")
            if info.is_dir() and parts and parts[-1] == "":
                parts.pop()

            if (
                not parts
                or any(part in {"", ".", ".."} for part in parts)
                or any(":" in part for part in parts)
            ):
                raise BootstrapError("The source archive contains an unsafe path.")

            roots.add(parts[0])
            if len(roots) != 1:
                raise BootstrapError("The source archive contains multiple root folders.")
            if len(parts) == 1:
                if not info.is_dir():
                    raise BootstrapError("The source archive has an invalid root entry.")
                continue

            relative_parts = parts[1:]
            relative_name = "/".join(relative_parts)
            target = destination.joinpath(*relative_parts)

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            if info.flag_bits & 0x1:
                raise BootstrapError("Encrypted files are not accepted in the source archive.")

            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise BootstrapError("Symbolic links are not accepted in the source archive.")

            if info.file_size < 0 or info.file_size > MAX_FILE_BYTES:
                raise BootstrapError(f"Source file exceeds the size limit: {relative_name}")

            extracted_total += info.file_size
            extracted_files += 1
            if extracted_total > MAX_EXTRACTED_BYTES or extracted_files > MAX_ARCHIVE_FILES:
                raise BootstrapError("The expanded source archive exceeds its safety limits.")

            key = relative_name.casefold()
            if key in extracted_names:
                raise BootstrapError("The source archive contains duplicate file paths.")
            extracted_names.add(key)

            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(info, "r") as source, target.open("xb") as output:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > info.file_size or written > MAX_FILE_BYTES:
                        raise BootstrapError(f"Source file exceeded its declared size: {relative_name}")
                    output.write(chunk)

            if written != info.file_size:
                raise BootstrapError(f"Source file size did not match its archive entry: {relative_name}")

        if len(roots) != 1:
            raise BootstrapError("The source archive does not have one root folder.")

    missing = [
        name for name in REQUIRED_SOURCE_FILES
        if not (destination / name).is_file()
    ]
    if missing:
        raise BootstrapError(
            "The source archive is missing required files: " + ", ".join(missing)
        )


def source_is_complete(source_dir: Path) -> bool:
    return source_dir.is_dir() and all(
        (source_dir / name).is_file() for name in REQUIRED_SOURCE_FILES
    )


def read_source_commit(source_dir: Path) -> str | None:
    try:
        metadata = json.loads(
            (source_dir / ".radiostream-source.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None

    if (
        isinstance(metadata, dict)
        and metadata.get("repository") == REPOSITORY
        and metadata.get("branch") == BRANCH
        and isinstance(metadata.get("commit"), str)
        and COMMIT_PATTERN.fullmatch(metadata["commit"])
    ):
        return metadata["commit"]
    return None


def write_source_metadata(source_dir: Path, commit: str) -> None:
    payload = {
        "repository": REPOSITORY,
        "branch": BRANCH,
        "commit": commit,
    }
    atomic_write(
        source_dir / ".radiostream-source.json",
        (json.dumps(payload, indent=2) + "\n").encode("utf-8"),
    )


def read_update_commit(data_dir: Path) -> str | None:
    try:
        state = json.loads(
            (data_dir / ".radiostream-update.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None

    commit = state.get("commit") if isinstance(state, dict) else None
    if (
        isinstance(state, dict)
        and state.get("repository") == REPOSITORY
        and state.get("branch") == BRANCH
        and isinstance(commit, str)
        and COMMIT_PATTERN.fullmatch(commit)
    ):
        return commit
    return None


def write_update_state(data_dir: Path, commit: str) -> None:
    state = {
        "repository": REPOSITORY,
        "branch": BRANCH,
        "commit": commit,
    }
    atomic_write(
        data_dir / ".radiostream-update.json",
        (json.dumps(state, indent=2) + "\n").encode("utf-8"),
    )


def save_archive_cache(cache_dir: Path, archive_data: bytes, commit: str) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "repository": REPOSITORY,
        "branch": BRANCH,
        "commit": commit,
        "sha256": hashlib.sha256(archive_data).hexdigest(),
    }
    atomic_write(cache_dir / "source.zip", archive_data)
    atomic_write(
        cache_dir / "source.json",
        (json.dumps(metadata, indent=2) + "\n").encode("utf-8"),
    )


def load_archive_cache(cache_dir: Path) -> tuple[str, bytes]:
    try:
        metadata = json.loads((cache_dir / "source.json").read_text(encoding="utf-8"))
        archive_data = (cache_dir / "source.zip").read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise BootstrapError("No cached source archive is available.") from exc

    commit = metadata.get("commit") if isinstance(metadata, dict) else None
    expected_hash = metadata.get("sha256") if isinstance(metadata, dict) else None
    if (
        not isinstance(metadata, dict)
        or metadata.get("repository") != REPOSITORY
        or metadata.get("branch") != BRANCH
        or not isinstance(commit, str)
        or not COMMIT_PATTERN.fullmatch(commit)
        or not isinstance(expected_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        or len(archive_data) > MAX_ARCHIVE_BYTES
        or hashlib.sha256(archive_data).hexdigest() != expected_hash
    ):
        raise BootstrapError("The cached source archive failed its integrity check.")

    return commit, archive_data


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def install_source_archive(
    archive_data: bytes,
    commit: str,
    root: Path,
    *,
    cache_archive: bool = True,
) -> Path:
    """Stage and validate a complete source tree before replacing the active one."""
    if not COMMIT_PATTERN.fullmatch(commit):
        raise BootstrapError("Refusing to install source for an invalid commit ID.")

    root.mkdir(parents=True, exist_ok=True)
    active = root / "source"
    backup = root / ".source-previous"
    staging = Path(tempfile.mkdtemp(prefix=".source-staging-", dir=root))

    try:
        extract_source_archive(archive_data, staging)
        write_source_metadata(staging, commit)
        if not source_is_complete(staging):
            raise BootstrapError("The extracted source tree is incomplete.")

        if cache_archive:
            try:
                save_archive_cache(root / "cache", archive_data, commit)
            except OSError as exc:
                log(f"Could not update the offline source archive: {exc}")

        remove_path(backup)
        if active.exists():
            os.replace(active, backup)

        try:
            os.replace(staging, active)
        except Exception:
            if backup.exists() and not active.exists():
                os.replace(backup, active)
            raise

        try:
            remove_path(backup)
        except OSError as exc:
            log(f"Could not remove the previous source folder: {exc}")

        return active
    finally:
        if staging.exists():
            remove_path(staging)


def restore_cached_source(root: Path) -> tuple[Path, str]:
    commit, archive_data = load_archive_cache(root / "cache")
    source_dir = install_source_archive(
        archive_data,
        commit,
        root,
        cache_archive=False,
    )
    return source_dir, commit


def migrate_adjacent_data(executable_dir: Path, data_dir: Path) -> None:
    """Copy existing data beside the EXE once, without replacing newer data."""
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        source_dir = executable_dir.resolve()
        target_dir = data_dir.resolve()
    except OSError:
        return

    if source_dir == target_dir:
        return

    for filename in MIGRATABLE_DATA_FILES:
        source = source_dir / filename
        target = target_dir / filename
        if not source.is_file() or target.exists():
            continue
        try:
            shutil.copy2(source, target)
            log(f"Imported existing {filename}.")
        except OSError as exc:
            log(f"Could not import {filename}: {exc}")


def choose_source(root: Path, data_dir: Path) -> Path:
    """Prefer the newest GitHub commit; fall back to the installed or cached source."""
    active = root / "source"
    last_error: Exception | None = None

    try:
        latest = latest_commit()
        active_commit = read_source_commit(active)
        update_commit = read_update_commit(data_dir)

        if source_is_complete(active) and active_commit == latest:
            write_update_state(data_dir, latest)
            log(f"Using current source ({latest[:12]}).")
            return active

        if source_is_complete(active) and update_commit == latest:
            try:
                write_source_metadata(active, latest)
            except OSError as exc:
                log(f"Could not refresh the local source marker: {exc}")
            log(f"Using source already updated to {latest[:12]}.")
            return active

        log(f"Downloading source for {latest[:12]}.")
        archive_data = download_source_archive(latest)
        source_dir = install_source_archive(archive_data, latest, root)
        write_update_state(data_dir, latest)
        log(f"Installed source ({latest[:12]}).")
        return source_dir
    except Exception as exc:
        last_error = exc
        log(f"Online source refresh failed: {type(exc).__name__}: {exc}")

    if source_is_complete(active) and read_source_commit(active):
        commit = read_source_commit(active)
        log(f"Using cached source ({commit[:12]}).")
        return active

    try:
        source_dir, commit = restore_cached_source(root)
        try:
            write_update_state(data_dir, commit)
        except OSError as exc:
            log(f"Could not update the local update state: {exc}")
        log(f"Restored cached source ({commit[:12]}).")
        return source_dir
    except Exception as cache_error:
        detail = f"Online refresh failed: {last_error}. Cached source unavailable: {cache_error}"
        raise BootstrapError(
            detail + ". Connect to the internet and start RadioStream+ again."
        ) from cache_error


def run_application() -> None:
    root = install_root()
    source_dir = root / "source"
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (root / "cache").mkdir(parents=True, exist_ok=True)

    with instance_lock(data_dir / ".launcher.lock"):
        if getattr(sys, "frozen", False):
            migrate_adjacent_data(Path(sys.executable).resolve().parent, data_dir)

        source_dir = choose_source(root, data_dir)
        if not source_is_complete(source_dir):
            raise BootstrapError("The selected RadioStream+ source folder is incomplete.")

        os.environ["RADIOSTREAM_DATA_DIR"] = str(data_dir.resolve())
        source_text = str(source_dir.resolve())
        if source_text in sys.path:
            sys.path.remove(source_text)
        sys.path.insert(0, source_text)

        log(f"Data directory: {data_dir}")
        runpy.run_path(str(source_dir / "radiostream.py"), run_name="__main__")


def main() -> int:
    try:
        run_application()
    except AlreadyRunningError as exc:
        log(str(exc))
        return 0
    except KeyboardInterrupt:
        log("Stopped.")
        return 0
    except Exception as exc:
        log(f"Startup failed: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
