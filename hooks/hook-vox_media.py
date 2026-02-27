# PyInstaller hook for vox_media (pyo3 native extension).
#
# The vox_media package's __init__.py does `from .vox_media import *` to
# re-export the native Rust extension.  PyInstaller's analysis cannot trace
# relative imports of native sub-modules, so we declare it explicitly.

from PyInstaller.utils.hooks import collect_dynamic_libs

hiddenimports = ["vox_media.vox_media"]
binaries = collect_dynamic_libs("vox_media")
