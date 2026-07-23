import zipfile


from anydoc2md.config import MAX_ZIP_ENTRIES
from anydoc2md.converter import convert_one


class TestDispatch:
    def test_plain_text_file(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("Hello from a text file.", encoding="utf-8")
        text, method = convert_one(str(path), use_ocr=False)
        assert "Hello from a text file." in text
        assert method == "text extraction"

    def test_csv_file(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("name,amount\nwidget,42\n", encoding="utf-8")
        text, _ = convert_one(str(path), use_ocr=False)
        assert "widget" in text

    def test_html_file(self, tmp_path):
        path = tmp_path / "page.html"
        path.write_text("<html><body><h1>Title</h1></body></html>", encoding="utf-8")
        text, _ = convert_one(str(path), use_ocr=False)
        assert "Title" in text

    def test_extension_matching_is_case_insensitive(self, tmp_path):
        path = tmp_path / "SHOUTY.TXT"
        path.write_text("mixed case extension", encoding="utf-8")
        text, _ = convert_one(str(path), use_ocr=False)
        assert "mixed case extension" in text


class TestZipHandling:
    def test_benign_zip_is_converted(self, tmp_path):
        path = tmp_path / "ok.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("inside.txt", "contents of the zipped file")
        text, method = convert_one(str(path), use_ocr=False)
        assert method == "text extraction"
        assert "contents of the zipped file" in text

    def test_unsafe_zip_is_refused_without_being_decompressed(self, tmp_path):
        path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(MAX_ZIP_ENTRIES + 1):
                zf.writestr(f"f{i}.txt", "x")
        text, method = convert_one(str(path), use_ocr=False)
        assert method == "refused (unsafe zip)"
        assert "Refused to convert this zip file" in text

    def test_refusal_message_carries_no_local_path(self, tmp_path):
        path = tmp_path / "bomb.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for i in range(MAX_ZIP_ENTRIES + 1):
                zf.writestr(f"f{i}.txt", "x")
        text, _ = convert_one(str(path), use_ocr=False)
        assert str(tmp_path) not in text


class TestImageDispatch:
    def test_ocr_is_skipped_when_disabled(self, tmp_path, monkeypatch):
        # With use_ocr=False an image must not reach the OCR path at all.
        called = []
        monkeypatch.setattr(
            "anydoc2md.converter.ocr_image_file",
            lambda p: called.append(p) or "",
        )
        path = tmp_path / "pic.png"
        path.write_bytes(b"not a real png")
        try:
            convert_one(str(path), use_ocr=False)
        except Exception:
            pass  # markitdown may reject it; the point is OCR was not used
        assert not called

    def test_image_with_no_detected_text_says_so(self, tmp_path, monkeypatch):
        monkeypatch.setattr("anydoc2md.converter.ocr_image_file", lambda p: "   ")
        path = tmp_path / "blank.png"
        path.write_bytes(b"stub")
        text, method = convert_one(str(path), use_ocr=True)
        assert method == "OCR"
        assert "No text detected" in text
