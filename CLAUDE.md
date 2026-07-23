# AnyDoc2MD — orientation for Claude

Any-document-to-Markdown converter (PDF, Office, images, email) with a
Tkinter GUI, built for feeding clean, AI-ready output into LLM workflows.

**Read this file, then go to the right doc instead of re-deriving things:**

| Question | Answer lives in |
|---|---|
| Features, install, usage, architecture, known limitations | [`README.md`](README.md) |
| What's bundled in the standalone `.exe` and under what license | [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |
| How to report a vulnerability, and the threat model this tool defends | [`SECURITY.md`](SECURITY.md) |
| Release history | [`CHANGELOG.md`](CHANGELOG.md) |
| What actually changed and when | `git log` |

## Non-obvious things a fresh session would otherwise waste tokens rediscovering

- **`vendor/` is gitignored, not committed.** It holds a trimmed
  Tesseract OCR + Poppler build for the standalone `.exe`, regenerated
  via `python scripts/prepare_vendor.py` (requires the winget installs
  from README's Option B). Never try to commit it — it's ~150MB of
  third-party binaries, not source.
- **Rebuilding the `.exe`**: `pyinstaller anydoc2md.spec --clean
  --noconfirm`, output in `dist/AnyDoc2MD/`. It's `--onedir`, not
  `--onefile` (onefile re-extracts on every launch — real perf cost at
  this size). No UPX (antivirus false-positive risk). Zip
  `dist/AnyDoc2MD/` whole for a release asset.
- **Testing pattern used throughout this project**: don't try to
  automate the Tkinter GUI (proved fragile/unreliable when tried). The
  pure-logic modules are covered by `pytest` (`python -m pytest`); for
  anything end-to-end, call
  `anydoc2md.converter.convert_one(path, use_ocr)` directly against a
  real file — that's the actual conversion entrypoint the GUI calls too.
- **Office format support (`.docx`/`.pptx`/`.xlsx`/`.xls`) requires the
  markitdown extras** (`markitdown[docx,pptx,xlsx]` + `xlrd` — see
  `requirements.txt`). This was silently broken for a while because only
  `markitdown[pdf]` was ever installed; don't assume a supported
  extension actually works without testing it against a real file of
  that type.
- **Arabic PDF text-order fix (`anydoc2md/arabic.py`) is a targeted
  heuristic, not a general bidi algorithm.** It's verified correct for
  flowing paragraph text but known-unreliable for PDF table cells (a
  different glyph-clustering pattern) — see README's Known Limitations
  before "fixing" table-cell Arabic further without re-verifying against
  a real table-heavy PDF first.
- **Security posture matters here**: this tool's whole point is
  processing untrusted files (email attachments, downloaded zips). Any
  new file-format support or attachment-handling change should be
  checked against the threat model in `SECURITY.md` — decompression
  bombs, unbounded recursion, unbounded rasterization, path traversal,
  and argument injection — before considering it done.
- **Never put a raw local path or a raw exception string into converted
  output or the GUI log.** Converted `.md` files get shared and fed to
  LLMs; `redact_local_paths()` in `anydoc2md/text_utils.py` exists
  precisely to keep the operator's home directory and temp paths out of
  them. Route new user-facing error text through it.

## Contributing conventions

- Public-facing text (README, error messages, output Markdown) should
  never contain a personal name, employer, real customer document name,
  or local filesystem path. Use `example.com` addresses and generic
  filenames in samples and screenshots.
- Anything genuinely machine-local (dev journals, scratch notes, local
  agent preferences) belongs in a gitignored `*.local.md` /
  `.claude/settings.local.json`, not in a tracked file.
