"""
Stages a trimmed copy of Tesseract OCR and Poppler into vendor/, for the
standalone .exe build (see anydoc2md.spec).

Only files verified (via PE import-table analysis, not guesswork) to be
required at runtime are copied -- training tools, other language packs,
and unrelated CLI utilities are left out. See THIRD_PARTY_NOTICES.md for
what's bundled and under what license.

Prerequisites (install via winget first):
    winget install UB-Mannheim.TesseractOCR
    winget install oschwartz10612.Poppler

Usage:
    python scripts/prepare_vendor.py
"""

import glob
import os
import shutil
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TESSERACT_SRC = os.path.expandvars(
    r"%LOCALAPPDATA%\Programs\Tesseract-OCR"
)
POPPLER_SRC_GLOB = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_*\poppler-*\Library\bin"
)

TESSERACT_FILES = [
    "libarchive-13.dll", "libb2-1.dll", "libbz2-1.dll", "libcrypto-3-x64.dll",
    "libdeflate.dll", "libexpat-1.dll", "libgcc_s_seh-1.dll", "libgif-7.dll",
    "libiconv-2.dll", "libjbig-0.dll", "libjpeg-8.dll", "libleptonica-6.dll",
    "liblerc.dll", "liblz4.dll", "liblzma-5.dll", "libopenjp2-7.dll",
    "libpng16-16.dll", "libsharpyuv-0.dll", "libstdc++-6.dll",
    "libtesseract-5.dll", "libtiff-6.dll", "libwebp-7.dll", "libwebpmux-3.dll",
    "libwinpthread-1.dll", "libzstd.dll", "tesseract.exe", "zlib1.dll",
]
TESSDATA_FILES = ["eng.traineddata", "osd.traineddata"]

POPPLER_FILES = [
    "cairo.dll", "deflate.dll", "fontconfig-1.dll", "freetype.dll", "jpeg8.dll",
    "lcms2.dll", "lerc.dll", "libcrypto-3-x64.dll", "libcurl.dll", "libexpat.dll",
    "liblzma.dll", "libpng16.dll", "libssh2.dll", "openjp2.dll",
    "pdftocairo.exe", "pdftoppm.exe", "pixman-1-0.dll", "poppler.dll",
    "tiff.dll", "zlib.dll", "zstd.dll",
]


def stage(name, src_dir, files, dst_dir):
    if not os.path.isdir(src_dir):
        print(f"ERROR: {name} not found at {src_dir}")
        print("Install it first (see the docstring at the top of this script).")
        sys.exit(1)

    os.makedirs(dst_dir, exist_ok=True)
    missing = []
    total = 0
    for filename in files:
        src = os.path.join(src_dir, filename)
        dst = os.path.join(dst_dir, filename)
        if not os.path.exists(src):
            missing.append(filename)
            continue
        shutil.copy2(src, dst)
        total += os.path.getsize(dst)

    if missing:
        print(f"WARNING: {name} is missing expected files (installed version may differ): {missing}")

    print(f"{name}: staged {len(files) - len(missing)} files, {total / 1024 / 1024:.1f} MB -> {dst_dir}")


def main():
    vendor_dir = os.path.join(PROJECT_ROOT, "vendor")

    stage(
        "Tesseract",
        TESSERACT_SRC,
        TESSERACT_FILES,
        os.path.join(vendor_dir, "tesseract"),
    )
    stage(
        "Tesseract tessdata",
        os.path.join(TESSERACT_SRC, "tessdata"),
        TESSDATA_FILES,
        os.path.join(vendor_dir, "tesseract", "tessdata"),
    )

    poppler_matches = glob.glob(POPPLER_SRC_GLOB)
    if not poppler_matches:
        print(f"ERROR: Poppler not found matching {POPPLER_SRC_GLOB}")
        print("Install it first: winget install oschwartz10612.Poppler")
        sys.exit(1)
    stage(
        "Poppler",
        poppler_matches[0],
        POPPLER_FILES,
        os.path.join(vendor_dir, "poppler"),
    )

    print("\nDone. Build the .exe with:")
    print("    pyinstaller anydoc2md.spec --clean --noconfirm")


if __name__ == "__main__":
    main()
