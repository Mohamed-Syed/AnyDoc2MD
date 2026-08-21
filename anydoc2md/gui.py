import os
import subprocess
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext

from . import __version__
from .config import (
    FOLDER_SCAN_EXTENSIONS,
    SUPPORTED_TYPES,
    VISUAL_CONTEXT_BALANCED,
    VISUAL_CONTEXT_SCENE_BY_SCENE,
    VISUAL_CONTEXT_TRANSCRIPT_ONLY,
)
from .converter import convert_one
from .text_utils import describe_exception, redact_local_paths
from .video_download import download_metadata_path, download_video, parse_video_urls

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")
ICON_PNG_PATH = os.path.join(ASSETS_DIR, "icon.png")

_IS_WINDOWS = sys.platform.startswith("win")
_IS_MACOS = sys.platform == "darwin"

ACCENT = "#2563EB"
BG = "#F4F6FB"
VISUAL_CONTEXT_LABELS = {
    "Transcript only": VISUAL_CONTEXT_TRANSCRIPT_ONLY,
    "Balanced": VISUAL_CONTEXT_BALANCED,
    "Scene-by-scene": VISUAL_CONTEXT_SCENE_BY_SCENE,
}


class AnyDoc2MDApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AnyDoc2MD — Any Document to AI-Ready Markdown")
        self.root.geometry("940x700")
        self.root.minsize(780, 580)
        self.root.configure(bg=BG)
        self._set_icon()
        self._set_style()

        self.files = []
        self.output_dir = tk.StringVar(value="(same folder as each file)")
        self.output_dir_path = None
        self.use_browser_cookies = tk.BooleanVar(value=False)
        self.convert_to_md_from_url = tk.BooleanVar(value=True)
        self.visual_context_label = tk.StringVar(value="Balanced")
        self.use_ocr = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self._last_output_folder = None
        self._url_batch_running = False
        self._url_batch_urls = []
        self._url_batch_seen = set()
        self._url_batch_lock = threading.Lock()
        self._url_job_seq = 0

        self._build_menu()
        self._build_ui()

    def _set_icon(self):
        # iconbitmap(.ico) is the reliable path on Windows; on Linux/macOS
        # Tk's .ico support is absent or flaky, so use the PNG via
        # iconphoto there. Either failing is cosmetic and must never abort
        # startup.
        try:
            if _IS_WINDOWS:
                self.root.iconbitmap(default=ICON_PATH)
            else:
                self._icon_image = tk.PhotoImage(file=ICON_PNG_PATH)
                self.root.iconphoto(True, self._icon_image)
        except Exception:
            pass

    def _set_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=BG, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=BG, font=("Segoe UI", 15, "bold"), foreground="#1E293B")
        style.configure("Sub.TLabel", background=BG, font=("Segoe UI", 9), foreground="#64748B")
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure(
            "Accent.TButton", font=("Segoe UI", 10, "bold"), padding=8,
            background=ACCENT, foreground="white",
        )
        style.map("Accent.TButton", background=[("active", "#1D4ED8"), ("disabled", "#94A3B8")])
        # NOTE: font sizes here must be integers -- a fractional point size
        # (e.g. 9.5) silently breaks ttk Treeview row text rendering on this
        # Tk build: rows get valid geometry (bbox, height) but draw no text,
        # while the exact same fractional size works fine on every other
        # widget (headings, labels, buttons). Confirmed by bisecting style
        # calls one at a time against a real rendered screenshot.
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("TProgressbar", troughcolor="#E2E8F0", background=ACCENT)
        style.configure("Status.TLabel", background="#E2E8F0", foreground="#334155", padding=4)

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Add Files...", command=self.add_files)
        file_menu.add_command(label="Add Folder...", command=self.add_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Clear All", command=self.clear_all)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About AnyDoc2MD", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _show_about(self):
        messagebox.showinfo(
            "About AnyDoc2MD",
            "AnyDoc2MD v" + __version__ + "\n\n"
            "Converts PDFs, Office documents, images, videos, and emails "
            "(.eml/.msg, with attachments) into clean, AI-ready Markdown.\n\n"
            "Features: OCR fallback for scanned PDFs/images, recursive "
            "email-attachment conversion, local video digests, and an "
            "Arabic PDF text-order fix.",
        )

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(16, 14, 16, 4))
        header.pack(fill="x")
        ttk.Label(header, text="AnyDoc2MD", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header, text="Any document → clean Markdown, ready for humans or AI.",
            style="Sub.TLabel",
        ).pack(anchor="w")

        toolbar = ttk.Frame(self.root, padding=(16, 8))
        toolbar.pack(fill="x")
        self.add_files_btn = ttk.Button(toolbar, text="Add Files...", command=self.add_files)
        self.add_files_btn.pack(side="left", padx=(0, 6))
        self.add_folder_btn = ttk.Button(toolbar, text="Add Folder...", command=self.add_folder)
        self.add_folder_btn.pack(side="left", padx=6)
        self.remove_btn = ttk.Button(toolbar, text="Remove Selected", command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=6)
        self.clear_btn = ttk.Button(toolbar, text="Clear All", command=self.clear_all)
        self.clear_btn.pack(side="left", padx=6)
        self.open_folder_btn = ttk.Button(
            toolbar, text="Open Output Folder", command=self._open_output_folder, state="disabled"
        )
        self.open_folder_btn.pack(side="right")

        url_frame = ttk.Frame(self.root, padding=(16, 0, 16, 6))
        url_frame.pack(fill="x")
        ttk.Label(url_frame, text="Video URLs").pack(side="left", padx=(0, 8), anchor="n")
        self.video_url_text = scrolledtext.ScrolledText(
            url_frame,
            height=3,
            wrap="word",
            font=("Segoe UI", 9),
            relief="flat",
            borderwidth=1,
        )
        self.video_url_text.pack(side="left", fill="x", expand=True)
        self.video_url_text.bind("<Control-Return>", lambda _event: self.start_url_batch())
        self.download_url_btn = ttk.Button(
            url_frame, text="Process URLs", command=self.start_url_batch
        )
        self.download_url_btn.pack(side="left", padx=(8, 0))

        url_options_frame = ttk.Frame(self.root, padding=(96, 0, 16, 8))
        url_options_frame.pack(fill="x")
        self.convert_to_md_from_url_check = tk.Checkbutton(
            url_options_frame,
            text="Convert to .md file",
            variable=self.convert_to_md_from_url,
            background=BG,
            activebackground=BG,
            selectcolor=ACCENT,
            font=("Segoe UI", 9),
            relief="flat",
            highlightthickness=0,
        )
        self.convert_to_md_from_url_check.pack(side="left")
        self.browser_cookies_check = tk.Checkbutton(
            url_options_frame,
            text="Use browser cookies",
            variable=self.use_browser_cookies,
            background=BG,
            activebackground=BG,
            selectcolor=ACCENT,
            font=("Segoe UI", 9),
            relief="flat",
            highlightthickness=0,
        )
        self.browser_cookies_check.pack(side="left", padx=(10, 0))
        self._file_list_buttons = (
            self.add_files_btn,
            self.add_folder_btn,
            self.remove_btn,
            self.clear_btn,
            self.download_url_btn,
        )

        list_frame = ttk.Frame(self.root, padding=(16, 0))
        list_frame.pack(fill="both", expand=True)

        columns = ("type", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="tree headings", selectmode="extended")
        self.tree.heading("#0", text="File")
        self.tree.heading("type", text="Type")
        self.tree.heading("status", text="Status")
        self.tree.column("#0", width=460, anchor="w")
        self.tree.column("type", width=90, anchor="center")
        self.tree.column("status", width=180, anchor="w")
        self.tree.tag_configure("ok", foreground="#15803D")
        self.tree.tag_configure("failed", foreground="#B91C1C")
        self.tree.tag_configure("queued", foreground="#64748B")
        self.tree.tag_configure("running", foreground="#1D4ED8")

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        out_frame = ttk.Frame(self.root, padding=16)
        out_frame.pack(fill="x")
        ttk.Label(out_frame, text="Save to:").pack(side="left")
        ttk.Label(out_frame, textvariable=self.output_dir, width=45, relief="sunken", anchor="w").pack(
            side="left", padx=8, fill="x", expand=True
        )
        ttk.Button(out_frame, text="Choose Output Folder...", command=self.choose_output_folder).pack(
            side="left", padx=6
        )
        ttk.Button(out_frame, text="Reset (same folder)", command=self.reset_output_folder).pack(side="left")

        ocr_frame = ttk.Frame(self.root, padding=(16, 0))
        ocr_frame.pack(fill="x")
        # Plain tk.Checkbutton, not ttk: the clam theme's ttk Checkbutton
        # indicator doesn't respond to indicatorcolor styling on this Tk
        # build, so a checked box was visually indistinguishable from an
        # unchecked one. tk.Checkbutton's selectcolor always works.
        tk.Checkbutton(
            ocr_frame,
            text="Use OCR for images, scanned PDFs, video keyframes, and image attachments inside emails",
            variable=self.use_ocr,
            background=BG,
            activebackground=BG,
            selectcolor=ACCENT,
            font=("Segoe UI", 10),
            relief="flat",
            highlightthickness=0,
        ).pack(side="left")
        ttk.Label(ocr_frame, text="Visual context:").pack(side="left", padx=(18, 6))
        self.visual_context_combo = ttk.Combobox(
            ocr_frame,
            textvariable=self.visual_context_label,
            values=list(VISUAL_CONTEXT_LABELS),
            state="readonly",
            width=17,
        )
        self.visual_context_combo.pack(side="left")

        action_frame = ttk.Frame(self.root, padding=16)
        action_frame.pack(fill="x")
        self.convert_btn = ttk.Button(
            action_frame, text="Convert All to .md", command=self.start_conversion, style="Accent.TButton"
        )
        self.convert_btn.pack(side="left")
        self.progress = ttk.Progressbar(action_frame, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=12)

        log_frame = ttk.Frame(self.root, padding=(16, 0, 16, 8))
        log_frame.pack(fill="both", expand=True)
        ttk.Label(log_frame, text="Log:").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(
            log_frame, height=8, state="disabled", font=("Consolas", 9), relief="flat", borderwidth=1
        )
        self.log.tag_configure("ok", foreground="#15803D")
        self.log.tag_configure("failed", foreground="#B91C1C")
        self.log.tag_configure("info", foreground="#334155")
        self.log.pack(fill="both", expand=True)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        status_bar.pack(fill="x", side="bottom")

    def log_msg(self, msg, tag="info"):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_url_controls_state(self, state):
        self.video_url_text.configure(state=state)
        self.download_url_btn.configure(state=state)
        self.convert_to_md_from_url_check.configure(state=state)
        self.browser_cookies_check.configure(state=state)

    def _set_running_url_controls(self):
        self.video_url_text.configure(state="normal")
        self.download_url_btn.configure(state="normal", text="Add URLs")
        self.convert_to_md_from_url_check.configure(state="disabled")
        self.browser_cookies_check.configure(state="disabled")

    def _set_idle_url_controls(self):
        self.video_url_text.configure(state="normal")
        self.download_url_btn.configure(state="normal", text="Process URLs")
        self.convert_to_md_from_url_check.configure(state="normal")
        self.browser_cookies_check.configure(state="normal")

    def _selected_visual_context(self):
        return VISUAL_CONTEXT_LABELS.get(self.visual_context_label.get(), VISUAL_CONTEXT_BALANCED)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select files to convert", filetypes=SUPPORTED_TYPES)
        for p in paths:
            self._add_path(p)

    def start_url_batch(self):
        urls = parse_video_urls(self.video_url_text.get("1.0", "end"))
        if not urls:
            messagebox.showwarning("No URL", "Paste one or more video URLs first.")
            return

        if self._url_batch_running:
            jobs = self._make_url_jobs(urls)
            new_count, total = self._add_urls_to_running_batch(jobs)
            if new_count:
                self.video_url_text.delete("1.0", "end")
                self.status_var.set(f"Added {new_count} URL(s) to the running batch.")
                self.log_msg(f"Added {new_count} URL(s) to URL batch. Total queued: {total}.")
            else:
                self.status_var.set("Those URL(s) are already in the running batch.")
            return

        out_folder = self.output_dir_path
        if not out_folder:
            out_folder = filedialog.askdirectory(title="Choose where to save downloaded videos or Markdown")
            if not out_folder:
                return
            self.output_dir_path = out_folder
            self.output_dir.set(out_folder)

        jobs = self._make_url_jobs(urls)
        with self._url_batch_lock:
            self._url_batch_urls = list(jobs)
            self._url_batch_seen = {job["url"] for job in jobs}
            self._url_batch_running = True
        self.video_url_text.delete("1.0", "end")
        self._set_running_url_controls()
        self.progress.configure(maximum=100, value=0)
        self.status_var.set("Starting URL batch...")
        self.log_msg(
            f"Starting {len(urls)} video URL(s): "
            + ("creating Markdown only." if self.convert_to_md_from_url.get() else "downloading videos.")
        )
        use_browser_cookies = self.use_browser_cookies.get()
        convert_to_md = self.convert_to_md_from_url.get()
        use_ocr = self.use_ocr.get()
        visual_context = self._selected_visual_context()
        thread = threading.Thread(
            target=self._download_url_batch_worker,
            args=(out_folder, use_browser_cookies, convert_to_md, use_ocr, visual_context),
            daemon=True,
        )
        thread.start()

    def _make_url_jobs(self, urls):
        jobs = []
        for url in urls:
            if url in self._url_batch_seen:
                continue
            self._url_job_seq += 1
            iid = f"url-job-{self._url_job_seq}"
            job = {"iid": iid, "url": url}
            jobs.append(job)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                text=self._url_row_text(url),
                values=("URL", "Queued"),
                tags=("queued",),
            )
        return jobs

    def _url_row_text(self, url):
        return url if len(url) <= 95 else url[:92] + "..."

    def _add_urls_to_running_batch(self, jobs):
        with self._url_batch_lock:
            new_jobs = [job for job in jobs if job["url"] not in self._url_batch_seen]
            self._url_batch_urls.extend(new_jobs)
            self._url_batch_seen.update(job["url"] for job in new_jobs)
            return len(new_jobs), len(self._url_batch_urls)

    def _next_url_batch_item(self, index):
        with self._url_batch_lock:
            if index >= len(self._url_batch_urls):
                return None, len(self._url_batch_urls)
            return self._url_batch_urls[index], len(self._url_batch_urls)

    def _url_batch_total(self):
        with self._url_batch_lock:
            return max(len(self._url_batch_urls), 1)

    def _download_url_batch_worker(
        self,
        out_folder,
        use_browser_cookies,
        convert_to_md,
        use_ocr,
        visual_context,
    ):
        converted_count = 0
        downloaded_count = 0
        fail_count = 0
        index = 0
        while True:
            job, total = self._next_url_batch_item(index)
            if not job:
                break
            index += 1
            url = job["url"]
            iid = job["iid"]
            try:
                self.root.after(0, self._set_url_job_status, iid, "Downloading 0%", "running")
                self.root.after(0, self.status_var.set, f"Downloading URL {index}/{total}...")
                result = download_video(
                    url,
                    out_folder,
                    use_browser_cookies=use_browser_cookies,
                    progress_callback=lambda progress, i=index, row=iid: self._queue_url_download_progress(
                        progress,
                        i,
                        row,
                    ),
                )
                if convert_to_md:
                    self.root.after(0, self._set_url_job_status, iid, "Converting to .md", "running")
                    self.root.after(0, self.status_var.set, f"Converting URL {index}/{total} to .md...")
                    try:
                        out_path, method = self._convert_and_write(
                            result.path,
                            use_ocr,
                            out_folder,
                            visual_context,
                        )
                    except Exception as e:
                        fail_count += 1
                        self.root.after(
                            0,
                            self._on_url_batch_item_done,
                            {
                                "action": "conversion_failed",
                                "result": result,
                                "iid": iid,
                                "error": describe_exception(e),
                            },
                        )
                    else:
                        self._remove_download_work_file(result.path)
                        converted_count += 1
                        self.root.after(
                            0,
                            self._on_url_batch_item_done,
                            {
                                "action": "converted",
                                "result": result,
                                "iid": iid,
                                "out_path": out_path,
                                "method": method,
                            },
                        )
                else:
                    downloaded_count += 1
                    self.root.after(
                        0,
                        self._on_url_batch_item_done,
                        {"action": "downloaded", "result": result, "iid": iid},
                    )
            except Exception as e:
                fail_count += 1
                self.root.after(
                    0,
                    self._on_url_batch_item_done,
                    {
                        "action": "failed",
                        "iid": iid,
                        "url": url,
                        "error": describe_exception(e),
                    },
                )
        self.root.after(0, self._on_url_batch_done, converted_count, downloaded_count, fail_count)

    def _remove_download_work_file(self, video_path):
        for path in (download_metadata_path(video_path), video_path):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass

    def _queue_url_download_progress(self, progress, index, iid):
        self.root.after(0, self._on_url_download_progress, progress, index, iid)

    def _on_url_download_progress(self, progress, index, iid):
        total = self._url_batch_total()
        percent = progress.get("percent")
        if percent is None:
            self._set_url_job_status(iid, "Downloading", "running")
            self.status_var.set(f"Downloading URL {index}/{total}...")
            return
        overall = ((index - 1) + (percent / 100)) / max(total, 1) * 100
        size = self._format_download_size(progress.get("downloaded_bytes"), progress.get("total_bytes"))
        self.progress.configure(value=overall)
        self._set_url_job_status(iid, f"Downloading {percent:.1f}%", "running")
        if size:
            self.status_var.set(f"Downloading URL {index}/{total}: {percent:.1f}% ({size})")
        else:
            self.status_var.set(f"Downloading URL {index}/{total}: {percent:.1f}%")

    def _format_download_size(self, downloaded, total):
        if downloaded is None or not total:
            return ""
        return f"{self._format_bytes(downloaded)} / {self._format_bytes(total)}"

    def _format_bytes(self, value):
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} GB"

    def _on_url_batch_item_done(self, event):
        action = event["action"]
        if action == "converted":
            result = event["result"]
            out_path = event["out_path"]
            self._last_output_folder = os.path.dirname(out_path)
            self.open_folder_btn.configure(state="normal")
            self._finish_url_job_row(event["iid"], result.title, "MD", f"Converted ({event['method']})", "ok")
            self.log_msg(
                f"[OK, {event['method']}] {result.title} -> {redact_local_paths(out_path)}",
                "ok",
            )
        elif action == "downloaded":
            result = event["result"]
            self._finish_url_job_row(event["iid"], result.title, "VIDEO", "Downloaded", "ok")
            self._add_path(result.path)
            self._last_output_folder = os.path.dirname(result.path)
            self.open_folder_btn.configure(state="normal")
            self.log_msg(
                f"[OK, downloaded] {result.title} -> {redact_local_paths(result.path)}",
                "ok",
            )
            self.tree.see(result.path)
        elif action == "conversion_failed":
            result = event["result"]
            self._finish_url_job_row(event["iid"], result.title, "VIDEO", "Conversion failed", "failed")
            self._add_path(result.path)
            self._last_output_folder = os.path.dirname(result.path)
            self.open_folder_btn.configure(state="normal")
            self.log_msg(
                f"[FAILED conversion, video kept] {result.title} -> {event['error']}",
                "failed",
            )
            self.tree.see(result.path)
        else:
            self._set_url_job_status(event["iid"], "Download failed", "failed")
            self.log_msg(f"[FAILED download] {event['url']} -> {event['error']}", "failed")

    def _set_url_job_status(self, iid, status, tag):
        if not self.tree.exists(iid):
            return
        values = self.tree.item(iid, "values")
        kind = values[0] if values else "URL"
        self.tree.item(iid, values=(kind, status), tags=(tag,))
        self.tree.see(iid)

    def _finish_url_job_row(self, iid, title, kind, status, tag):
        if not self.tree.exists(iid):
            return
        self.tree.item(iid, text=title or self.tree.item(iid, "text"), values=(kind, status), tags=(tag,))
        self.tree.see(iid)

    def _on_url_batch_done(self, converted_count, downloaded_count, fail_count):
        with self._url_batch_lock:
            self._url_batch_running = False
            self._url_batch_urls = []
            self._url_batch_seen = set()
        self._set_idle_url_controls()
        done_count = converted_count + downloaded_count + fail_count
        self.progress.configure(value=100 if done_count else 0)
        if fail_count == 0:
            self.video_url_text.delete("1.0", "end")
        self.status_var.set(
            f"URL batch done — {converted_count} converted, {downloaded_count} downloaded, {fail_count} failed."
        )
        self.log_msg(
            f"URL batch done. {converted_count} converted, {downloaded_count} downloaded, {fail_count} failed.",
            "info",
        )

    def add_folder(self):
        folder = filedialog.askdirectory(title="Select a folder (all supported files inside will be added)")
        if not folder:
            return
        added = 0
        for root_dir, _, filenames in os.walk(folder):
            for name in filenames:
                ext = os.path.splitext(name)[1].lower()
                if ext in FOLDER_SCAN_EXTENSIONS:
                    full = os.path.join(root_dir, name)
                    if self._add_path(full):
                        added += 1
        self.log_msg(f"Added {added} file(s) from folder: {redact_local_paths(folder)}")

    def _add_path(self, path):
        if path in self.files:
            return False
        self.files.append(path)
        ext = os.path.splitext(path)[1].lstrip(".").upper()
        self.tree.insert("", "end", iid=path, text=os.path.basename(path), values=(ext, ""))
        return True

    def remove_selected(self):
        for iid in self.tree.selection():
            self.tree.delete(iid)
            if iid in self.files:
                self.files.remove(iid)

    def clear_all(self):
        self.tree.delete(*self.tree.get_children())
        self.files.clear()

    def choose_output_folder(self):
        folder = filedialog.askdirectory(title="Choose where to save the .md files")
        if folder:
            self.output_dir_path = folder
            self.output_dir.set(folder)

    def reset_output_folder(self):
        self.output_dir_path = None
        self.output_dir.set("(same folder as each file)")

    def _open_output_folder(self):
        folder = self._last_output_folder
        if not (folder and os.path.isdir(folder)):
            return
        # The argument is a directory this app just wrote to -- either one
        # the user picked in a folder dialog or the source file's own
        # parent. It is never derived from document content, and each
        # opener is handed an argument list (never a shell string), so
        # there is no injection surface. See SECURITY.md.
        try:
            if _IS_WINDOWS:
                os.startfile(folder)  # noqa: S606
            elif _IS_MACOS:
                subprocess.run(["open", folder], check=False)  # noqa: S603, S607
            else:
                subprocess.run(["xdg-open", folder], check=False)  # noqa: S603, S607
        except Exception:
            pass

    def start_conversion(self):
        if not self.files:
            messagebox.showwarning("No files", "Add some files or a folder first.")
            return
        self.convert_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        for btn in self._file_list_buttons:
            btn.configure(state="disabled")
        self._set_url_controls_state("disabled")
        self.progress.configure(maximum=len(self.files), value=0)
        for path in self.files:
            self.tree.item(path, values=(self.tree.item(path, "values")[0], "Queued"))
            self.tree.item(path, tags=("queued",))
        # Read Tk variables/attributes on the main thread and pass plain
        # values down. Worker threads must never touch a tk.Variable
        # directly -- Tcl/Tk is not safe to call into from arbitrary
        # threads, and doing so here reliably crashed under real
        # concurrent load ("main thread is not in main loop").
        use_ocr = self.use_ocr.get()
        visual_context = self._selected_visual_context()
        out_dir_override = self.output_dir_path
        thread = threading.Thread(
            target=self._convert_all,
            args=(use_ocr, out_dir_override, visual_context),
            daemon=True,
        )
        thread.start()

    def _convert_and_write(
        self,
        src_path,
        use_ocr,
        out_dir_override,
        visual_context=VISUAL_CONTEXT_BALANCED,
    ):
        base = os.path.splitext(os.path.basename(src_path))[0]
        out_folder = out_dir_override or os.path.dirname(src_path)
        out_path = os.path.join(out_folder, base + ".md")
        assets_dir = None
        if visual_context == VISUAL_CONTEXT_SCENE_BY_SCENE:
            assets_dir = os.path.join(out_folder, base + "_assets")
        text, method = convert_one(
            src_path,
            use_ocr,
            visual_context=visual_context,
            output_assets_dir=assets_dir,
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        return out_path, method

    def _on_file_done(self, src_path, ok, detail, out_path):
        # Logged paths are redacted to a bare filename: this log is shown
        # on screen and users routinely paste or screenshot it into bug
        # reports, so it must not carry the operator's username and folder
        # layout any more than the converted .md output does.
        if ok:
            self.tree.item(src_path, values=(self.tree.item(src_path, "values")[0], detail), tags=("ok",))
            self.log_msg(
                f"[OK, {detail}] {redact_local_paths(src_path)} -> {redact_local_paths(out_path)}", "ok"
            )
        else:
            self.tree.item(src_path, values=(self.tree.item(src_path, "values")[0], "Failed"), tags=("failed",))
            self.log_msg(f"[FAILED] {redact_local_paths(src_path)} -> {detail}", "failed")

    def _on_all_done(self, ok_count, fail_count):
        self.log_msg(f"Done. {ok_count} succeeded, {fail_count} failed.", "info")
        self.status_var.set(f"Done — {ok_count} succeeded, {fail_count} failed.")
        self.convert_btn.configure(state="normal")
        for btn in self._file_list_buttons:
            btn.configure(state="normal")
        self._set_url_controls_state("normal")
        if self._last_output_folder:
            self.open_folder_btn.configure(state="normal")
        messagebox.showinfo(
            "Conversion complete", f"{ok_count} succeeded, {fail_count} failed.\nSee log for details."
        )

    def _convert_all(self, use_ocr, out_dir_override, visual_context):
        files = list(self.files)
        total = len(files)
        ok_count = 0
        fail_count = 0
        completed = 0
        max_workers = min(8, max(2, os.cpu_count() or 4))
        last_out_folder = None

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_path = {
                pool.submit(self._convert_and_write, p, use_ocr, out_dir_override, visual_context): p
                for p in files
            }
            for future in as_completed(future_to_path):
                src_path = future_to_path[future]
                completed += 1
                try:
                    out_path, method = future.result()
                    ok_count += 1
                    last_out_folder = os.path.dirname(out_path)
                    self.root.after(0, self._on_file_done, src_path, True, method, out_path)
                except Exception as e:
                    fail_count += 1
                    # The full traceback goes to stderr for debugging (a
                    # no-op in the windowed .exe build, which has no
                    # console); the GUI log gets a redacted one-liner,
                    # since users routinely paste that log into bug
                    # reports and it must not carry local paths.
                    traceback.print_exc()
                    self.root.after(
                        0, self._on_file_done, src_path, False, describe_exception(e), None
                    )
                self.root.after(0, self.progress.configure, {"value": completed})
                self.root.after(0, self.status_var.set, f"Converting... {completed}/{total}")

        self._last_output_folder = last_out_folder
        self.root.after(0, self._on_all_done, ok_count, fail_count)
