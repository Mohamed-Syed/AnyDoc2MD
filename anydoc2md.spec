# PyInstaller spec for AnyDoc2MD -- builds a standalone, --onedir bundle
# (not --onefile: onefile re-extracts the whole payload to a temp folder
# on every launch, which is a real, repeated startup cost for a bundle
# this size; onedir launches instantly since nothing needs unpacking).
#
# Cross-platform: on Windows it produces dist/AnyDoc2MD/AnyDoc2MD.exe, on
# Linux dist/AnyDoc2MD/AnyDoc2MD, and on macOS a dist/AnyDoc2MD.app
# bundle. The trimmed Tesseract/Poppler for the host platform must be
# staged into vendor/ first (scripts/prepare_vendor.py).
#
# Build with: pyinstaller anydoc2md.spec --clean --noconfirm

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

_IS_WINDOWS = sys.platform.startswith("win")
_IS_MACOS = sys.platform == "darwin"

# magika (markitdown's ML-based file-type sniffer) ships its ONNX model
# and config as package data, not Python code -- PyInstaller's import
# analysis won't find these on its own.
magika_datas = collect_data_files("magika")

vendor_datas = [
    ("vendor/tesseract", "vendor/tesseract"),
    ("vendor/poppler", "vendor/poppler"),
]

# The GPL requires the license text to travel with the binary, and MIT
# requires its notice to be retained -- so LICENSE, the notices, and every
# copyleft license text ship inside the bundle itself, not just in the repo.
license_datas = [
    ("licenses", "licenses"),
    ("LICENSE", "."),
    ("THIRD_PARTY_NOTICES.md", "."),
]

# Windows wants a .ico; macOS wants a .icns (generated in CI from the PNG);
# Linux ignores the EXE icon. Pass an icon only when one exists for the
# host so a missing file never fails the build.
if _IS_WINDOWS:
    _icon = "assets/icon.ico"
elif _IS_MACOS:
    _icon = "assets/icon.icns" if os.path.exists("assets/icon.icns") else None
else:
    _icon = None

a = Analysis(
    ["build_entry.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets", "assets"),
        *license_datas,
        *vendor_datas,
        *magika_datas,
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnyDoc2MD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # deliberately skipped -- see README's Security/packaging notes
    console=False,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AnyDoc2MD",
)

# On macOS, wrap the onedir output into a proper .app bundle so it launches
# from Finder and carries its own icon and metadata.
if _IS_MACOS:
    app = BUNDLE(
        coll,
        name="AnyDoc2MD.app",
        icon=_icon,
        bundle_identifier="io.github.mohamed_syed.anydoc2md",
        info_plist={
            "CFBundleName": "AnyDoc2MD",
            "CFBundleDisplayName": "AnyDoc2MD",
            "CFBundleShortVersionString": "1.1.0",
            "NSHighResolutionCapable": True,
            # Tkinter needs a real windowserver session; not a background agent.
            "LSBackgroundOnly": False,
        },
    )
