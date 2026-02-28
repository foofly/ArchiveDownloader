# /// script
# requires-python = ">=3.10"
# dependencies = ["pikepdf", "requests"]
# ///

import logging
import os
import queue
import threading
import tkinter as tk
import urllib.parse
from tkinter import filedialog, messagebox, scrolledtext, ttk

import ArchiveDownloader as ad

_SENTINEL = object()


def _extract_identifier(url_or_id):
    """Return the Archive.org item identifier from a URL or bare identifier."""
    parsed = urllib.parse.urlparse(url_or_id)
    if parsed.scheme in ("http", "https"):
        parts = [p for p in parsed.path.split("/") if p]
        # /details/<id>  or  /download/<id>  or  /metadata/<id>
        if len(parts) >= 2 and parts[0] in ("details", "download", "metadata"):
            return parts[1]
        if parts:
            return parts[-1]
    return url_or_id.strip()


class TextHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self._queue = log_queue

    def emit(self, record):
        self._queue.put(self.format(record))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Archive.org PDF Downloader")
        self.resizable(True, True)
        self._log_queue = queue.Queue()
        self._build_ui()
        self.after(100, self._poll_log_queue)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        form = ttk.LabelFrame(self, text="Settings")
        form.pack(fill=tk.X, padx=10, pady=8)

        self._fields = {}
        rows = [
            ("Archive.org URL *", "url",          False),
            ("Pattern",           "pattern",      False),
            ("Download Dir",      "download_dir", "dir"),
            ("Upload Dir",        "upload_dir",   "dir"),
            ("History File",      "history_file", "file"),
        ]

        for i, (label, key, browse) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky=tk.W, **pad)
            var = tk.StringVar()
            entry = ttk.Entry(form, textvariable=var, width=42)
            entry.grid(row=i, column=1, sticky=tk.EW, **pad)
            self._fields[key] = (var, entry)

            if browse == "dir":
                ttk.Button(form, text="Browse",
                           command=lambda k=key: self._browse_dir(k)
                           ).grid(row=i, column=2, **pad)
            elif browse == "file":
                ttk.Button(form, text="Browse",
                           command=lambda k=key: self._browse_file(k)
                           ).grid(row=i, column=2, **pad)

        # Helper text under Pattern
        ttk.Label(form, text="(optional — if omitted, files are moved as-is)",
                  foreground="grey").grid(row=1, column=1, sticky=tk.W, padx=8)

        # Defaults
        self._fields["download_dir"][0].set(ad.DOWNLOAD_DIR)
        self._fields["upload_dir"][0].set(ad.UPLOAD_DIR)
        self._fields["history_file"][0].set(ad.HISTORY_FILE)

        # Retries + log level row
        r = len(rows)
        ttk.Label(form, text="Retries").grid(row=r, column=0, sticky=tk.W, **pad)
        inner = ttk.Frame(form)
        inner.grid(row=r, column=1, sticky=tk.W, **pad)

        self._retries_var = tk.StringVar(value="3")
        ttk.Spinbox(inner, textvariable=self._retries_var,
                    from_=1, to=10, width=4).pack(side=tk.LEFT)

        ttk.Label(inner, text="  Log Level").pack(side=tk.LEFT)
        self._log_level_var = tk.StringVar(value="INFO")
        ttk.Combobox(inner, textvariable=self._log_level_var,
                     values=["DEBUG", "INFO", "WARNING", "ERROR"],
                     state="readonly", width=9).pack(side=tk.LEFT, padx=4)

        form.columnconfigure(1, weight=1)

        # Run button
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=4)
        self._run_btn = ttk.Button(btn_frame, text="Run", command=self._on_run)
        self._run_btn.pack(ipadx=20)

        # Log output
        log_frame = ttk.LabelFrame(self, text="Log output")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        self._log_text = scrolledtext.ScrolledText(log_frame, state=tk.DISABLED,
                                                   wrap=tk.WORD, height=14)
        self._log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.minsize(600, 500)

    # ------------------------------------------------------------------
    # Browse helpers
    # ------------------------------------------------------------------

    def _browse_dir(self, key):
        path = filedialog.askdirectory(title="Select directory")
        if path:
            self._fields[key][0].set(path)

    def _browse_file(self, key):
        path = filedialog.asksaveasfilename(
            title="Select history file",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*")],
        )
        if path:
            self._fields[key][0].set(path)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _collect_args(self):
        return {k: v.get().strip() for k, (v, _) in self._fields.items()}

    def _validate(self, args):
        if not args["url"]:
            messagebox.showerror("Missing field", "Archive.org URL is required.")
            return False
        try:
            int(self._retries_var.get())
        except ValueError:
            messagebox.showerror("Invalid value", "Retries must be an integer.")
            return False
        return True

    def _set_form_state(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for _, entry in self._fields.values():
            entry.config(state=state)
        self._run_btn.config(state=state)

    def _on_run(self):
        args = self._collect_args()
        if not self._validate(args):
            return

        self._set_form_state(False)
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.config(state=tk.DISABLED)

        run_args = {
            **args,
            "retries": int(self._retries_var.get()),
            "log_level": self._log_level_var.get(),
        }
        t = threading.Thread(target=self._run_download, args=(run_args,), daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _run_download(self, args):
        log = logging.getLogger("gui_run")
        log.setLevel(getattr(logging, args["log_level"]))
        log.propagate = False
        log.handlers.clear()
        handler = TextHandler(self._log_queue)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                               datefmt="%Y-%m-%d %H:%M:%S"))
        log.addHandler(handler)

        ad_logger = logging.getLogger(ad.__name__)
        ad_logger.setLevel(getattr(logging, args["log_level"]))
        ad_logger.propagate = False
        ad_logger.handlers.clear()
        ad_logger.addHandler(handler)

        try:
            identifier = _extract_identifier(args["url"])
            pattern = args["pattern"]
            retries = args["retries"]

            log.info("Identifier: %s", identifier)

            ad.ensureDirectory(args["download_dir"])
            ad.ensureDirectory(args["upload_dir"])

            history = ad.loadHistory(args["history_file"])
            if identifier not in history:
                history[identifier] = []

            metadata = ad.getMetadata(identifier, retries=retries)
            if metadata is None:
                log.error("Could not fetch metadata — aborting.")
                return

            series = metadata.get("metadata", {}).get("title", identifier)
            log.info("Series: %s", series)

            pending = ad.getPendingFilenames(identifier, history, metadata)
            if not pending:
                log.info("No new PDFs to process.")
                return

            for filename in pending:
                downloaded = ad.downloadFile(identifier, filename,
                                             download_dir=args["download_dir"],
                                             retries=retries)
                if not downloaded:
                    continue

                if pattern:
                    ok = ad.ApplyMetadata(filename, pattern, series,
                                         download_dir=args["download_dir"],
                                         upload_dir=args["upload_dir"])
                else:
                    log.info("Saved %s", os.path.join(args["download_dir"], filename))
                    ok = True

                if ok:
                    history[identifier].append(filename)
                    ad.SaveHistory(history, args["history_file"])

            log.info("Run complete.")
        except Exception as exc:
            log.exception("Unexpected error: %s", exc)
        finally:
            self._log_queue.put(_SENTINEL)

    # ------------------------------------------------------------------
    # Queue drain (main thread)
    # ------------------------------------------------------------------

    def _poll_log_queue(self):
        try:
            while True:
                item = self._log_queue.get_nowait()
                if item is _SENTINEL:
                    self._set_form_state(True)
                else:
                    self._log_text.config(state=tk.NORMAL)
                    self._log_text.insert(tk.END, item + "\n")
                    self._log_text.see(tk.END)
                    self._log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)


if __name__ == "__main__":
    app = App()
    app.mainloop()
