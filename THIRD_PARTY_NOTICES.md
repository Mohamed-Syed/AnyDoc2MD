# Third-Party Notices

AnyDoc2MD itself is licensed under the MIT License (see [LICENSE](LICENSE)).

The standalone/frozen build (the packaged `.exe`) additionally bundles
compiled binaries from two third-party projects, trimmed to only the
files actually needed at runtime (see `anydoc2md.spec` and the build
notes in `README.md` for exactly what's included and why). Their
licenses apply to those binaries and are reproduced here in full.

## Tesseract OCR

- Project: https://github.com/tesseract-ocr/tesseract
- Version bundled: 5.4.0 (Windows build via the `UB-Mannheim.TesseractOCR`
  winget package)
- License: Apache License 2.0 -- full text in
  [`licenses/TESSERACT-LICENSE-Apache-2.0.txt`](licenses/TESSERACT-LICENSE-Apache-2.0.txt)

Only `tesseract.exe`, its runtime DLL dependencies (verified via PE
import-table analysis, not guesswork), and the English (`eng`) +
orientation/script-detection (`osd`) trained-data files are bundled.
Tesseract's training tools, other language packs, and documentation are
not included.

## Poppler

- Project: https://poppler.freedesktop.org/
- Version bundled: 25.07.0 (Windows build via the
  `oschwartz10612.Poppler` winget package)
- License: GNU General Public License, version 2 (or later) -- full text
  in [`licenses/POPPLER-LICENSE-GPL-2.0.txt`](licenses/POPPLER-LICENSE-GPL-2.0.txt)

Only `pdftoppm.exe`, `pdftocairo.exe` (the two tools `pdf2image` actually
invokes), and their verified runtime DLL dependencies are bundled.
Poppler's source is available from the project link above; this build
introduces no modifications to Poppler itself.

## Python dependencies

All other bundled Python packages (MarkItDown, Pillow, pytesseract,
pdf2image, extract-msg, beautifulsoup4, and their own dependencies) are
used under their respective licenses as declared on PyPI; none are
modified. See `requirements.txt` for the full list.
