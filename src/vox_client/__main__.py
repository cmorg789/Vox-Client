"""Entry point: sets up qasync event loop and launches the app."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
import qasync

from vox_client.app import VoxApp

log = logging.getLogger(__name__)


def _install_exception_hooks() -> None:
    """Install global handlers so unhandled exceptions always get logged."""

    def _excepthook(exc_type, exc_value, exc_tb):  # noqa: ANN001
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _excepthook

    def _asyncio_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:  # noqa: ANN401
        exc = context.get("exception")
        msg = context.get("message", "Unhandled asyncio exception")
        if exc is not None:
            log.critical("%s", msg, exc_info=exc)
        else:
            log.critical("%s", msg)

    asyncio.get_event_loop().set_exception_handler(_asyncio_handler)


def main() -> None:
    parser = argparse.ArgumentParser(prog="vox_client")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=None,
        help="Override the persisted log level",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Also log to stderr",
    )
    args = parser.parse_args()

    # Configure logging before anything else
    from vox_client.logging_config import setup_logging
    setup_logging(level=args.log_level, stderr=args.verbose)

    # Enable high-DPI scaling with passthrough (no rounding) so text and
    # widgets render at native Retina resolution instead of being upscaled.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qt_app = QApplication(sys.argv)
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)
    _install_exception_hooks()

    vox_app = VoxApp(qt_app)
    vox_app.show_main()

    # Warm up the multimedia backend so the first settings open isn't slow.
    # Deferred so it doesn't block window creation (can hang on some Linux setups).
    from PySide6.QtCore import QTimer
    def _warmup_multimedia() -> None:
        try:
            from PySide6.QtMultimedia import QMediaDevices
            QMediaDevices.audioInputs()
        except Exception:
            pass
    QTimer.singleShot(0, _warmup_multimedia)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
