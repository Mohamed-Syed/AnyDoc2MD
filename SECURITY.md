# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, not as a public GitHub issue.

Use GitHub's private vulnerability reporting for this repository:
**Security → Report a vulnerability**
(<https://github.com/Mohamed-Syed/AnyDoc2MD/security/advisories/new>).

Please include the affected version, the file type involved, and — if you
can share it — a minimal sample file that reproduces the issue. A sample
that is small and synthetic is far more useful than a real document;
**do not send real personal or confidential documents.**

Expect an initial acknowledgement within about 7 days. This is a
volunteer-maintained project, so please allow reasonable time for a fix
before disclosing publicly.

## Supported versions

Only the latest released version receives fixes.

| Version | Supported |
|---|---|
| 1.1.x | ✅ |
| < 1.1 | ❌ |

## Threat model

AnyDoc2MD exists to convert files that **come from somewhere else** —
email attachments, downloaded archives, scanned documents. Every input is
treated as attacker-controlled. The relevant risks and the controls that
bound them:

| Risk | Control | Where |
|---|---|---|
| Zip decompression bomb (ratio, many-files, nested) | Central-directory size/entry caps checked before decompressing; bounded read when descending into a nested zip | `safety.py`, `MAX_ZIP_*` in `config.py` |
| Unbounded recursion via forwarded-email chains | Nesting depth cap | `email_convert.py`, `MAX_EMAIL_NESTING_DEPTH` |
| Unbounded work via mass attachments | Attachment count and aggregate-size caps | `email_convert.py`, `MAX_EMAIL_ATTACHMENT*` |
| Unbounded rasterization (PDF with huge or numerous pages) | Page cap plus an explicit Pillow pixel ceiling before rendering | `ocr.py`, `MAX_OCR_PDF_PAGES`, `MAX_OCR_IMAGE_PIXELS` |
| Path traversal via attachment filenames | Filenames flattened to a basename, illegal characters replaced, Windows device names renamed, length capped | `text_utils.safe_filename` |
| Argument injection into OCR/PDF tooling | No `shell=True` anywhere; this project makes no subprocess calls of its own, and every path handed to `pytesseract`/`pdf2image` is an absolute path it constructed | `ocr.py` |
| Leaking the operator's local paths into shared output | Exception text is redacted before it reaches converted Markdown or the GUI log | `text_utils.redact_local_paths` |

Each control has regression tests in `tests/`.

### Out of scope

- **Vulnerabilities in upstream dependencies** (MarkItDown, Pillow,
  Poppler, Tesseract, extract-msg). Report those to the relevant project;
  we will pick up the fixed version. Do open an issue here if AnyDoc2MD
  pins a version known to be vulnerable.
- **Conversion accuracy.** Wrong or garbled output is a bug, not a
  security issue — please file it as a normal issue.
- **The content of converted documents.** AnyDoc2MD faithfully reproduces
  what a document contains, including anything sensitive in it. Deciding
  where converted `.md` output goes is the operator's responsibility.

### Known residual limitations

- The zip guard descends at most `MAX_ZIP_NESTING_DEPTH` (3) levels. The
  size and entry-count checks still apply at every level reached, so a
  bomb has to be *both* deeper than three levels *and* individually
  benign at each level above it.
- The Arabic text-order fix is a targeted heuristic; it can misorder
  table-cell text. This is a correctness limitation, not a security one.

## Privacy

AnyDoc2MD runs entirely locally. Its own code makes **no network
requests** — it imports no HTTP, socket, or telemetry library — and it
writes nothing outside the output folder you choose and a temporary
directory (deleted after each email is processed). OCR and PDF rendering
are performed by the bundled Tesseract and Poppler binaries on your
machine; no document content leaves it.
