# Third-Party Notices

AnyDoc2MD's **own source code** is licensed under the MIT License (see
[LICENSE](LICENSE)).

This file records the third-party components the project depends on, and
— importantly — the licensing consequences of **redistributing the
standalone `.exe`**, which bundles those components. Running from source
after `pip install -r requirements.txt` is unaffected by everything in
the "Standalone build" section: installing dependencies for your own use
is not distribution and triggers no obligations.

---

## ⚠️ Copyleft components in the standalone build

The prebuilt `.exe` is a **combined work**. Two of the components inside
it are under the GNU GPL, so the binary as a whole must be distributed
under the **GPL v3**, and its source must be made available. AnyDoc2MD's
own code remains MIT and can be reused under MIT independently of the
binary.

| Component | License | Full text | How it is combined |
|---|---|---|---|
| [`extract-msg`](https://github.com/TeamMsgExtractor/msg-extractor) | **GPL-3.0** | [`licenses/EXTRACT-MSG-LICENSE-GPL-3.0.txt`](licenses/EXTRACT-MSG-LICENSE-GPL-3.0.txt) | `import`ed into the same Python process (`anydoc2md/email_convert.py`) to parse Outlook `.msg` files |
| [`pcodedmp`](https://github.com/bontchev/pcodedmp) | **GPL-3.0** | [`licenses/PCODEDMP-LICENSE-GPL-3.0.txt`](licenses/PCODEDMP-LICENSE-GPL-3.0.txt) | Transitive: `extract-msg` → `RTFDE` → `oletools` → `pcodedmp` |
| [`RTFDE`](https://github.com/seamustuohy/RTFDE) | LGPL-3.0 | [`licenses/RTFDE-LICENSE-LGPL-3.0.txt`](licenses/RTFDE-LICENSE-LGPL-3.0.txt) | Transitive dependency of `extract-msg` |
| [Poppler](https://poppler.freedesktop.org/) | GPL-2.0-or-later | [`licenses/POPPLER-LICENSE-GPL-2.0.txt`](licenses/POPPLER-LICENSE-GPL-2.0.txt) | Separate `pdftoppm.exe` / `pdftocairo.exe` processes invoked by `pdf2image` — aggregation, not linking, but redistributed in the same archive |

Every license text above ships **inside** the standalone build (in
`_internal/licenses/`), alongside AnyDoc2MD's own `LICENSE` and this
notices file, so a downloaded binary carries its licenses with it as the
GPL requires — not only the repository does.

### Written offer for source code

For any binary release of AnyDoc2MD, the complete corresponding source
code is available at
<https://github.com/Mohamed-Syed/AnyDoc2MD>, tagged with the matching
release version, together with the build scripts
(`anydoc2md.spec`, `scripts/prepare_vendor.py`) needed to reproduce it.

Source for the bundled third-party binaries is available from each
project at the links above. Poppler's Windows build is produced by the
[`oschwartz10612/poppler-windows`](https://github.com/oschwartz10612/poppler-windows)
project; the Tesseract Windows build by
[UB-Mannheim](https://github.com/UB-Mannheim/tesseract). Neither is
modified by this project. On request, the maintainer will provide the
corresponding source for the exact bundled versions for at least three
years from the date of distribution, per GPL-2.0 §3(b).

### Avoiding the copyleft obligation

`.msg` support is the only reason GPL code is present. A build without
`extract-msg` installed loses OLE2 `.msg` parsing (`.eml`, and `.msg`
files that are actually raw MIME, still work via the fallback path in
`email_convert.py`) and carries no copyleft obligation. Everything else
in the dependency tree is permissively licensed.

---

## Bundled binaries

The standalone build bundles compiled binaries from two projects,
trimmed to only the files actually needed at runtime (see
`anydoc2md.spec` and `scripts/prepare_vendor.py` for exactly what is
included).

### Tesseract OCR

- Project: <https://github.com/tesseract-ocr/tesseract>
- Version bundled: 5.4.0 (Windows build via the `UB-Mannheim.TesseractOCR`
  winget package)
- License: Apache License 2.0 — full text in
  [`licenses/TESSERACT-LICENSE-Apache-2.0.txt`](licenses/TESSERACT-LICENSE-Apache-2.0.txt)

Only `tesseract.exe`, its runtime DLL dependencies (verified via PE
import-table analysis, not guesswork), and the English (`eng`) +
orientation/script-detection (`osd`) trained-data files are bundled.
Tesseract's training tools, other language packs, and documentation are
not included. Tesseract is unmodified.

### Poppler

- Project: <https://poppler.freedesktop.org/>
- Version bundled: 25.07.0 (Windows build via the
  `oschwartz10612.Poppler` winget package)
- License: GNU General Public License, version 2 or later — full text in
  [`licenses/POPPLER-LICENSE-GPL-2.0.txt`](licenses/POPPLER-LICENSE-GPL-2.0.txt)

Only `pdftoppm.exe`, `pdftocairo.exe` (the two tools `pdf2image` actually
invokes), and their verified runtime DLL dependencies are bundled.
Poppler is unmodified; see the written offer above for source.

---

## Python dependencies

Direct dependencies and their licenses. Each is used unmodified, under
its own license; transitive dependencies are covered by the same terms
as declared on PyPI.

| Package | License |
|---|---|
| [`markitdown`](https://github.com/microsoft/markitdown) | MIT |
| [`beautifulsoup4`](https://www.crummy.com/software/BeautifulSoup/) | MIT |
| [`pdf2image`](https://github.com/Belval/pdf2image) | MIT |
| [`Pillow`](https://python-pillow.org/) | MIT-CMU |
| [`pytesseract`](https://github.com/madmaze/pytesseract) | Apache-2.0 |
| [`xlrd`](https://github.com/python-excel/xlrd) | BSD-3-Clause |
| [`extract-msg`](https://github.com/TeamMsgExtractor/msg-extractor) | **GPL-3.0** — see above |

To regenerate a complete, verified list of every transitive dependency
and its license for a given build:

```powershell
pip install pip-licenses
pip-licenses --format=markdown --with-urls --with-license-file
```

## Trademarks

AnyDoc2MD is an independent, unofficial project. It is not affiliated
with, endorsed by, or sponsored by Microsoft, Google, the Tesseract
project, or the Poppler project. Product names are the trademarks of
their respective owners and are used only to identify the software
described here.
