import os
import re


def clean_str(value):
    # Some .msg sources leave stray NUL/control bytes baked into stored
    # property strings (subject, attachment filenames, etc.) that survive
    # extract_msg's own parsing. Strip them outright: a literal "_" in
    # their place would be misleading, and an actual NUL/control char
    # corrupts filenames (e.g. turns ".pdf" into ".pdf\x00", which
    # os.path.splitext no longer recognizes as ".pdf").
    if not value:
        return value
    return "".join(ch for ch in value if ch in "\r\n\t" or ord(ch) >= 32).strip()


def safe_filename(name):
    name = os.path.basename(clean_str(name) or "attachment")
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.rstrip(" .")
    return name or "attachment"


def html_to_text(html):
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text("\n")
    except Exception:
        return re.sub(r"<[^<]+?>", "", html)
