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


# Windows treats these as device names in *any* directory, so opening
# "<tmpdir>/CON" talks to the console device instead of creating a file --
# with or without an extension ("CON.pdf" is still CON). An attachment
# named after one of these must be renamed before it touches the disk.
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Windows caps a single path component at 255 characters; a longer
# attachment filename makes open() fail outright. 120 is a deliberately
# conservative margin below that limit -- room is left for the destination
# directory and a distinguishing suffix a caller might add, without ever
# risking the actual 255-character wall.
_MAX_FILENAME_LENGTH = 120


def safe_filename(name):
    """Reduce an untrusted attachment filename to something safe to write.

    Defends against directory traversal (``../../evil``), drive-relative
    and UNC paths, Windows reserved device names, and over-long names.
    """
    name = os.path.basename(clean_str(name) or "attachment")
    # basename() only strips the separators of the *host* OS, so an
    # attachment crafted on the other platform still needs handling: do it
    # explicitly rather than relying on which OS we happen to run on.
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = "".join(ch for ch in name if ord(ch) >= 32)
    name = name.strip().rstrip(" .")

    if not name:
        return "attachment"

    stem, ext = os.path.splitext(name)
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"{stem}_file"

    if len(stem) + len(ext) > _MAX_FILENAME_LENGTH:
        ext = ext[:16]
        stem = stem[: max(1, _MAX_FILENAME_LENGTH - len(ext))]

    return (stem + ext).rstrip(" .") or "attachment"


# Absolute filesystem paths that appear in exception text. Converted .md
# files are routinely shared and fed to LLMs, so a raw exception string
# would publish the operator's username, home directory, and temp-folder
# layout to wherever that output ends up.
_PATH_PATTERNS = (
    # Windows drive-letter path, e.g. C:\Users\alice\AppData\Local\Temp\x
    re.compile(r"[A-Za-z]:[\\/](?:[^\\/\r\n\"']*[\\/])*"),
    # UNC share, e.g. \\fileserver\share\
    re.compile(r"\\\\[^\\/\r\n\"']+[\\/](?:[^\\/\r\n\"']*[\\/])*"),
    # POSIX absolute path under a directory that implies a real home/tmp
    # (root's home is /root, not /home/root -- CI runners and containers
    # commonly run as root, so it needs its own alternative here)
    re.compile(r"/(?:home|Users|root|tmp|var|private)/(?:[^/\r\n\"']*/)*"),
)


def redact_local_paths(text):
    """Strip directory components out of any absolute path in ``text``.

    The bare filename is kept because it is genuinely useful in an error
    message ("could not convert invoice.pdf"); everything to its left is
    machine-identifying and gets replaced with a marker.

    >>> redact_local_paths(r"cannot identify image file 'C:\\Users\\me\\t\\p.png'")
    "cannot identify image file '<path>/p.png'"
    """
    if not text:
        return text
    result = str(text)
    for pattern in _PATH_PATTERNS:
        result = pattern.sub("<path>/", result)
    return result


def describe_exception(exc):
    """Render an exception for user-facing output, without leaking paths.

    Used for text written into converted Markdown and into the GUI log.
    The exception type is included because the message alone is often
    uninformative (many libraries raise with an empty string).
    """
    message = redact_local_paths(str(exc)).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def html_to_text(html):
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text("\n")
    except Exception:
        return re.sub(r"<[^<]+?>", "", html)
