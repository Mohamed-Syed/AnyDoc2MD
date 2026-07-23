from anydoc2md.arabic import fix_arabic_text_order


class TestNonArabicIsUntouched:
    def test_plain_english_passes_through_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert fix_arabic_text_order(text) == text

    def test_markdown_structure_survives(self):
        text = "# Heading\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
        assert fix_arabic_text_order(text) == text

    def test_empty_input(self):
        assert fix_arabic_text_order("") == ""


class TestArabicReordering:
    def test_visual_order_run_is_reversed(self):
        # PDFs commonly emit Arabic in on-page visual order; reversing the
        # run restores logical reading order.
        assert fix_arabic_text_order("ملس") == "سلم"

    def test_presentation_forms_are_unshaped(self):
        # U+FEDF is the initial presentation form of LAM (U+0644); NFKC
        # normalization maps it back to the base letter.
        result = fix_arabic_text_order("ﻟ")
        assert result == "ل"

    def test_is_an_involution_on_a_single_run(self):
        once = fix_arabic_text_order("مرحبا")
        assert fix_arabic_text_order(once) == "مرحبا"


class TestDigitsAreNotScrambled:
    def test_western_digits_keep_their_order(self):
        # Regression guard: digits must stay left-to-right. Sweeping them
        # into the reversal would turn "152" into "251".
        assert "152" in fix_arabic_text_order("ملس 152")

    def test_arabic_indic_digits_keep_their_order(self):
        # U+0661 U+0665 U+0662 == Arabic-Indic 1 5 2, deliberately excluded
        # from the reversal ranges.
        text = "ملس ١٥٢"
        assert "١٥٢" in fix_arabic_text_order(text)


class TestMixedContent:
    def test_english_words_in_an_arabic_document_are_preserved(self):
        result = fix_arabic_text_order("ملس Invoice 2026")
        assert "Invoice" in result
        assert "2026" in result
