import io
import os
import zipfile

import pytest

from anydoc2md.config import (
    MAX_ZIP_ENTRIES,
    MAX_ZIP_UNCOMPRESSED_BYTES,
    MAX_ZIP_NESTING_DEPTH,
)
from anydoc2md.safety import assert_zip_is_safe, UnsafeZipError


def write_zip(path, entries):
    """entries: list of (name, bytes)."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return str(path)


def zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


class TestBenignZips:
    def test_ordinary_zip_is_accepted(self, tmp_path):
        path = write_zip(tmp_path / "ok.zip", [("a.txt", b"hello"), ("b.txt", b"world")])
        assert_zip_is_safe(path)  # must not raise

    def test_empty_zip_is_accepted(self, tmp_path):
        assert_zip_is_safe(write_zip(tmp_path / "empty.zip", []))

    def test_non_zip_is_deferred_to_the_normal_converter(self, tmp_path):
        # Deliberately not our job to reject: let the real conversion path
        # produce its own, more accurate error.
        path = tmp_path / "notazip.zip"
        path.write_bytes(b"this is not a zip file")
        assert_zip_is_safe(str(path))


class TestDecompressionBombs:
    def test_oversized_declared_content_is_refused(self, tmp_path):
        # Highly compressible payload: tiny on disk, huge decompressed --
        # the classic ratio bomb.
        chunk = b"\0" * (16 * 1024 * 1024)
        count = (MAX_ZIP_UNCOMPRESSED_BYTES // len(chunk)) + 2
        path = write_zip(tmp_path / "bomb.zip", [(f"f{i}", chunk) for i in range(count)])
        with pytest.raises(UnsafeZipError, match="uncompressed"):
            assert_zip_is_safe(path)

    def test_too_many_entries_is_refused(self, tmp_path):
        path = write_zip(
            tmp_path / "many.zip",
            [(f"f{i}.txt", b"x") for i in range(MAX_ZIP_ENTRIES + 1)],
        )
        with pytest.raises(UnsafeZipError, match="entries"):
            assert_zip_is_safe(path)

    def test_entry_count_at_the_limit_is_still_allowed(self, tmp_path):
        path = write_zip(
            tmp_path / "atlimit.zip",
            [(f"f{i}.txt", b"x") for i in range(MAX_ZIP_ENTRIES)],
        )
        assert_zip_is_safe(path)

    def test_bomb_hidden_inside_a_nested_zip_is_refused(self, tmp_path):
        inner = zip_bytes([(f"f{i}.txt", b"x") for i in range(MAX_ZIP_ENTRIES + 1)])
        path = write_zip(tmp_path / "outer.zip", [("inner.zip", inner)])
        with pytest.raises(UnsafeZipError):
            assert_zip_is_safe(path)

    def test_nested_zip_that_is_not_really_a_zip_is_skipped(self, tmp_path):
        path = write_zip(tmp_path / "outer.zip", [("fake.zip", b"not a zip")])
        assert_zip_is_safe(path)

    def test_descends_far_enough_to_cover_the_declared_nesting_depth(self, tmp_path):
        payload = zip_bytes([(f"f{i}.txt", b"x") for i in range(MAX_ZIP_ENTRIES + 1)])
        for _ in range(MAX_ZIP_NESTING_DEPTH - 1):
            payload = zip_bytes([("nested.zip", payload)])
        path = write_zip(tmp_path / "deep.zip", [("nested.zip", payload)])
        with pytest.raises(UnsafeZipError):
            assert_zip_is_safe(path)


class TestMemorySafety:
    def test_bytes_read_do_not_scale_with_archive_size(self, tmp_path, monkeypatch):
        """The guard must inspect metadata, not buffer the untrusted file.

        Regression test: an earlier version called ``f.read()`` on the whole
        archive before any size check ran, so a multi-gigabyte input
        exhausted memory *before* the decompression-bomb guard could fire.

        This asserts the property that actually matters -- total bytes read
        stays flat as the archive grows -- rather than looking for a
        particular ``read()`` call shape.

        An earlier version of this test flagged any ``read(-1)`` as a slurp,
        which failed on Python 3.11 only: its ``zipfile._EndRecData`` seeks
        to the last 22 bytes and then calls ``fpin.read()`` with no size, so
        the call *looks* unbounded while returning 22 bytes (3.12+ passes an
        explicit size). Measured both ways, the guard reads 96 bytes from an
        8 MB archive on 3.11 and on 3.14 alike -- the call shape is a stdlib
        implementation detail, and this test should not care about it.
        """
        # Incompressible payload, so the archive on disk really is ~8 MB and
        # a naive whole-file read would show up plainly in the byte count.
        payload = os.urandom(8 * 1024 * 1024)
        path = write_zip(tmp_path / "big.zip", [("blob.bin", payload)])
        archive_size = os.path.getsize(path)
        assert archive_size > 4 * 1024 * 1024, "payload compressed unexpectedly well"

        real_io_open = io.open
        bytes_read = []

        def counting_open(file, mode="r", *args, **kwargs):
            handle = real_io_open(file, mode, *args, **kwargs)
            if str(file) == str(path) and "b" in mode:
                original_read = handle.read

                def read(size=-1):
                    data = original_read(size)
                    bytes_read.append(len(data))
                    return data

                handle.read = read
            return handle

        # zipfile calls io.open; patch builtins.open too in case that changes.
        monkeypatch.setattr(io, "open", counting_open)
        monkeypatch.setattr("builtins.open", counting_open)
        assert_zip_is_safe(path)

        total = sum(bytes_read)
        # Locating the EOCD costs at most ZIP_MAX_COMMENT (64 KB) and the
        # central directory for one entry is tiny. 1 MB is a generous
        # ceiling that still fails loudly on an 8 MB whole-file read.
        assert total < 1024 * 1024, (
            f"read {total:,} bytes from a {archive_size:,}-byte archive; "
            f"the guard should read only metadata"
        )
