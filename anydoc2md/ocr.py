import os

from .config import (
    TESSERACT_EXE,
    POPPLER_BIN,
    MAX_OCR_PDF_PAGES,
    MAX_OCR_IMAGE_PIXELS,
)

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


def _apply_pixel_limit():
    # Pillow's decompression-bomb guard: it raises DecompressionBombError
    # past 2x MAX_IMAGE_PIXELS and only warns at 1x, and the default
    # depends on the installed Pillow version. Pin it explicitly so an
    # image attachment declaring absurd dimensions fails fast and loudly
    # instead of trying to allocate the bitmap.
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_OCR_IMAGE_PIXELS
    return Image


def ocr_image_file(path):
    Image = _apply_pixel_limit()
    pytesseract = _pytesseract()
    # Context-managed: without it the decoder keeps the file handle open,
    # and on Windows that blocks deletion of the temp directory an email
    # attachment was extracted into.
    with Image.open(path) as image:
        return pytesseract.image_to_string(image)


def ocr_pdf(path):
    from pdf2image import convert_from_path, pdfinfo_from_path
    _apply_pixel_limit()
    pytesseract = _pytesseract()

    kwargs = {}
    if os.path.exists(POPPLER_BIN):
        kwargs["poppler_path"] = POPPLER_BIN

    # Ask Poppler for the page count before rendering anything. A PDF's
    # page count is unbounded, and each page costs a full 300-dpi raster;
    # rendering is by far the most expensive operation here, so cap it
    # rather than letting a crafted attachment dictate the workload.
    truncated = False
    try:
        page_count = int(pdfinfo_from_path(path, **kwargs)["Pages"])
    except Exception:
        # Older poppler builds and odd PDFs can fail pdfinfo while still
        # rendering fine. Fall back to bounding the render directly.
        page_count = None

    render_kwargs = dict(kwargs)
    if page_count is None or page_count > MAX_OCR_PDF_PAGES:
        render_kwargs["last_page"] = MAX_OCR_PDF_PAGES
        truncated = page_count is None or page_count > MAX_OCR_PDF_PAGES

    pages = convert_from_path(path, dpi=300, **render_kwargs)
    if truncated and len(pages) < MAX_OCR_PDF_PAGES:
        # pdfinfo was unavailable and the document turned out to be short
        # after all -- nothing was actually cut off.
        truncated = False

    text_parts = []
    for page_num, page_image in enumerate(pages, start=1):
        try:
            text_parts.append(
                f"## Page {page_num}\n\n{pytesseract.image_to_string(page_image)}"
            )
        finally:
            page_image.close()

    if truncated:
        text_parts.append(
            f"*(OCR stopped after the first {MAX_OCR_PDF_PAGES} pages -- "
            f"this document is longer. Raise MAX_OCR_PDF_PAGES in "
            f"anydoc2md/config.py to process more.)*"
        )

    return "\n\n".join(text_parts)
