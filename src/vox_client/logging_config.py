"""Logging configuration – OS-appropriate log paths + rotating file handler."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_log_dir() -> Path:
    """Return the OS-specific log directory, creating it if needed."""
    if sys.platform == "darwin":
        d = Path.home() / "Library" / "Logs" / "Vox"
    elif sys.platform == "win32":
        local = Path(
            __import__("os").environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        )
        d = local / "Vox" / "Logs"
    else:
        # Linux / other: XDG_STATE_HOME or fallback
        xdg = __import__("os").environ.get("XDG_STATE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "state"
        d = base / "vox"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(level: str | None = None, stderr: bool = False) -> None:
    """Configure the root logger with a rotating file handler.

    *level* defaults to the value persisted in QSettings (``"logging/level"``),
    falling back to ``"WARNING"`` when nothing is saved.

    A ``StreamHandler(sys.stderr)`` is added when *stderr* is ``True`` **or**
    when the resolved level is ``DEBUG``.
    """
    if level is None:
        from PySide6.QtCore import QSettings
        settings = QSettings("Vox", "VoxClient")
        level = settings.value("logging/level", "INFO")

    level = level.upper()
    numeric = getattr(logging, level, logging.WARNING)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    log_path = get_log_dir() / "VoxClient.log"
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(numeric)
    root.addHandler(file_handler)

    # qasync logs full Future results (including raw file bytes) at DEBUG;
    # filter those specific messages to keep other qasync debug output useful.
    class _QAsyncBytesFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if record.msg == "Setting Future result: %s" and record.args:
                val = record.args[0] if isinstance(record.args, tuple) else record.args
                if isinstance(val, (bytes, bytearray)) and len(val) > 200:
                    record.args = (f"<{len(val)} bytes>",)
            return True

    # Filters don't propagate to child loggers, so target the specific one
    logging.getLogger("qasync._QThreadWorker").addFilter(_QAsyncBytesFilter())

    if stderr or level == "DEBUG":
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(fmt)
        root.addHandler(stream_handler)
