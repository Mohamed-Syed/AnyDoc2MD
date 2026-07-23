import io
import zipfile

from .config import (
    MAX_ZIP_UNCOMPRESSED_BYTES,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_NESTING_DEPTH,
)


class UnsafeZipError(Exception):
    """Raised when a .zip file looks like a decompression bomb."""


def _check_open_zip(zf, depth):
    # A zip's central directory records each entry's declared uncompressed
    # size, readable via ZipFile.infolist() without decompressing anything
    # -- this lets us bound total decompressed size and entry count before
    # MarkItDown's ZipConverter (which has no such limit) actually reads
    # and decompresses entries into memory.
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
            nested = _read_bounded(zf, info)
            try:
                nested_zf = zipfile.ZipFile(io.BytesIO(nested))
            except zipfile.BadZipFile:
                # A ".zip" entry that isn't actually a zip -- nothing to
                # descend into. The parent's size/count checks still applied.
                continue
            with nested_zf:
                _check_open_zip(nested_zf, depth + 1)


def _read_bounded(zf, info):
    """Decompress one entry, refusing to exceed the global size limit.

    Descending into a nested zip is the one place this module has to
    actually decompress attacker-controlled data. Streaming it with a hard
    ceiling -- rather than trusting the declared ``file_size`` and calling
    ``ZipFile.read()`` -- closes the gap where a deliberately understated
    header would otherwise let a nested bomb expand unbounded in memory.
    """
    limit = MAX_ZIP_UNCOMPRESSED_BYTES
    with zf.open(info) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise UnsafeZipError(
            f"nested zip entry {info.filename!r} expands past the safety "
            f"limit of {limit:,} bytes (its declared size understated what "
            f"the decompressor actually produced -- decompression bomb)."
        )
    return data


def assert_zip_is_safe(path):
    """Raise UnsafeZipError if ``path`` looks like a zip decompression bomb.

    Checked via central-directory metadata (and, for nested zips, by
    reading only the nested zip's own metadata) -- never by decompressing
    arbitrary file contents from an untrusted zip beyond the bounded read
    in ``_read_bounded``.

    All standard/known zip-bomb techniques (e.g. the classic "42.zip",
    ratio bombs, many-small-files bombs) report accurate metadata and are
    caught by the declared-size checks. A zip deliberately crafted so its
    declared size understates what actually comes out of the decompressor
    is caught one level down by the bounded read, which stops at the size
    limit instead of trusting the header.
    """
    try:
        # Opened by path, not by reading the file into memory first: a
        # multi-gigabyte input would otherwise be fully buffered *before*
        # any size check ran, which is the exact failure the guard exists
        # to prevent. ZipFile seeks to the central directory instead.
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        # Not a real zip (or corrupt) -- let the normal conversion path
        # surface its own error rather than us pre-emptively failing.
        return
    with zf:
        _check_open_zip(zf, depth=0)
