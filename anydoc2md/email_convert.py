import os
import re
import shutil
import tempfile
from email import policy
from email.parser import BytesParser

import extract_msg

from .config import MAX_EMAIL_NESTING_DEPTH
from .text_utils import clean_str, safe_filename, html_to_text

# Patterns marking the start of a quoted reply/forward trail in an email
# body. Everything from the earliest match onward is trimmed to keep
# converted emails short (quoted history is usually redundant with an
# earlier message already in the same mailbox/thread).
QUOTE_MARKERS = [
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^On .{1,120}\bwrote:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^From:.+\n+Sent:.+\n+To:.+\n+Subject:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^_{10,}\s*$", re.MULTILINE),
]


def strip_quoted_reply(text):
    earliest = None
    for pattern in QUOTE_MARKERS:
        m = pattern.search(text)
        if m and (earliest is None or m.start() < earliest):
            earliest = m.start()
    if earliest is not None and earliest > 0:
        trimmed = text[:earliest].rstrip()
        return trimmed + "\n\n*(quoted reply/forward trail trimmed to save space)*"
    return text


def _parse_eml(path):
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part is not None:
        content = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            body_text = html_to_text(content)
        else:
            body_text = content
    else:
        body_text = ""

    attachments = []
    for part in msg.iter_attachments():
        filename = safe_filename(part.get_filename())
        try:
            if part.get_content_type() == "message/rfc822":
                # A forwarded email attached as its own message has no
                # encoded byte payload -- get_payload(decode=True) returns
                # None for this content type. Its payload is a list
                # containing one Message object; serialize that directly.
                nested = part.get_payload()
                data = nested[0].as_bytes() if nested else None
                if filename and not filename.lower().endswith((".eml", ".msg")):
                    filename += ".eml"
            else:
                data = part.get_payload(decode=True)
        except Exception:
            data = None
        if data:
            attachments.append((filename, data))

    return {
        "subject": clean_str(msg.get("subject", "")) or "(no subject)",
        "from": clean_str(msg.get("from", "")),
        "to": clean_str(msg.get("to", "")),
        "cc": clean_str(msg.get("cc", "")),
        "date": clean_str(msg.get("date", "")),
        "body": clean_str(body_text),
        "attachments": attachments,
    }


def _parse_msg(path, tmp_dir):
    m = extract_msg.Message(path)
    try:
        body_text = m.body or ""
        if not body_text.strip() and m.htmlBody:
            html = m.htmlBody
            if isinstance(html, bytes):
                html = html.decode("utf-8", errors="ignore")
            body_text = html_to_text(html)

        attachments = []
        for att in m.attachments:
            filename = safe_filename(
                getattr(att, "longFilename", None) or getattr(att, "shortFilename", None)
            )
            try:
                # save() returns (SaveType, path). extractEmbedded=True makes
                # a forwarded email save as a single .msg file (SaveType.FILE)
                # instead of expanding into a folder.
                save_type, saved_path = att.save(
                    customPath=tmp_dir, customFilename=filename, extractEmbedded=True
                )
                if saved_path and os.path.isfile(saved_path):
                    attachments.append((os.path.basename(saved_path), saved_path))
            except Exception:
                continue

        return {
            "subject": clean_str(m.subject) or "(no subject)",
            "from": clean_str(m.sender) or "",
            "to": clean_str(m.to) or "",
            "cc": clean_str(m.cc) or "",
            "date": clean_str(str(m.date)) if m.date else "",
            "body": clean_str(body_text),
            "attachments": attachments,
        }
    finally:
        m.close()


def convert_email(src_path, convert_one, depth=0):
    # convert_one(path) -> (text, method) is passed in rather than imported
    # directly, so attachments (including nested forwarded emails and
    # PDF/image attachments) recurse back through the full conversion
    # pipeline without this module importing converter.py (which imports
    # this module to dispatch .eml/.msg -- a direct import back here would
    # be circular).
    #
    # `depth` guards against a maliciously crafted email that forwards an
    # email that forwards an email... with no natural bound. converter.py
    # increments this each time it re-enters convert_email via a nested
    # attachment (see its `_depth` parameter).
    if depth >= MAX_EMAIL_NESTING_DEPTH:
        return (
            f"(Nested email attachment exceeded the maximum depth of "
            f"{MAX_EMAIL_NESTING_DEPTH} -- stopped here to avoid unbounded "
            f"processing of a deeply/maliciously nested file.)",
            f"skipped (nesting too deep)",
        )

    ext = os.path.splitext(src_path)[1].lower()
    tmp_dir = tempfile.mkdtemp(prefix="anydoc2md_email_")
    try:
        parsed = None
        if ext == ".msg":
            try:
                parsed = _parse_msg(src_path, tmp_dir)
            except extract_msg.exceptions.InvalidFileFormatError:
                # Some tools save a raw MIME (.eml-style) email with a .msg
                # extension instead of the real OLE2 binary format. Fall
                # back to parsing it as raw MIME rather than failing.
                parsed = None

        if parsed is None:
            parsed = _parse_eml(src_path)
            # Raw-MIME attachments arrive as bytes in memory; write them to
            # disk so they go through the same file-based conversion path
            # (convert_one) that every other supported type uses.
            written = []
            for filename, data in parsed["attachments"]:
                att_path = os.path.join(tmp_dir, filename)
                with open(att_path, "wb") as f:
                    f.write(data)
                written.append((filename, att_path))
            parsed["attachments"] = written

        body = strip_quoted_reply((parsed["body"] or "").strip())

        lines = [f"# {parsed['subject']}", "", f"**From:** {parsed['from']}  ", f"**To:** {parsed['to']}  "]
        if parsed["cc"]:
            lines.append(f"**Cc:** {parsed['cc']}  ")
        lines.append(f"**Date:** {parsed['date']}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(body if body else "(no body text)")

        if parsed["attachments"]:
            lines.append("")
            lines.append("## Attachments")
            for i, (filename, att_path) in enumerate(parsed["attachments"], start=1):
                try:
                    att_text, att_method = convert_one(att_path)
                except Exception as e:
                    att_text, att_method = f"(Could not convert this attachment: {e})", "failed"
                lines.append("")
                lines.append(f"### {i}. {filename} ({att_method})")
                lines.append("")
                lines.append(att_text)

        return "\n".join(lines), "email parsing"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
