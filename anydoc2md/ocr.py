import os

from .config import TESSERACT_EXE, POPPLER_BIN

# pytesseract/pdf2image/PIL are only imported when OCR is actually
# invoked, not at module load time -- these are the heaviest pure-Python
# dependencies in the app (PIL alone is substantial), and most
# conversions (plain PDFs/Office docs/HTML) never touch OCR at all. This
# keeps startup fast for the common case, which matters more once the app
# is a frozen standalone .exe than it did as a plain script.
_tesseract_cmd_set = False


def _pytesseract():
    global _tesseract_cmd_set
    import pytesseract
    if not _tesseract_cmd_set:
        if os.path.exists(TESSERACT_EXE):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE
        _tesseract_cmd_set = True
    return pytesseract


def ocr_image_file(path):
    from PIL import Image
    pytesseract = _pytesseract()
    return pytesseract.image_to_string(Image.open(path))


def ocr_pdf(path):
    from pdf2image import convert_from_path
    pytesseract = _pytesseract()
    kwargs = {}
    if os.path.exists(POPPLER_BIN):
        kwargs["poppler_path"] = POPPLER_BIN
    pages = convert_from_path(path, dpi=300, **kwargs)
    text_parts = []
    for page_num, page_image in enumerate(pages, start=1):
        text = pytesseract.image_to_string(page_image)
        text_parts.append(f"## Page {page_num}\n\n{text}")
    return "\n\n".join(text_parts)
