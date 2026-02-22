"""Entry point: sets up qasync event loop and launches the app."""

from __future__ import annotations

import asyncio
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
import qasync

from vox_client.app import VoxApp


def main() -> None:
    # Enable high-DPI scaling with passthrough (no rounding) so text and
    # widgets render at native Retina resolution instead of being upscaled.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    qt_app = QApplication(sys.argv)
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    # Warm up the multimedia backend so the first settings open isn't slow.
    # The FFmpeg plugin loads lazily on first *use*, not on import — calling
    # audioInputs() forces the plugin to load now.
    try:
        from PyQt6.QtMultimedia import QMediaDevices
        QMediaDevices.audioInputs()
    except Exception:
        pass  # multimedia backend unavailable or permissions not yet granted

    vox_app = VoxApp(qt_app)
    vox_app.show_main()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
