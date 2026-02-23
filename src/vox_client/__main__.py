"""Entry point: sets up qasync event loop and launches the app."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import qasync

from vox_client.app import VoxApp

log = logging.getLogger(__name__)


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

    vox_app = VoxApp(qt_app)
    vox_app.show_main()

    # Warm up the multimedia backend so the first settings open isn't slow.
    # Deferred so it doesn't block window creation (can hang on some Linux setups).
    from PyQt6.QtCore import QTimer
    def _warmup_multimedia() -> None:
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            QMediaDevices.audioInputs()
        except Exception:
            pass
    QTimer.singleShot(0, _warmup_multimedia)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
