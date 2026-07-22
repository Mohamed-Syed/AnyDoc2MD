import os

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from .config import TESSERACT_EXE, POPPLER_BIN

if os.path.exists(TESSERACT_EXE):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE


def ocr_image_file(path):
    return pytesseract.image_to_string(Image.open(path))


def ocr_pdf(path):
    kwargs = {}
    if os.path.exists(POPPLER_BIN):
        kwargs["poppler_path"] = POPPLER_BIN
    pages = convert_from_path(path, dpi=300, **kwargs)
    text_parts = []
    for page_num, page_image in enumerate(pages, start=1):
        text = pytesseract.image_to_string(page_image)
        text_parts.append(f"## Page {page_num}\n\n{text}")
    return "\n\n".join(text_parts)
