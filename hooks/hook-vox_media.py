# PyInstaller hook for vox_media (pyo3 native extension).
#
# The vox_media package's __init__.py does `from .vox_media import *` to
# re-export the native Rust extension.  PyInstaller's analysis cannot trace
# relative imports of native sub-modules, so we declare it explicitly.
#
# On Windows, the wheel is repaired by delvewheel which places vendored DLLs
# (dav1d, opus, etc.) in a vox_media.libs/ directory.  We collect those too.

from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import collect_dynamic_libs

hiddenimports = ["vox_media.vox_media"]
binaries = collect_dynamic_libs("vox_media")

if is_win:
    try:
        from PyInstaller.utils.hooks import collect_delvewheel_libs_directory

        datas, binaries = collect_delvewheel_libs_directory(
            "vox_media", datas=[], binaries=binaries
        )
    except ImportError:
        pass  # older PyInstaller without delvewheel support
