# PyInstaller spec for AnyDoc2MD -- builds a standalone, --onedir bundle
# (not --onefile: onefile re-extracts the whole payload to a temp folder
# on every launch, which is a real, repeated startup cost for a bundle
# this size; onedir launches instantly since nothing needs unpacking).
#
# Build with: pyinstaller anydoc2md.spec --clean --noconfirm

from PyInstaller.utils.hooks import collect_data_files

# magika (markitdown's ML-based file-type sniffer) ships its ONNX model
# and config as package data, not Python code -- PyInstaller's import
# analysis won't find these on its own.
magika_datas = collect_data_files("magika")

vendor_datas = [
    ("vendor/tesseract", "vendor/tesseract"),
    ("vendor/poppler", "vendor/poppler"),
]

a = Analysis(
    ["build_entry.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("assets", "assets"),
        # The GPL requires the license text to travel with the binary, and
        # MIT requires its notice to be retained -- so LICENSE, the notices,
        # and every copyleft license text ship inside the bundle itself, not
        # just in the repository.
        ("licenses", "licenses"),
        ("LICENSE", "."),
        ("THIRD_PARTY_NOTICES.md", "."),
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
    icon="assets/icon.ico",
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
