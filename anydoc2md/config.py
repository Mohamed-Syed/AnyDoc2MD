import glob
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

    # winget installs Poppler into a version-stamped folder
    # (poppler-25.07.0, poppler-25.10.0, ...), so a hardcoded path breaks
    # on the next `winget upgrade`. Resolve the newest matching install at
    # import time instead, and fall back to the glob pattern itself so the
    # "not found" path in ocr.py behaves the same as before when nothing
    # matches.
    _POPPLER_GLOB = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        r"\oschwartz10612.Poppler_*\poppler-*\Library\bin"
    )
    _poppler_matches = sorted(glob.glob(_POPPLER_GLOB))
    POPPLER_BIN = _poppler_matches[-1] if _poppler_matches else _POPPLER_GLOB

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

# OCR rasterization caps. Rendering a PDF to images at 300 dpi is by far
# the most expensive thing this tool does, and both of its inputs are
# attacker-controlled in the email-attachment threat model: page *count*
# is unbounded in the format, and so is page *size* (a PDF may declare a
# MediaBox of 200x200 inches, which at 300 dpi is a 3.6-gigapixel bitmap).
# Without caps, a small crafted PDF exhausts memory long before any of the
# zip/nesting guards get a say.
MAX_OCR_PDF_PAGES = 200
# Pillow's own decompression-bomb ceiling, applied to both PDF page
# renders and image attachments. Pillow warns at its default
# (~179 megapixels) and errors at twice that; this pins an explicit,
# smaller limit so behaviour does not drift with the installed version.
# 80 MP still comfortably covers an A4 page at 600 dpi (~35 MP).
MAX_OCR_IMAGE_PIXELS = 80_000_000

# Per-email attachment caps. A single .eml is free to declare thousands of
# attachments; each one is written to disk and recursively converted.
MAX_EMAIL_ATTACHMENTS = 100
MAX_EMAIL_ATTACHMENT_TOTAL_BYTES = 300 * 1024 * 1024  # 300 MB

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
