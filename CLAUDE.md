# AnyDoc2MD — orientation for Claude

Any-document-to-Markdown converter (PDF, Office, images, email) with a
Tkinter GUI, built for feeding clean, AI-ready output into LLM workflows.
Repo: https://github.com/Mohamed-Syed/AnyDoc2MD (public, MIT).

**Read this file, then go to the right doc instead of re-deriving things:**

| Question | Answer lives in |
|---|---|
| Features, install, usage, architecture, known limitations | [`README.md`](README.md) |
| What's bundled in the standalone `.exe` and under what license | [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |
| Full narrative history of *why* things are the way they are (every bug found, every test run, every design tradeoff) | [`SESSION_SUMMARY.md`](SESSION_SUMMARY.md) — **local-only, gitignored, never publish or reference its contents in anything user-facing** (real personal filenames/company names throughout) |
| What actually changed and when | `git log` |

## Non-obvious things a fresh session would otherwise waste tokens rediscovering

- **Git identity**: commits must use `maintainer@example.com` or the GitHub
  noreply address (`154465537+Mohamed-Syed@users.noreply.github.com`) —
  **never** the work email (`@example.com`). Windows
  auto-populates git identity from the machine's org account; check
  `git log -1 --format="%ae"` before committing if unsure.
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
  automate the Tkinter GUI (proved fragile/unreliable when tried). Test
  by calling `anydoc2md.converter.convert_one(path, use_ocr)` directly
  against real files — that's the actual conversion entrypoint the GUI
  calls too, and every fix in this project was verified that way. For
  testing the frozen `.exe` specifically, `build_entry.py` supports a
  temporary env-var-triggered self-test hook (`ANYDOC2MD_SELFTEST=1`) —
  see git history for the exact pattern if this needs reviving; it's not
  left in `build_entry.py` permanently.
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
  checked against: decompression bombs, unbounded recursion, path
  traversal, and argument injection (see README's Security section and
  `anydoc2md/safety.py`) before considering it done.

## Quick start for a fresh session

```powershell
cd path/to/AnyDoc2MD
git log --oneline          # see what's changed since this file was written
git status                 # anything uncommitted?
```

Then read `README.md` for the current feature set before making changes.
