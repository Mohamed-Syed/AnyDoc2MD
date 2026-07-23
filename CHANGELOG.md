# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-07-23

Hardening and repository-hygiene release ahead of public distribution.
No changes to the conversion pipeline's normal-path behaviour.

### Security

- **Converted output no longer leaks local filesystem paths.** When an
  email attachment failed to convert, the raw library exception — which
  routinely quotes the temporary path the attachment was extracted into,
  and therefore the operator's username and folder layout — was embedded
  verbatim in the generated `.md`. Exception text shown to the user is
  now routed through `redact_local_paths()`, which keeps the useful
  filename and drops every directory component. The same applies to the
  GUI log, which users paste into bug reports.
- **The zip decompression-bomb guard no longer buffers the whole
  archive.** `assert_zip_is_safe()` read the entire untrusted file into
  memory before any size check ran, so a multi-gigabyte input exhausted
  memory before the guard could fire. It now opens the archive by path
  and reads only central-directory metadata.
- **Nested zips are read with a hard ceiling** instead of trusting the
  declared `file_size`, closing the documented gap where a deliberately
  understated header let a nested bomb expand unbounded.
- **OCR rasterization is now bounded** (`MAX_OCR_PDF_PAGES`,
  `MAX_OCR_IMAGE_PIXELS`). A PDF may declare unlimited pages and
  arbitrarily large page dimensions; at 300 dpi a single crafted page
  could request a multi-gigapixel bitmap. Page count is checked before
  rendering, and Pillow's decompression-bomb ceiling is pinned explicitly
  rather than left to vary with the installed version.
- **Per-email attachment caps** (`MAX_EMAIL_ATTACHMENTS`,
  `MAX_EMAIL_ATTACHMENT_TOTAL_BYTES`) bound the work a single crafted
  `.eml` can demand.
- **`safe_filename()` hardened**: Windows reserved device names
  (`CON`, `NUL`, `COM1`…) are renamed rather than opened as devices,
  over-long names are truncated below the 255-character path-component
  limit, and separators from the *other* platform are stripped rather
  than relying on the host `os.path.basename`.

### Added

- `SECURITY.md` with a private vulnerability-reporting channel, the
  project's threat model, and its known residual limitations.
- A `pytest` suite (`tests/`) covering every security control, the
  Arabic reordering heuristic, email parsing, and conversion dispatch.
- GitHub Actions CI running the suite on Windows and Linux.
- `pyproject.toml` with packaging metadata and tool configuration.
- `CHANGELOG.md` and `.gitattributes`.

### Fixed

- **Poppler's path is no longer version-pinned.** `config.py` hardcoded
  `poppler-25.07.0`, so any `winget upgrade` silently broke the OCR
  fallback for source installs. The newest matching install is now
  resolved at import time. (Previously listed under Known Limitations.)
- `Image.open()` is context-managed, so the decoder no longer holds a
  file handle that blocks deletion of an email's temporary directory on
  Windows.

### Changed

- `CLAUDE.md` now covers project orientation only; machine-specific
  notes belong in `*.local.md`, excluded by convention.
- `.gitignore` covers credentials (`.env`, key/certificate files),
  tooling caches, editor directories, and build output.
- The packaging CI job verifies the sdist against an allowlist of
  expected paths, so anything unexpected fails the build.

## [1.0.0] - 2026-07-22

Initial release.

### Added

- Batch Tkinter GUI converting PDF, DOCX, PPTX, XLSX/XLS, HTML, CSV,
  JSON, TXT, images, MP3/WAV, ZIP, and email (`.eml`/`.msg`) to Markdown.
- OCR fallback via Tesseract for scanned PDFs and image files.
- Recursive conversion of email attachments, including forwarded emails
  attached as their own `.msg`/`.eml`.
- Arabic PDF text-order fix for flowing paragraph text.
- Parallel batch conversion on a bounded thread pool.
- Zip decompression-bomb guard and email nesting-depth cap.
- Standalone PyInstaller build bundling trimmed Tesseract and Poppler
  binaries, with third-party license notices.

[1.1.0]: https://github.com/Mohamed-Syed/AnyDoc2MD/releases/tag/v1.1.0
[1.0.0]: https://github.com/Mohamed-Syed/AnyDoc2MD/releases/tag/v1.0.0
