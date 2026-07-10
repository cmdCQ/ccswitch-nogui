from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any


APP_DIR_NAME = ".ccswitch-nogui"
BACKUP_RETAIN = 10


def home_dir() -> Path:
    override = os.environ.get("CCSWITCH_NOGUI_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home()


def claude_dir() -> Path:
    override = os.environ.get("CCSWITCH_NOGUI_CLAUDE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return home_dir() / ".claude"


def claude_settings_path() -> Path:
    directory = claude_dir()
    settings = directory / "settings.json"
    legacy = directory / "claude.json"
    if settings.exists() or not legacy.exists():
        return settings
    return legacy


def app_dir() -> Path:
    return home_dir() / APP_DIR_NAME


def store_path() -> Path:
    return app_dir() / "providers.json"


def legacy_profiles_path() -> Path:
    return claude_dir() / "cc-profiles.json"


def backup_dir() -> Path:
    return app_dir() / "backups"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any, mode: int | None = None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    atomic_write(path, text.encode("utf-8"), mode=mode)


def atomic_write(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is None and path.exists():
            mode = path.stat().st_mode & 0o777
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def backup_file(path: Path, label: str) -> Path | None:
    if not path.exists():
        return None
    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    target = directory / f"{label}.{ts}.json"
    counter = 1
    while target.exists():
        target = directory / f"{label}.{ts}.{counter}.json"
        counter += 1
    shutil.copy2(path, target)
    rotate_backups(label)
    return target


def rotate_backups(label: str, retain: int = BACKUP_RETAIN) -> None:
    directory = backup_dir()
    if not directory.exists():
        return
    backups = sorted(directory.glob(f"{label}.*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old in backups[retain:]:
        old.unlink(missing_ok=True)
