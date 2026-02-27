# PyInstaller hook for vox_media (pyo3 native extension).
#
# The vox_media package's __init__.py does `from .vox_media import *` to
# re-export the native Rust extension.  PyInstaller's analysis cannot trace
# relative imports of native sub-modules, so we declare it explicitly.
#
# Binary collection (vendored DLLs etc.) is handled by the spec file, which
# places delvewheel DLLs at the bundle root where PyInstaller can find them.

hiddenimports = ["vox_media.vox_media"]
