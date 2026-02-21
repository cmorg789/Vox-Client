"""Entry point: sets up qasync event loop and launches the app."""

from __future__ import annotations

import asyncio
import sys

from PyQt6.QtWidgets import QApplication
import qasync

from vox_client.app import VoxApp


def main() -> None:
    qt_app = QApplication(sys.argv)
    loop = qasync.QEventLoop(qt_app)
    asyncio.set_event_loop(loop)

    vox_app = VoxApp(qt_app)
    vox_app.show_main()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
