import pytest

from anydoc2md.text_utils import (
    clean_str,
    safe_filename,
    redact_local_paths,
    describe_exception,
    html_to_text,
)


class TestCleanStr:
    def test_strips_nul_and_control_bytes(self):
        # Real .msg files carry NULs baked into stored property strings;
        # a surviving NUL turns ".pdf" into something splitext won't match.
        assert clean_str("report.pdf\x00") == "report.pdf"
        assert clean_str("a\x01b\x02c") == "abc"

    def test_preserves_meaningful_whitespace(self):
        assert clean_str("line1\nline2\tend") == "line1\nline2\tend"

    @pytest.mark.parametrize("value", ["", None])
    def test_passes_through_falsy(self, value):
        assert clean_str(value) == value


class TestSafeFilename:
    @pytest.mark.parametrize(
        "attack",
        [
            "../../evil.pdf",
            "..\\..\\evil.pdf",
            "/etc/passwd/../evil.pdf",
            "C:\\Windows\\System32\\evil.pdf",
            "\\\\server\\share\\evil.pdf",
        ],
    )
    def test_directory_traversal_is_flattened(self, attack):
        result = safe_filename(attack)
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result

    @pytest.mark.parametrize(
        "reserved", ["CON", "con.txt", "NUL", "PRN", "AUX", "COM1.pdf", "lpt9.docx"]
    )
    def test_windows_reserved_device_names_are_renamed(self, reserved):
        # On Windows these resolve to devices in *any* directory, so
        # open()ing them writes to the console/printer instead of a file.
        import os

        stem = os.path.splitext(safe_filename(reserved))[0]
        assert stem.upper() not in {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }

    def test_reserved_name_keeps_its_extension(self):
        # The extension drives conversion routing, so it must survive.
        assert safe_filename("CON.pdf").endswith(".pdf")

    def test_overlong_name_is_truncated_but_keeps_extension(self):
        result = safe_filename("a" * 300 + ".pdf")
        assert len(result) <= 255  # Windows path-component limit
        assert result.endswith(".pdf")

    @pytest.mark.parametrize("empty", ["", None, "...", "   ", "/", "\\"])
    def test_degenerate_names_get_a_fallback(self, empty):
        assert safe_filename(empty) == "attachment"

    def test_illegal_characters_are_replaced(self):
        assert safe_filename('a<b>c:d"e|f?g*h.pdf') == "a_b_c_d_e_f_g_h.pdf"

    def test_ordinary_name_is_left_alone(self):
        assert safe_filename("Quarterly Report 2026.pdf") == "Quarterly Report 2026.pdf"


class TestRedactLocalPaths:
    @pytest.mark.parametrize(
        "text",
        [
            r"cannot identify image file 'C:\Users\alice\AppData\Local\Temp\x\p.png'",
            r"[Errno 2] No such file: 'C:/Users/alice/Documents/p.png'",
            r"failed on \\fileserver\share\team\p.png",
            "failed on /home/alice/tmp/p.png",
            "failed on /Users/alice/Documents/p.png",
        ],
    )
    def test_directory_components_are_removed(self, text):
        result = redact_local_paths(text)
        assert "alice" not in result
        assert "fileserver" not in result
        assert "<path>/" in result

    def test_basename_is_preserved_because_it_is_useful(self):
        result = redact_local_paths(r"cannot open 'C:\Users\alice\invoice.pdf'")
        assert "invoice.pdf" in result

    def test_text_without_paths_is_untouched(self):
        assert redact_local_paths("conversion failed") == "conversion failed"

    @pytest.mark.parametrize("value", ["", None])
    def test_passes_through_falsy(self, value):
        assert redact_local_paths(value) == value


class TestDescribeException:
    def test_includes_type_and_redacted_message(self):
        exc = ValueError(r"bad file C:\Users\alice\secret\x.pdf")
        result = describe_exception(exc)
        assert result.startswith("ValueError:")
        assert "alice" not in result
        assert "x.pdf" in result

    def test_falls_back_to_type_when_message_is_empty(self):
        assert describe_exception(RuntimeError()) == "RuntimeError"


class TestHtmlToText:
    def test_extracts_visible_text(self):
        assert "Hello" in html_to_text("<p>Hello</p>")

    def test_does_not_raise_on_malformed_markup(self):
        assert isinstance(html_to_text("<p>unclosed <b>bold"), str)
