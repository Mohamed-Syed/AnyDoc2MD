import base64
import os


from anydoc2md.config import MAX_EMAIL_NESTING_DEPTH
from anydoc2md.converter import convert_one
from anydoc2md.email_convert import strip_quoted_reply


def build_eml(path, *, subject="Test subject", body="Hello there.", attachments=()):
    """Write a minimal multipart .eml. Binary mode matters: text mode on
    Windows would translate CRLF to CRCRLF and corrupt the MIME headers."""
    parts = [
        f"From: sender@example.com\r\nTo: recipient@example.com\r\n"
        f"Subject: {subject}\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="BOUND"\r\n\r\n'
        f"--BOUND\r\nContent-Type: text/plain\r\n\r\n{body}\r\n"
    ]
    for filename, content_type, data in attachments:
        parts.append(
            f"--BOUND\r\nContent-Type: {content_type}\r\n"
            f'Content-Disposition: attachment; filename="{filename}"\r\n'
            "Content-Transfer-Encoding: base64\r\n\r\n"
            + base64.b64encode(data).decode()
            + "\r\n"
        )
    parts.append("--BOUND--\r\n")
    path.write_bytes("".join(parts).encode("utf-8"))
    return str(path)


class TestStripQuotedReply:
    def test_original_message_marker_trims_the_trail(self):
        text = "My reply.\n\n-----Original Message-----\nFrom: old@example.com\nOld body."
        result = strip_quoted_reply(text)
        assert "My reply." in result
        assert "Old body." not in result
        assert "trimmed" in result

    def test_on_wrote_marker_trims_the_trail(self):
        text = "Thanks!\n\nOn Monday, Alex wrote:\n> earlier message\n"
        result = strip_quoted_reply(text)
        assert "Thanks!" in result
        assert "earlier message" not in result

    def test_body_without_a_quote_trail_is_unchanged(self):
        text = "Just a plain message with no quoted history."
        assert strip_quoted_reply(text) == text

    def test_a_body_that_is_entirely_quoted_is_not_emptied(self):
        # earliest == 0 must not produce an empty document.
        text = "-----Original Message-----\nFrom: old@example.com\n"
        assert strip_quoted_reply(text) == text


class TestEmailConversion:
    def test_headers_and_body_are_rendered(self, tmp_path):
        path = build_eml(tmp_path / "m.eml", subject="Quarterly report")
        text, method = convert_one(path, use_ocr=False)
        assert method == "email parsing"
        assert "# Quarterly report" in text
        assert "sender@example.com" in text
        assert "recipient@example.com" in text
        assert "Hello there." in text

    def test_attachment_is_converted_into_its_own_section(self, tmp_path):
        path = build_eml(
            tmp_path / "m.eml",
            attachments=[("notes.txt", "text/plain", b"attachment body text")],
        )
        text, _ = convert_one(path, use_ocr=False)
        assert "## Attachments" in text
        assert "notes.txt" in text
        assert "attachment body text" in text

    def test_missing_subject_gets_a_placeholder(self, tmp_path):
        path = tmp_path / "m.eml"
        path.write_bytes(b"From: sender@example.com\r\n\r\nbody\r\n")
        text, _ = convert_one(str(path), use_ocr=False)
        assert "(no subject)" in text


class TestErrorsDoNotLeakLocalPaths:
    def test_failed_attachment_message_has_no_filesystem_path(self, tmp_path):
        """Converted .md files get shared and fed to LLMs. A raw library
        exception quotes the temp path the attachment was extracted into,
        which carries the operator's username and folder layout."""
        path = build_eml(
            tmp_path / "m.eml",
            attachments=[("pic.png", "image/png", b"definitely not a png")],
        )
        text, _ = convert_one(path, use_ocr=True)

        assert "Could not convert this attachment" in text
        assert "pic.png" in text, "the filename itself is useful and should remain"
        assert "anydoc2md_email_" not in text
        assert os.path.expanduser("~") not in text
        assert ":\\" not in text and ":/" not in text


class TestNestingDepthCap:
    def test_cap_is_enforced_before_any_work_is_done(self, tmp_path):
        from anydoc2md.email_convert import convert_email

        path = build_eml(tmp_path / "m.eml")
        text, method = convert_email(
            path,
            lambda p: ("", "unused"),
            depth=MAX_EMAIL_NESTING_DEPTH,
        )
        assert "nesting too deep" in method
        assert str(MAX_EMAIL_NESTING_DEPTH) in text

    def test_just_below_the_cap_still_converts(self, tmp_path):
        from anydoc2md.email_convert import convert_email

        path = build_eml(tmp_path / "m.eml", subject="Still fine")
        text, method = convert_email(
            path,
            lambda p: ("", "unused"),
            depth=MAX_EMAIL_NESTING_DEPTH - 1,
        )
        assert method == "email parsing"
        assert "Still fine" in text


class TestAttachmentCaps:
    def test_attachment_count_is_bounded(self, tmp_path, monkeypatch):
        monkeypatch.setattr("anydoc2md.email_convert.MAX_EMAIL_ATTACHMENTS", 3)
        path = build_eml(
            tmp_path / "m.eml",
            attachments=[
                (f"f{i}.txt", "text/plain", f"body {i}".encode()) for i in range(10)
            ],
        )
        text, _ = convert_one(path, use_ocr=False)
        assert "### 3." in text
        assert "### 4." not in text

    def test_total_attachment_size_is_bounded(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "anydoc2md.email_convert.MAX_EMAIL_ATTACHMENT_TOTAL_BYTES", 100
        )
        path = build_eml(
            tmp_path / "m.eml",
            attachments=[
                ("small.txt", "text/plain", b"x" * 40),
                ("big.txt", "text/plain", b"y" * 500),
            ],
        )
        text, _ = convert_one(path, use_ocr=False)
        assert "small.txt" in text
        assert "big.txt" not in text
