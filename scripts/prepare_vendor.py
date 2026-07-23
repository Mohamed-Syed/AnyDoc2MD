"""
Stages a trimmed copy of Tesseract OCR and Poppler into vendor/, for the
standalone build (see anydoc2md.spec). Runs on Windows, Linux, and macOS
and stages the right binaries -- plus, on Linux/macOS, the shared
libraries those binaries need -- for whichever platform it runs on.

Only files needed at runtime are copied: the two Poppler tools pdf2image
invokes (pdftoppm, pdftocairo), the Tesseract binary, the English + OSD
trained-data, and the binaries' own library dependencies. Training tools,
other language packs, and unrelated utilities are left out. See
THIRD_PARTY_NOTICES.md for what is bundled and under what license.

Prerequisites:
    Windows: winget install UB-Mannheim.TesseractOCR
             winget install oschwartz10612.Poppler
    Linux:   apt-get install tesseract-ocr tesseract-ocr-eng \
                             tesseract-ocr-osd poppler-utils
    macOS:   brew install tesseract poppler

Usage:
    python scripts/prepare_vendor.py
"""

import glob
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_IS_WINDOWS = sys.platform.startswith("win")
_IS_MACOS = sys.platform == "darwin"
_IS_LINUX = sys.platform.startswith("linux")


# --------------------------------------------------------------------------
# Windows: copy an explicit list of files from the winget install locations.
# (Unchanged from the original Windows-only script.)
# --------------------------------------------------------------------------

TESSERACT_SRC_WIN = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR")
POPPLER_SRC_GLOB_WIN = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\oschwartz10612.Poppler_*\poppler-*\Library\bin"
)

TESSERACT_FILES_WIN = [
    "libarchive-13.dll", "libb2-1.dll", "libbz2-1.dll", "libcrypto-3-x64.dll",
    "libdeflate.dll", "libexpat-1.dll", "libgcc_s_seh-1.dll", "libgif-7.dll",
    "libiconv-2.dll", "libjbig-0.dll", "libjpeg-8.dll", "libleptonica-6.dll",
    "liblerc.dll", "liblz4.dll", "liblzma-5.dll", "libopenjp2-7.dll",
    "libpng16-16.dll", "libsharpyuv-0.dll", "libstdc++-6.dll",
    "libtesseract-5.dll", "libtiff-6.dll", "libwebp-7.dll", "libwebpmux-3.dll",
    "libwinpthread-1.dll", "libzstd.dll", "tesseract.exe", "zlib1.dll",
]
TESSDATA_FILES = ["eng.traineddata", "osd.traineddata"]

POPPLER_FILES_WIN = [
    "cairo.dll", "deflate.dll", "fontconfig-1.dll", "freetype.dll", "jpeg8.dll",
    "lcms2.dll", "lerc.dll", "libcrypto-3-x64.dll", "libcurl.dll", "libexpat.dll",
    "liblzma.dll", "libpng16.dll", "libssh2.dll", "openjp2.dll",
    "pdftocairo.exe", "pdftoppm.exe", "pixman-1-0.dll", "poppler.dll",
    "tiff.dll", "zlib.dll", "zstd.dll",
]


def _stage_named(name, src_dir, files, dst_dir):
    """Copy an explicit list of files (Windows path)."""
    if not os.path.isdir(src_dir):
        sys.exit(f"ERROR: {name} not found at {src_dir}\nInstall it first (see the docstring).")

    os.makedirs(dst_dir, exist_ok=True)
    missing, total = [], 0
    for filename in files:
        src = os.path.join(src_dir, filename)
        if not os.path.exists(src):
            missing.append(filename)
            continue
        shutil.copy2(src, os.path.join(dst_dir, filename))
        total += os.path.getsize(src)

    if missing:
        print(f"WARNING: {name} is missing expected files (installed version may differ): {missing}")
    print(f"{name}: staged {len(files) - len(missing)} files, {total / 1024 / 1024:.1f} MB -> {dst_dir}")


