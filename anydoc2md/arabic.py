import re
import unicodedata

# Arabic script letter/mark ranges (Arabic, Arabic Supplement, Arabic
# Extended-A, and the two Presentation-Forms blocks). The Arabic-Indic and
# Extended Arabic-Indic *digit* sub-ranges are deliberately excluded: PDF
# text extraction already recovers embedded numbers in correct left-to-right
# order, and sweeping them into the reversal below would scramble them
# (e.g. "152" -> "251").
_ARABIC_CHAR_RANGES = (
    "؀-ٟ٪-ۯۺ-ۿ"
    "ݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿"
)
_ARABIC_CONNECTORS = r"\s،؛؟"
ARABIC_RUN_RE = re.compile(
    f"[{_ARABIC_CHAR_RANGES}](?:[{_ARABIC_CHAR_RANGES}{_ARABIC_CONNECTORS}]*[{_ARABIC_CHAR_RANGES}])?"
)


def fix_arabic_text_order(text):
    # PDFs with Arabic content are frequently extracted in on-page visual
    # (right-to-left glyph) order rather than logical reading order, and
    # with letters in shaped presentation-form codepoints instead of their
    # base form. NFKC unshapes the letters back to base form; reversing
    # each matched run then restores correct word/letter order. Skip
    # entirely (and cheaply) when there's no Arabic at all, the common case.
    #
    # Known limitation: this assumes glyphs were extracted one at a time in
    # pure visual order, which holds for flowing paragraph text but not
    # reliably for PDF table cells (some PDFs cluster glyphs differently
    # there) -- see README's "Known limitations" section.
    if not text or not ARABIC_RUN_RE.search(text):
        return text
    text = unicodedata.normalize("NFKC", text)
    return ARABIC_RUN_RE.sub(lambda m: m.group(0)[::-1], text)
