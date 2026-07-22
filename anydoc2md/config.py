import os
import sys

# When frozen by PyInstaller, sys._MEIPASS points at the directory holding
# bundled data -- the temp extraction folder in --onefile mode, or the
# folder next to the .exe in --onedir mode. Either way, our own bundled
# vendor/tesseract and vendor/poppler folders (added via the .spec file's
# `datas`) live there, and we use those instead of requiring a system
# install. Running from source (not frozen), fall back to a normal winget
# install location, matching prior behavior.
_FROZEN_BASE = getattr(sys, "_MEIPASS", None)

if _FROZEN_BASE:
    TESSERACT_EXE = os.path.join(_FROZEN_BASE, "vendor", "tesseract", "tesseract.exe")
    POPPLER_BIN = os.path.join(_FROZEN_BASE, "vendor", "poppler")
else:
    TESSERACT_EXE = os.path.expandvars(
        r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"
    )
    POPPLER_BIN = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin"
    )

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif"}
EMAIL_EXTENSIONS = {".eml", ".msg"}
ZIP_EXTENSIONS = {".zip"}

# Below this many characters, a PDF's normal text layer is treated as
# "essentially empty" (i.e. a scanned PDF), triggering OCR fallback.
MIN_TEXT_LENGTH_BEFORE_OCR = 20

# Security limits. This tool's whole purpose is processing files that may
# have arrived from an untrusted source (an email attachment, a downloaded
# zip) -- these caps bound the damage a maliciously crafted input can do.
#
# A forwarded-email-within-a-forwarded-email chain has no natural limit;
# without a cap, a crafted .msg/.eml could recurse until Python's call
# stack is exhausted, or simply do an unbounded amount of conversion work
# (OCR, PDF rendering, etc.) per level.
MAX_EMAIL_NESTING_DEPTH = 10

# MarkItDown's zip handling (`markitdown/converters/_zip_converter.py`)
# reads every entry's full decompressed content into memory with no size
# or entry-count limit, and recurses into nested zips the same way -- a
# classic decompression-bomb ("zip bomb") shape. These caps are checked
# against the zip's central-directory metadata (free to read, no
# decompression needed) before any entry is actually decompressed.
MAX_ZIP_UNCOMPRESSED_BYTES = 300 * 1024 * 1024  # 300 MB
MAX_ZIP_ENTRIES = 2000
MAX_ZIP_NESTING_DEPTH = 3

SUPPORTED_TYPES = [
    ("All supported files",
     "*.pdf *.docx *.pptx *.xlsx *.xls *.html *.htm *.csv *.json *.txt "
     "*.png *.jpg *.jpeg *.gif *.bmp *.mp3 *.wav *.zip *.eml *.msg"),
    ("PDF files", "*.pdf"),
    ("Word documents", "*.docx"),
    ("PowerPoint files", "*.pptx"),
    ("Excel files", "*.xlsx *.xls"),
    ("Email files", "*.eml *.msg"),
    ("Images", "*.png *.jpg *.jpeg *.gif *.bmp"),
    ("All files", "*.*"),
]

FOLDER_SCAN_EXTENSIONS = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".html", ".htm",
    ".csv", ".json", ".txt", ".png", ".jpg", ".jpeg", ".gif",
    ".bmp", ".mp3", ".wav", ".zip", ".eml", ".msg",
}
