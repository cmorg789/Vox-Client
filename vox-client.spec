# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Vox Client – onedir build with macOS .app bundle."""

import glob
import os
import sys
import warnings

# Collect the native vox_media Rust extension (.so / .pyd / .dylib).
# collect_dynamic_libs() misses pyo3 extensions that live inside a package,
# so we locate the native binary by globbing the installed package directory.
vox_media_binaries = []
try:
    import vox_media as _vm
    pkg_dir = os.path.dirname(_vm.__file__)
    # Look for the native extension: .pyd (Windows), .so (Linux/macOS)
    # and any companion DLLs the extension depends on (Windows).
    for pattern in ("*.pyd", "*.so", "*.dll"):
        for path in glob.glob(os.path.join(pkg_dir, pattern)):
            fname = os.path.basename(path)
            # Skip __init__ or pure-python files that somehow match
            if fname.startswith("__"):
                continue
            vox_media_binaries.append((path, "vox_media"))
    # On Windows, delvewheel places vendored DLLs in a .libs sibling directory
    # (e.g. site-packages/vox_media.libs/).  Collect those too.
    site_dir = os.path.dirname(pkg_dir)
    for libs_name in ("vox_media.libs", ".vox_media.libs"):
        libs_dir = os.path.join(site_dir, libs_name)
        if os.path.isdir(libs_dir):
            for path in glob.glob(os.path.join(libs_dir, "*.dll")):
                vox_media_binaries.append((path, libs_name))
    if vox_media_binaries:
        print(f"vox_media: collected {len(vox_media_binaries)} native binaries")
        for src, dst in vox_media_binaries:
            print(f"  {src} -> {dst}/")
    else:
        warnings.warn("vox_media package found but no native extension located — audio will not work!")
except ImportError:
    warnings.warn("vox_media not installed — native media will not be bundled")

a = Analysis(
    ["src/vox_client/__main__.py"],
    pathex=["src"],
    binaries=vox_media_binaries,
    datas=[
        ("src/vox_client/resources/icons", "vox_client/resources/icons"),
        ("src/vox_client/resources/fonts", "vox_client/resources/fonts"),
    ],
    hiddenimports=[
        # PyQt6
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtSvg",
        "PyQt6.QtNetwork",
        # Async
        "qasync",
        # Theme
        "catppuccin",
        # SDK core
        "vox_sdk",
        "vox_sdk.client",
        "vox_sdk.gateway",
        "vox_sdk.http",
        "vox_sdk.errors",
        "vox_sdk.permissions",
        "vox_sdk.pagination",
        "vox_sdk.rate_limit",
        # SDK models (all lazy-loaded)
        "vox_sdk.models.base",
        "vox_sdk.models.auth",
        "vox_sdk.models.bots",
        "vox_sdk.models.channels",
        "vox_sdk.models.dms",
        "vox_sdk.models.e2ee",
        "vox_sdk.models.emoji",
        "vox_sdk.models.enums",
        "vox_sdk.models.errors",
        "vox_sdk.models.events",
        "vox_sdk.models.federation",
        "vox_sdk.models.files",
        "vox_sdk.models.invites",
        "vox_sdk.models.members",
        "vox_sdk.models.messages",
        "vox_sdk.models.moderation",
        "vox_sdk.models.roles",
        "vox_sdk.models.server",
        "vox_sdk.models.sync",
        "vox_sdk.models.users",
        "vox_sdk.models.voice",
        # SDK API (all lazy-loaded in client.py)
        "vox_sdk.api.auth",
        "vox_sdk.api.bots",
        "vox_sdk.api.channels",
        "vox_sdk.api.dms",
        "vox_sdk.api.e2ee",
        "vox_sdk.api.embeds",
        "vox_sdk.api.emoji",
        "vox_sdk.api.federation",
        "vox_sdk.api.files",
        "vox_sdk.api.invites",
        "vox_sdk.api.members",
        "vox_sdk.api.messages",
        "vox_sdk.api.moderation",
        "vox_sdk.api.roles",
        "vox_sdk.api.search",
        "vox_sdk.api.server",
        "vox_sdk.api.sync",
        "vox_sdk.api.users",
        "vox_sdk.api.voice",
        "vox_sdk.api.webhooks",
        # Native media extension
        "vox_media",
        "vox_media.vox_media",
        "vox_sdk._media",
        # Transport
        "httpx",
        "websockets",
        "zstandard",
        "pydantic",
    ],
    hookspath=["hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "test", "xmlrpc"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="vox-client",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False if sys.platform == "darwin" else True,  # UPX breaks macOS code signing
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False if sys.platform == "darwin" else True,
    upx_exclude=[],
    name="vox-client",
)

# macOS: produce a .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Vox Client.app",
        icon=None,
        bundle_identifier="com.vox.client",
        info_plist={
            "CFBundleDisplayName": "Vox Client",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "Vox Client needs microphone access for voice chat.",
            "NSCameraUsageDescription": "Vox Client needs camera access for video chat.",
        },
    )
