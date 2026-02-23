# PyInstaller hook for vox_media (pyo3 native extension).
#
# The vox_media package's __init__.py does `from .vox_media import *` to
# re-export the native Rust extension.  PyInstaller's analysis cannot trace
# relative imports of native sub-modules, so we declare it explicitly.

hiddenimports = ["vox_media.vox_media"]
