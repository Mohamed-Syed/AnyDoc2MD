# AnyDoc2MD

**Any document → clean Markdown, ready for humans or AI.**

A desktop GUI that batch-converts PDFs, Office documents, images, and emails
(`.eml` / `.msg`, attachments included) into Markdown — with OCR fallback for
scanned content, recursive conversion of email attachments (including
forwarded emails), and a fix for a common Arabic PDF text-extraction bug.

![AnyDoc2MD screenshot](assets/screenshot.png)

## Features

- **Broad format support**: PDF, DOCX, PPTX, XLSX/XLS, HTML, CSV, JSON, TXT,
  images (PNG/JPG/GIF/BMP/TIFF), MP3/WAV, ZIP, and email (`.eml`, `.msg`).
- **OCR fallback**: scanned PDFs and image files are OCR'd automatically via
  Tesseract when the normal text layer comes back empty or missing.
- **Emails, properly**: `.eml`/`.msg` files are parsed for their headers and
  body (HTML bodies are converted to text, quoted reply/forward trails are
  trimmed to save tokens), and every attachment — including a forwarded email
  attached as its own `.msg`/`.eml` — is recursively converted through the
  same pipeline and appended as its own section.
- **Arabic PDF text-order fix**: many PDFs extract Arabic text in on-page
  visual (reversed) order with shaped presentation-form glyphs instead of
  logical reading order. AnyDoc2MD detects and corrects this for flowing
  paragraph text (see [Known limitations](#known-limitations) for where it
  doesn't apply).
- **Parallel conversion**: batches convert several files concurrently
  instead of one at a time.
- **Batch GUI**: add files or whole folders, pick an output location (or
  keep each `.md` next to its source), watch per-file status and a live log,
  and open the output folder when done.

## Installation

### 1. System dependencies (Windows)

AnyDoc2MD needs two external tools on top of Python:

```powershell
winget install UB-Mannheim.TesseractOCR
winget install oschwartz10612.Poppler
```

- **Tesseract OCR** powers image/scanned-PDF text recognition.
- **Poppler** renders PDF pages to images for the OCR fallback path.

If either is installed somewhere other than the default winget location,
update the paths in [`anydoc2md/config.py`](anydoc2md/config.py)
(`TESSERACT_EXE`, `POPPLER_BIN`).

### 2. Python dependencies

```powershell
pip install -r requirements.txt
```

## Usage

```powershell
python -m anydoc2md
```

or double-click `run_anydoc2md.bat` for a no-console launch.

1. **Add Files...** or **Add Folder...** to queue up documents.
2. Optionally choose an output folder (defaults to saving each `.md` next
   to its source file).
3. Leave **Use OCR** checked to handle scanned PDFs and images.
4. Click **Convert All to .md** — status and a live log update per file as
   conversions complete.

## How it works

The package is organized by concern under `anydoc2md/`:

| Module | Responsibility |
|---|---|
| `converter.py` | Top-level dispatch: routes each file to the right conversion path by extension. |
| `email_convert.py` | Parses `.eml`/`.msg`, extracts attachments, recurses them back through `converter.py`. |
| `ocr.py` | Tesseract/Poppler-backed OCR for images and scanned PDFs. |
| `arabic.py` | The Arabic PDF text-order fix. |
| `text_utils.py` | Shared string-cleaning helpers (filename sanitizing, HTML-to-text, control-character stripping). |
| `safety.py` | Guards against maliciously crafted input (see [Security](#security) below). |
| `gui.py` | The Tkinter application. |

Batch conversion runs on a background thread with a `ThreadPoolExecutor`
pool (bounded to your CPU count, max 8) so multiple files convert at once;
each pool thread gets its own `MarkItDown` instance rather than sharing one
across threads.

## Security

This tool's entire purpose is processing files that may come from an
untrusted source — an email attachment, a downloaded zip — so it includes
guards against maliciously crafted input, not just malformed input:

- **Email nesting depth cap** (`MAX_EMAIL_NESTING_DEPTH`, default 10): a
  forwarded email containing a forwarded email containing a forwarded
  email... has no natural bound. Without a cap, a crafted `.msg`/`.eml`
  could force unbounded recursive processing. Past the cap, the
  conversion stops cleanly with a note in the output rather than
  recursing further.
- **Zip decompression-bomb guard** (`safety.py`): the `markitdown` library
  we build on decompresses every entry of a `.zip` with no size or
  entry-count limit, and recurses into nested zips the same way — a
  classic decompression-bomb shape. Before handing a `.zip` to
  `markitdown`, we check its central-directory metadata (total declared
  uncompressed size, entry count, and — recursively, up to a depth of 3 —
  the same for any zip nested inside it) and refuse to convert it if
  those exceed sane limits (300 MB uncompressed / 2,000 entries by
  default), without ever decompressing untrusted content to make that
  decision. This defeats all standard/known zip-bomb techniques; see the
  docstring on `assert_zip_is_safe` for the one narrow, documented edge
  case it doesn't cover.
- **Path traversal**: attachment filenames from parsed emails are passed
  through `os.path.basename()` before any filesystem use, so a
  crafted `../../` filename can't escape the temp directory it's
  extracted into.
- **No shell/subprocess injection risk**: this project makes no
  `subprocess`/shell calls of its own; the two dependencies that do
  (`pytesseract`, `pdf2image`) invoke Tesseract/Poppler with argument
  lists (never `shell=True`), and every path this project passes to them
  is always an absolute path built via `os.path.join`/`tempfile.mkdtemp`
  — never a bare, attacker-controlled string that could be misread as a
  command-line flag.

## Built on

Non-email/non-image document parsing is powered by Microsoft's
[MarkItDown](https://github.com/microsoft/markitdown) library. AnyDoc2MD is
an independent, unofficial GUI/pipeline built on top of it (and other
libraries listed in `requirements.txt`) — it is not affiliated with or
endorsed by Microsoft.

## Known limitations

- **Only English OCR** is installed by default. Add other Tesseract
  language packs (`tesseract-ocr-<lang>` via your package manager, or the
  relevant `.traineddata` file) for other languages.
- **Poppler's path is version-pinned** in `config.py` to the folder name at
  install time — a future `winget upgrade` may change that folder name and
  require updating the path.
- **The 20-character "is this PDF scanned" heuristic** can occasionally
  trigger OCR on a PDF with a real but very sparse text layer. Harmless,
  just slower.
- **No image preprocessing** (deskew, contrast enhancement) is applied
  before OCR, so quality depends on the source image/scan quality.
- **The Arabic text-order fix is a targeted heuristic, not a full Unicode
  Bidirectional Algorithm implementation.** It reliably fixes flowing
  paragraph text, but PDF **table cells** can cluster glyphs differently at
  the font/extraction level — confirmed on a real-world PDF where the same
  "reverse the run" logic that fixes paragraph text does not correctly
  reorder a table-cell label. The English content in the same table is
  unaffected; only Arabic *labels specifically inside PDF tables* should be
  treated with caution.
- **OneNote (`.one`) is not supported.** It's a proprietary binary format
  with no reliable open-source parser; export OneNote pages to PDF or Word
  first if you need to convert them.

## License

MIT — see [LICENSE](LICENSE).
