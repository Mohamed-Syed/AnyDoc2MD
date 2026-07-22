import io
import zipfile

from .config import (
    MAX_ZIP_UNCOMPRESSED_BYTES,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_NESTING_DEPTH,
)


class UnsafeZipError(Exception):
    """Raised when a .zip file looks like a decompression bomb."""


def _check_zip_bytes(data, depth):
    # A zip's central directory records each entry's declared uncompressed
    # size, readable via ZipFile.infolist() without decompressing anything
    # -- this lets us bound total decompressed size and entry count before
    # MarkItDown's ZipConverter (which has no such limit) actually reads
    # and decompresses entries into memory.
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        # Not a real zip (or corrupt) -- let the normal conversion path
        # surface its own error rather than us pre-emptively failing.
        return

    infos = zf.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        raise UnsafeZipError(
            f"zip contains {len(infos)} entries, exceeding the safety limit "
            f"of {MAX_ZIP_ENTRIES} (possible decompression-bomb pattern: "
            f"many small files)."
        )

    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
        raise UnsafeZipError(
            f"zip claims {total_uncompressed:,} bytes uncompressed, exceeding "
            f"the safety limit of {MAX_ZIP_UNCOMPRESSED_BYTES:,} bytes "
            f"(possible decompression bomb)."
        )

    if depth >= MAX_ZIP_NESTING_DEPTH:
        # Stop descending into nested zips; the declared-size checks above
        # already ran for this level, which is what a bomb hiding a few
        # levels deep would otherwise need to evade one level at a time.
        return

    for info in infos:
        if info.filename.lower().endswith(".zip"):
            _check_zip_bytes(zf.read(info), depth + 1)


def assert_zip_is_safe(path):
    """Raise UnsafeZipError if `path` looks like a zip decompression bomb.

    Checked via central-directory metadata (and, for nested zips, by
    reading only the nested zip's own metadata) -- never by decompressing
    arbitrary file contents from an untrusted zip.

    Known residual limitation: this trusts each entry's declared
    `file_size` field to decide whether it's safe to decompress one level
    further. All standard/known zip-bomb techniques (e.g. the classic
    "42.zip", ratio bombs, many-small-files bombs) report accurate
    metadata and are caught by this check. A zip deliberately crafted so
    its declared size understates what actually comes out of the
    decompressor (an obscure, purpose-built technique, not a standard
    zip-bomb generator) could in principle still evade the nested-descent
    step. Defeating that fully would require bounding bytes during
    decompression itself rather than trusting header metadata -- out of
    scope for this check.
    """
    with open(path, "rb") as f:
        _check_zip_bytes(f.read(), depth=0)
