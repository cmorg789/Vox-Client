# PyInstaller hook for vox_media (pyo3 native extension).
#
# The vox_media package's __init__.py does `from .vox_media import *` to
# re-export the native Rust extension.  PyInstaller's analysis cannot trace
# relative imports of native sub-modules, so we declare it explicitly.
#
# On Windows, the wheel is repaired by delvewheel which places vendored DLLs
# (dav1d, opus, etc.) in a .vox_media.libs/ directory.  We collect those too.

import glob
import os
import warnings

from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import collect_dynamic_libs

hiddenimports = ["vox_media.vox_media"]
binaries = collect_dynamic_libs("vox_media")
datas = []

if is_win:
    # Try the PyInstaller built-in delvewheel collector first
    try:
        from PyInstaller.utils.hooks import collect_delvewheel_libs_directory

        datas, binaries = collect_delvewheel_libs_directory(
            "vox_media", datas=datas, binaries=binaries
        )
    except ImportError:
        pass  # older PyInstaller without delvewheel support

    # Fallback: manually collect .vox_media.libs / vox_media.libs DLLs
    # in case collect_delvewheel_libs_directory missed them.
    try:
        import vox_media

        site_dir = os.path.dirname(os.path.dirname(vox_media.__file__))
        for libs_name in (".vox_media.libs", "vox_media.libs"):
            libs_dir = os.path.join(site_dir, libs_name)
            if os.path.isdir(libs_dir):
                for dll in glob.glob(os.path.join(libs_dir, "*.dll")):
                    binaries.append((dll, libs_name))
    except Exception as exc:
        warnings.warn(f"hook-vox_media: failed to collect vendored DLLs: {exc}")