def _prepare_windows(vendor_dir):
    _stage_named("Tesseract", TESSERACT_SRC_WIN, TESSERACT_FILES_WIN,
                 os.path.join(vendor_dir, "tesseract"))
    _stage_named("Tesseract tessdata", os.path.join(TESSERACT_SRC_WIN, "tessdata"),
                 TESSDATA_FILES, os.path.join(vendor_dir, "tesseract", "tessdata"))

    matches = glob.glob(POPPLER_SRC_GLOB_WIN)
    if not matches:
        sys.exit(f"ERROR: Poppler not found matching {POPPLER_SRC_GLOB_WIN}")
    _stage_named("Poppler", matches[0], POPPLER_FILES_WIN, os.path.join(vendor_dir, "poppler"))


# --------------------------------------------------------------------------
# Linux / macOS: copy each binary, then discover and copy the shared
# libraries it needs (recursively), skipping the OS's own core libraries.
# The binaries are launched as subprocesses at runtime, and config.py adds
# the vendored directories to LD_LIBRARY_PATH / DYLD_LIBRARY_PATH so they
# find these bundled libraries.
# --------------------------------------------------------------------------

# Core system libraries that must come from the host, not be bundled:
# bundling the C runtime / dynamic loader across machines is what breaks a
# "portable" build. These are matched as a prefix of the library basename.
_LINUX_SYSTEM_LIB_PREFIXES = (
    "libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so",
    "libresolv.so", "libutil.so", "ld-linux", "linux-vdso", "libgcc_s.so",
)


def _which_or_die(tool):
    path = shutil.which(tool)
    if not path:
        sys.exit(f"ERROR: '{tool}' not found on PATH. Install it first (see the docstring).")
    return os.path.realpath(path)


def _linux_lib_deps(binary):
    """Return the real paths of non-system shared libraries `binary` needs."""
    out = subprocess.run(["ldd", binary], capture_output=True, text=True, check=False).stdout
    deps = []
    for line in out.splitlines():
        line = line.strip()
        # ldd lines look like: "libfoo.so.1 => /path/to/libfoo.so.1 (0x...)"
        if "=>" not in line:
            continue
        rhs = line.split("=>", 1)[1].strip()
        if not rhs.startswith("/"):
            continue  # "not found" or a virtual entry
        lib_path = rhs.split(" (", 1)[0].strip()
        base = os.path.basename(lib_path)
        if any(base.startswith(p) for p in _LINUX_SYSTEM_LIB_PREFIXES):
            continue
        if os.path.exists(lib_path):
            deps.append(os.path.realpath(lib_path))
    return deps


def _collect_libs(binaries, deps_fn):
    """Transitively collect every non-system lib the binaries need."""
    seen, queue = {}, list(binaries)
    while queue:
        current = queue.pop()
        for dep in deps_fn(current):
            if dep not in seen:
                seen[dep] = True
                queue.append(dep)
    return list(seen)


def _stage_linux(name, binaries, dst_dir):
    """Copy binaries + their (transitive) non-system .so deps, flat, into dst_dir.

    The bundled binaries are launched as subprocesses and config.py puts
    dst_dir on LD_LIBRARY_PATH, so a flat directory of the binary next to
    its libraries is enough for the loader to resolve them.
    """
    os.makedirs(dst_dir, exist_ok=True)
    total = 0
    for b in binaries:
        dst = os.path.join(dst_dir, os.path.basename(b))
        shutil.copy2(b, dst)
        os.chmod(dst, 0o755)
        total += os.path.getsize(b)

    libs = _collect_libs(binaries, _linux_lib_deps)
    for lib in libs:
        dst = os.path.join(dst_dir, os.path.basename(lib))
        if not os.path.exists(dst):
            shutil.copy2(lib, dst)
            total += os.path.getsize(lib)

    print(f"{name}: staged {len(binaries)} binaries + {len(libs)} libraries, "
          f"{total / 1024 / 1024:.1f} MB -> {dst_dir}")


