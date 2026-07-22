import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext

from . import __version__
from .config import SUPPORTED_TYPES, FOLDER_SCAN_EXTENSIONS
from .converter import convert_one

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
ICON_PATH = os.path.join(ASSETS_DIR, "icon.ico")

ACCENT = "#2563EB"
BG = "#F4F6FB"


class AnyDoc2MDApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AnyDoc2MD — Any Document to AI-Ready Markdown")
        self.root.geometry("880x640")
        self.root.minsize(720, 520)
        self.root.configure(bg=BG)
        self._set_icon()
        self._set_style()

        self.files = []
        self.output_dir = tk.StringVar(value="(same folder as each file)")
        self.output_dir_path = None
        self.use_ocr = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self._last_output_folder = None

        self._build_menu()
        self._build_ui()

    def _set_icon(self):
        try:
            self.root.iconbitmap(default=ICON_PATH)
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
            "Converts PDFs, Office documents, images, and emails "
            "(.eml/.msg, with attachments) into clean, AI-ready Markdown.\n\n"
            "Features: OCR fallback for scanned PDFs/images, recursive "
            "email-attachment conversion, and an Arabic PDF text-order fix.",
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
        self._file_list_buttons = (self.add_files_btn, self.add_folder_btn, self.remove_btn, self.clear_btn)

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
            text="Use OCR for images, scanned PDFs, and image attachments inside emails",
            variable=self.use_ocr,
            background=BG,
            activebackground=BG,
            selectcolor=ACCENT,
            font=("Segoe UI", 10),
            relief="flat",
            highlightthickness=0,
        ).pack(side="left")

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

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Select files to convert", filetypes=SUPPORTED_TYPES)
        for p in paths:
            self._add_path(p)

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
        self.log_msg(f"Added {added} file(s) from folder: {folder}")

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
        if self._last_output_folder and os.path.isdir(self._last_output_folder):
            os.startfile(self._last_output_folder)

    def start_conversion(self):
        if not self.files:
            messagebox.showwarning("No files", "Add some files or a folder first.")
            return
        self.convert_btn.configure(state="disabled")
        self.open_folder_btn.configure(state="disabled")
        for btn in self._file_list_buttons:
            btn.configure(state="disabled")
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
        out_dir_override = self.output_dir_path
        thread = threading.Thread(target=self._convert_all, args=(use_ocr, out_dir_override), daemon=True)
        thread.start()

    def _convert_and_write(self, src_path, use_ocr, out_dir_override):
        base = os.path.splitext(os.path.basename(src_path))[0]
        out_folder = out_dir_override or os.path.dirname(src_path)
        out_path = os.path.join(out_folder, base + ".md")
        text, method = convert_one(src_path, use_ocr)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        return out_path, method

    def _on_file_done(self, src_path, ok, detail, out_path):
        if ok:
            self.tree.item(src_path, values=(self.tree.item(src_path, "values")[0], detail), tags=("ok",))
            self.log_msg(f"[OK, {detail}] {src_path} -> {out_path}", "ok")
        else:
            self.tree.item(src_path, values=(self.tree.item(src_path, "values")[0], "Failed"), tags=("failed",))
            self.log_msg(f"[FAILED] {src_path} -> {detail}", "failed")

    def _on_all_done(self, ok_count, fail_count):
        self.log_msg(f"Done. {ok_count} succeeded, {fail_count} failed.", "info")
        self.status_var.set(f"Done — {ok_count} succeeded, {fail_count} failed.")
        self.convert_btn.configure(state="normal")
        for btn in self._file_list_buttons:
            btn.configure(state="normal")
        if self._last_output_folder:
            self.open_folder_btn.configure(state="normal")
        messagebox.showinfo(
            "Conversion complete", f"{ok_count} succeeded, {fail_count} failed.\nSee log for details."
        )

    def _convert_all(self, use_ocr, out_dir_override):
        files = list(self.files)
        total = len(files)
        ok_count = 0
        fail_count = 0
        completed = 0
        max_workers = min(8, max(2, os.cpu_count() or 4))
        last_out_folder = None

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_path = {
                pool.submit(self._convert_and_write, p, use_ocr, out_dir_override): p for p in files
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
                    traceback.print_exc()
                    self.root.after(0, self._on_file_done, src_path, False, str(e), None)
                self.root.after(0, self.progress.configure, {"value": completed})
                self.root.after(0, self.status_var.set, f"Converting... {completed}/{total}")

        self._last_output_folder = last_out_folder
        self.root.after(0, self._on_all_done, ok_count, fail_count)
