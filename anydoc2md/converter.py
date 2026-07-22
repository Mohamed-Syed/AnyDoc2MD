import os
import threading

from markitdown import MarkItDown

from .config import IMAGE_EXTENSIONS, EMAIL_EXTENSIONS, ZIP_EXTENSIONS, MIN_TEXT_LENGTH_BEFORE_OCR
from .ocr import ocr_image_file, ocr_pdf
from .arabic import fix_arabic_text_order
from .email_convert import convert_email
from .safety import assert_zip_is_safe, UnsafeZipError

# MarkItDown() is not guaranteed thread-safe to share across worker threads,
# so each thread in the conversion pool gets its own lazily-built instance
# instead of paying construction cost per file.
_thread_local = threading.local()


def _get_markitdown():
    md = getattr(_thread_local, "md", None)
    if md is None:
        md = MarkItDown()
        _thread_local.md = md
    return md


def convert_one(src_path, use_ocr, _depth=0):
    ext = os.path.splitext(src_path)[1].lower()

    if ext in EMAIL_EXTENSIONS:
        return convert_email(
            src_path,
            lambda p: convert_one(p, use_ocr, _depth=_depth + 1),
            depth=_depth,
        )

    if ext in IMAGE_EXTENSIONS and use_ocr:
        text = ocr_image_file(src_path)
        if not text.strip():
            text = "(No text detected in this image.)"
        return text, "OCR"

    if ext in ZIP_EXTENSIONS:
        try:
            assert_zip_is_safe(src_path)
        except UnsafeZipError as e:
            return f"(Refused to convert this zip file: {e})", "refused (unsafe zip)"

    result = _get_markitdown().convert(src_path)
    text = result.text_content

    if ext == ".pdf":
        text = fix_arabic_text_order(text)

    if ext == ".pdf" and use_ocr and len(text.strip()) < MIN_TEXT_LENGTH_BEFORE_OCR:
        ocr_text = ocr_pdf(src_path)
        if ocr_text.strip():
            return ocr_text, "OCR (scanned PDF)"

    return text, "text extraction"