def _stage_macos(name, binaries, dst_dir):
    """Copy binaries, then let dylibbundler gather and relocate their dylibs.

    macOS binaries reference many libraries via ``@rpath`` (Homebrew's
    libpoppler among them), which neither an ``otool -L`` scan of absolute
    paths nor ``DYLD_LIBRARY_PATH`` resolves. dylibbundler follows those
    references, copies every dependency into ``<dst_dir>/libs``, and
    rewrites each install name to ``@executable_path/libs/...`` -- and since
    each binary is launched as its own subprocess, ``@executable_path`` is
    that binary's own directory, so the bundle is self-contained with no
    environment variables required.
    """
    os.makedirs(dst_dir, exist_ok=True)
    staged = []
    for b in binaries:
        dst = os.path.join(dst_dir, os.path.basename(b))
        shutil.copy2(b, dst)
        os.chmod(dst, 0o755)
        staged.append(dst)

    libs_dir = os.path.join(dst_dir, "libs")
    cmd = ["dylibbundler", "-of", "-cd", "-b", "-d", libs_dir, "-p", "@executable_path/libs/"]
    for s in staged:
        cmd += ["-x", s]
    # stdin=DEVNULL: dylibbundler prompts interactively for any dependency
    # it can't locate; in CI that would hang. Feeding EOF makes it fail
    # fast and surface the missing library instead.
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)

    n_libs = len(os.listdir(libs_dir)) if os.path.isdir(libs_dir) else 0
    print(f"{name}: staged {len(staged)} binaries + {n_libs} libraries (dylibbundler) -> {dst_dir}")


def _find_tessdata_dir():
    """Locate the system tessdata directory holding eng/osd trained data."""
    candidates = []
    prefix = os.environ.get("TESSDATA_PREFIX")
    if prefix:
        candidates.append(prefix)
    candidates += glob.glob("/usr/share/tesseract-ocr/*/tessdata")
    candidates += [
        "/usr/share/tessdata", "/usr/share/tesseract-ocr/tessdata",
        "/opt/homebrew/share/tessdata", "/usr/local/share/tessdata",
    ]
    for c in candidates:
        if c and os.path.exists(os.path.join(c, "eng.traineddata")):
            return c
    return None


def _stage_tessdata(vendor_dir):
    src = _find_tessdata_dir()
    if not src:
        sys.exit("ERROR: could not find a tessdata directory with eng.traineddata. "
                 "Install the English language pack (see the docstring).")
    dst_dir = os.path.join(vendor_dir, "tesseract", "tessdata")
    os.makedirs(dst_dir, exist_ok=True)
    staged = 0
    for fname in TESSDATA_FILES:
        s = os.path.join(src, fname)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(dst_dir, fname))
            staged += 1
        elif fname == "eng.traineddata":
            sys.exit(f"ERROR: {fname} not found in {src}")
    print(f"Tesseract tessdata: staged {staged} files from {src} -> {dst_dir}")


def _prepare_posix(vendor_dir):
    _stage = _stage_macos if _IS_MACOS else _stage_linux

    tesseract = _which_or_die("tesseract")
    _stage("Tesseract", [tesseract], os.path.join(vendor_dir, "tesseract"))
    _stage_tessdata(vendor_dir)

    pdftoppm = _which_or_die("pdftoppm")
    pdftocairo = _which_or_die("pdftocairo")
    _stage("Poppler", [pdftoppm, pdftocairo], os.path.join(vendor_dir, "poppler"))


def main():
    vendor_dir = os.path.join(PROJECT_ROOT, "vendor")
    if _IS_WINDOWS:
        _prepare_windows(vendor_dir)
    elif _IS_LINUX or _IS_MACOS:
        _prepare_posix(vendor_dir)
    else:
        sys.exit(f"ERROR: unsupported platform {sys.platform!r}")

    print("\nDone. Build the standalone bundle with:")
    print("    pyinstaller anydoc2md.spec --clean --noconfirm")


if __name__ == "__main__":
    main()
