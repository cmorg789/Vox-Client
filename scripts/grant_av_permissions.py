#!/usr/bin/env python3
"""Grant camera and microphone permissions for development.

macOS requires an .app bundle with Info.plist for Qt's permission API
to work.  When running unbundled via ``.venv/bin/python -m vox_client``,
this script uses AVFoundation (via pyobjc) to trigger the real macOS
permission prompts so the terminal app gets camera/mic access.

Run once after a fresh checkout or after resetting privacy permissions::

    .venv/bin/python scripts/grant_av_permissions.py

Requires: pyobjc-framework-AVFoundation
    pip install pyobjc-framework-AVFoundation
"""

from __future__ import annotations

import sys
import threading


def _request(media_type: str, label: str) -> bool:
    import AVFoundation as AVF

    status = AVF.AVCaptureDevice.authorizationStatusForMediaType_(media_type)
    if status == 3:
        print(f"  {label}: already authorized")
        return True
    if status == 2:
        print(f"  {label}: denied — open System Settings → Privacy & Security → {label}")
        return False
    if status == 1:
        print(f"  {label}: restricted by system policy")
        return False

    # NotDetermined — trigger the prompt
    print(f"  {label}: requesting access (approve the system dialog)...")
    event = threading.Event()
    result = [False]

    def handler(granted: bool) -> None:
        result[0] = granted
        event.set()

    AVF.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
        media_type, handler,
    )
    event.wait(timeout=60)
    if result[0]:
        print(f"  {label}: granted")
    else:
        print(f"  {label}: denied")
    return result[0]


def main() -> None:
    if sys.platform != "darwin":
        print("This script is only needed on macOS.")
        return

    try:
        import AVFoundation as AVF
    except ImportError:
        print("pyobjc-framework-AVFoundation is required:")
        print("  .venv/bin/pip install pyobjc-framework-AVFoundation")
        sys.exit(1)

    print("Requesting A/V permissions for development...\n")
    cam = _request(AVF.AVMediaTypeVideo, "Camera")
    mic = _request(AVF.AVMediaTypeAudio, "Microphone")

    print()
    if cam and mic:
        print("All permissions granted. You can now run:")
        print("  .venv/bin/python -m vox_client")
    else:
        print("Some permissions were denied. Check System Settings → Privacy & Security.")


if __name__ == "__main__":
    main()
