#!/usr/bin/env python3
"""
File Organizer PRO — Extended
Features:
 - Organize by type/extension/size/date/keyword/EXIF date
 - Batch folder scan + preview
 - Drag & Drop (optional via tkinterdnd2)
 - Duplicate finder (SHA-256), move/delete duplicates
 - Undo last operation (stores moves to undo index)
 - Dark mode toggle
 - Automatic folder monitoring (watchdog)
 - Safe dry-run mode
"""

from __future__ import annotations
import os
import sys
import shutil
import mimetypes
import hashlib
import json
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from tkinter import *
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
# watchdog for folder monitoring (optional)
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False

    # Create a dummy class so code doesn't crash
    class FileSystemEventHandler:
        pass

    class Observer:
        def schedule(self, *a, **k): pass
        def start(self): pass
        def stop(self): pass
        def join(self, *a, **k): pass

# Optional imports
try:
    from PIL import Image, ExifTags, ImageTk
except Exception:
    print("Pillow is required. Install: pip install pillow")
    raise

# watchdog for folder monitoring
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False

# send2trash for safe deletes (optional)
try:
    from send2trash import send2trash
    SEND2TRASH_AVAILABLE = True
except Exception:
    SEND2TRASH_AVAILABLE = False

# tkinterdnd2 for drag-and-drop (optional)
try:
    import tkinterdnd2 as tkdnd
    TKDND_AVAILABLE = True
except Exception:
    TKDND_AVAILABLE = False

# ---------------- Settings persistence ----------------
SETTINGS_PATH = os.path.expanduser("~/.file_organizer_pro_settings.json")
UNDO_STORE = os.path.expanduser("~/.file_organizer_pro_undo.json")

DEFAULT_SETTINGS = {
    "last_source": "",
    "last_dest": "",
    "dark_mode": False,
    "exif_prefer": True
}

def load_settings() -> dict:
    s = DEFAULT_SETTINGS.copy()
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                s.update(json.load(f))
    except Exception:
        pass
    return s

def save_settings(s: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except Exception:
        pass

def load_undo_store() -> dict:
    try:
        if os.path.exists(UNDO_STORE):
            with open(UNDO_STORE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"operations": []}

def save_undo_store(store: dict):
    try:
        with open(UNDO_STORE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception:
        pass

# ---------------- Utilities ----------------
def human_time(s: Optional[float]) -> str:
    if not s:
        return "Unknown"
    return time.strftime("%H:%M:%S", time.gmtime(s))

def file_hash(path: str, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()

def guess_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        return "Other"
    if mime.startswith("image"):
        return "Images"
    if mime.startswith("video"):
        return "Videos"
    if mime.startswith("audio"):
        return "Audio"
    if mime.startswith("text") or mime.startswith("application"):
        return "Documents"
    return "Other"

def size_category(sz: int) -> str:
    if sz < 1_000_000: return "Small (<1MB)"
    if sz < 10_000_000: return "Medium (1–10MB)"
    if sz < 100_000_000: return "Large (10–100MB)"
    return "Huge (>100MB)"

def exif_date(path: str) -> Optional[datetime]:
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None
        tag_map = {ExifTags.TAGS.get(k,k): v for k,v in exif.items()}
        for key in ("DateTimeOriginal","DateTime","DateTimeDigitized"):
            if key in tag_map:
                val = tag_map[key]
                # typical format "YYYY:MM:DD HH:MM:SS"
                try:
                    dt = datetime.strptime(val, "%Y:%m:%d %H:%M:%S")
                    return dt
                except Exception:
                    pass
    except Exception:
        pass
    return None

# ---------------- Watchdog handler ----------------
class NewFileHandler(FileSystemEventHandler):
    def __init__(self, app):
        self.app = app
    def on_created(self, event):
        if not event.is_directory:
            # small delay to ensure file is ready
            time.sleep(0.5)
            self.app.on_new_file_detected(event.src_path)

# ---------------- Main App ----------------
class FileOrganizerPRO:
    def __init__(self, root):
        self.root = root
        self.root.title("File Organizer PRO")
        self.settings = load_settings()
        self.undo_store = load_undo_store()
        self.src_dir = self.settings.get("last_source","")
        self.dst_dir = self.settings.get("last_dest","")
        self.files: List[Dict] = []
        self.monitor_observer: Optional[Observer] = None
        self.dark_mode = self.settings.get("dark_mode", False)
        self.exif_prefer = self.settings.get("exif_prefer", True)

        self._build_ui()
        if self.src_dir:
            self.scan_folder(self.src_dir)

    def _build_ui(self):
        # style
        self.style = ttk.Style()
        if self.dark_mode:
            self._set_dark_theme()

        # top controls
        top = Frame(self.root)
        top.pack(fill=X, padx=6, pady=6)

        Button(top, text="Select Source Folder", command=self.select_source).pack(side=LEFT)
        Button(top, text="Select Destination Folder", command=self.select_dest).pack(side=LEFT, padx=4)
        Button(top, text="Refresh", command=self.refresh).pack(side=LEFT, padx=4)

        self.monitor_var = IntVar(value=1 if WATCHDOG_AVAILABLE else 0)
        cb = Checkbutton(top, text="Auto-monitor source", variable=self.monitor_var, command=self.toggle_monitor)
        cb.pack(side=LEFT, padx=8)
        if not WATCHDOG_AVAILABLE:
            cb.config(state="disabled")
            self.log("Watchdog not installed — auto-monitor disabled. Install with: pip install watchdog")

        Button(top, text="Toggle Dark Mode", command=self.toggle_dark).pack(side=RIGHT)

        # middle split
        mid = PanedWindow(self.root, orient=HORIZONTAL)
        mid.pack(fill=BOTH, expand=True, padx=6, pady=6)

        # left: file list & controls
        left = Frame(mid)
        mid.add(left, stretch="always")

        # drag & drop area if available
        if TKDND_AVAILABLE:
            try:
                # use tkinterdnd2 root wrapper
                self.root = tkdnd.TkinterDnD.Tk()
                # re-run basic geometry
                self.root.geometry("1100x700")
                self.log("Drag & drop enabled (tkinterdnd2).")
            except Exception:
                pass

        Label(left, text="Files in Source Folder:").pack(anchor="w")
        self.file_canvas = Canvas(left, height=360)
        self.file_scroll = Scrollbar(left, orient=VERTICAL, command=self.file_canvas.yview)
        self.file_inner = Frame(self.file_canvas)
        self.file_inner.bind("<Configure>", lambda e: self.file_canvas.configure(scrollregion=self.file_canvas.bbox("all")))
        self.file_canvas.create_window((0,0), window=self.file_inner, anchor="nw")
        self.file_canvas.configure(yscrollcommand=self.file_scroll.set)
        self.file_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.file_scroll.pack(side=LEFT, fill=Y)

        # controls under list
        btns = Frame(left)
        btns.pack(fill=X, pady=6)
        Button(btns, text="Add Files", command=self.add_files).pack(side=LEFT)
        Button(btns, text="Find Duplicates", command=self.find_duplicates).pack(side=LEFT, padx=6)
        Button(btns, text="Undo Last", command=self.undo_last).pack(side=LEFT, padx=6)

        # right: preview, settings, progress, log
        right = Frame(mid, width=420)
        mid.add(right)

        Label(right, text="Preview:").pack(anchor="w")
        self.preview_lbl = Label(right, text="No preview", relief="sunken", width=60, height=16)
        self.preview_lbl.pack()

        self.info_lbl = Label(right, text="", justify=LEFT)
        self.info_lbl.pack(anchor="w")

        # organizing options
        Label(right, text="Organize by:").pack(anchor="w", pady=(8,0))
        self.method_var = StringVar(value="type")
        options = [("Type","type"),("Extension","extension"),("Size","size"),("Date","date"),("EXIF Date","exif"),("Keyword","keyword")]
        for txt,val in options:
            Radiobutton(right, text=txt, variable=self.method_var, value=val).pack(anchor="w")

        # keyword entry
        kwf = Frame(right); kwf.pack(fill=X, pady=4)
        Label(kwf, text="Keyword:").pack(side=LEFT)
        self.keyword_var = StringVar()
        Entry(kwf, textvariable=self.keyword_var).pack(side=LEFT, fill=X, expand=True)

        # EXIF preference checkbox
        self.exif_var = IntVar(value=1 if self.exif_prefer else 0)
        Checkbutton(right, text="Prefer EXIF date for images when sorting by date", variable=self.exif_var).pack(anchor="w")

        # dry run and move/copy option
        self.dry_var = IntVar(value=1)
        Checkbutton(right, text="Dry run (don't move files)", variable=self.dry_var).pack(anchor="w")
        self.copy_var = IntVar(value=0)
        Checkbutton(right, text="Copy instead of move", variable=self.copy_var).pack(anchor="w")

        # watermark of progress
        Label(right, text="Progress:").pack(anchor="w", pady=(8,0))
        self.progress_overall = ttk.Progressbar(right, orient="horizontal", length=380, mode="determinate")
        self.progress_overall.pack(pady=2)
        self.progress_current = ttk.Progressbar(right, orient="horizontal", length=380, mode="determinate")
        self.progress_current.pack(pady=2)

        # log
        Label(right, text="Log:").pack(anchor="w", pady=(6,0))
        self.log_box = Text(right, height=10)
        self.log_box.pack(fill=BOTH, expand=True)

        # drag & drop binding (if available)
        if TKDND_AVAILABLE:
            try:
                self.file_canvas.drop_target_register(tkdnd.DND_FILES)
                self.file_canvas.dnd_bind('<<Drop>>', self._on_drop)
                self.log("Drop files onto the list to add them.")
            except Exception:
                pass

    # ---------------- UI helpers ----------------
    def log(self, s: str):
        ts = time.strftime("%H:%M:%S")
        try:
            self.log_box.insert(END, f"[{ts}] {s}\n")
            self.log_box.see(END)
        except Exception:
            print(f"[{ts}] {s}")

    def select_source(self):
        d = filedialog.askdirectory(title="Select source folder")
        if not d:
            return
        self.src_dir = d
        self.settings['last_source'] = d
        save_settings(self.settings)
        self.scan_folder(d)
        if self.monitor_var.get() and WATCHDOG_AVAILABLE:
            self._start_monitor(d)

    def select_dest(self):
        d = filedialog.askdirectory(title="Select destination folder")
        if not d:
            return
        self.dst_dir = d
        self.settings['last_dest'] = d
        save_settings(self.settings)
        self.log(f"Destination set: {d}")

    def add_files(self):
        files = filedialog.askopenfilenames(title="Add files")
        for f in files:
            self._add_file_entry(f)
        self.refresh_file_list()

    def _on_drop(self, event):
        # event.data may contain braces; split
        data = event.data
        paths = self.root.tk.splitlist(data)
        for p in paths:
            if os.path.isfile(p):
                self._add_file_entry(p)
            elif os.path.isdir(p):
                self.scan_folder(p)
        self.refresh_file_list()

    # ---------------- Scanning ----------------
    def scan_folder(self, folder: str):
        self.files.clear()
        try:
            for name in sorted(os.listdir(folder)):
                p = os.path.join(folder, name)
                if os.path.isfile(p):
                    self._add_file_entry(p)
            self.src_dir = folder
            self.log(f"Scanned folder: {folder} ({len(self.files)} files)")
            self.refresh_file_list()
        except Exception as e:
            self.log(f"Scan error: {e}")

    def _add_file_entry(self, path: str):
        path = os.path.abspath(path)
        if any(entry["path"] == path for entry in self.files):
            return
        res = self._get_file_info(path)
        entry = {
            "path": path,
            "name": os.path.basename(path),
            "res": res,
            "selected": True
        }
        self.files.append(entry)

    def _get_file_info(self, path: str) -> dict:
        st = os.stat(path)
        res = {
            "size": st.st_size,
            "mtime": st.st_mtime,
            "type": guess_type(path)
        }
        # if image and pillow available, get exif date
        if res["type"] == "Images" and self.exif_prefer:
            d = exif_date(path)
            if d:
                res["exif_date"] = d.timestamp()
        return res

    def refresh_file_list(self):
        for w in self.file_inner.winfo_children():
            w.destroy()
        for entry in self.files:
            row = Frame(self.file_inner, bd=1, relief="flat")
            row.pack(fill=X, padx=2, pady=2)
            var = IntVar(value=1 if entry["selected"] else 0)
            chk = Checkbutton(row, variable=var)
            chk.pack(side=LEFT)
            # store var in entry for toggling
            entry["_var"] = var
            Label(row, text=entry["name"], width=50, anchor="w").pack(side=LEFT)
            Label(row, text=entry["res"]["type"]).pack(side=LEFT, padx=6)
            Label(row, text=size_category(entry["res"]["size"])).pack(side=LEFT, padx=6)
            btn = Button(row, text="Preview", command=lambda p=entry["path"]: self.preview(p))
            btn.pack(side=RIGHT)

    def preview(self, path: str):
        try:
            if guess_type(path) == "Images":
                img = Image.open(path)
                img.thumbnail((480,360))
                tkimg = ImageTk.PhotoImage(img)
                self.preview_lbl.config(image=tkimg, text="")
                self.preview_lbl.image = tkimg
            else:
                self.preview_lbl.config(image="", text=f"Preview not available for {os.path.basename(path)}")
                self.preview_lbl.image = None
            info = []
            st = os.stat(path)
            info.append(f"Path: {path}")
            info.append(f"Size: {st.st_size} bytes")
            info.append(f"Modified: {time.ctime(st.st_mtime)}")
            if "exif_date" in self._get_file_info(path):
                info.append("EXIF date: available")
            self.info_lbl.config(text="\n".join(info))
        except Exception as e:
            self.log(f"Preview error: {e}")

    # ---------------- Duplicates ----------------
    def find_duplicates(self):
        # Build hash map
        selected = [e for e in self.files if e["_var"].get()==1]
        if not selected:
            messagebox.showinfo("No files", "Select files or scan a folder first.")
            return
        self.log("Computing hashes (this may take time)...")
        hash_map: Dict[str, List[str]] = {}
        progress = 0
        total = len(selected)
        for e in selected:
            try:
                h = file_hash(e["path"])
                hash_map.setdefault(h, []).append(e["path"])
            except Exception as ex:
                self.log(f"Hash error {e['path']}: {ex}")
            progress += 1
            self.progress_overall['value'] = int(100*progress/total)
            self.root.update_idletasks()
        duplicates = [paths for paths in hash_map.values() if len(paths)>1]
        if not duplicates:
            messagebox.showinfo("Duplicates", "No duplicates found.")
            self.log("No duplicates found.")
            return
        # show duplicates and ask action
        msg = f"Found {len(duplicates)} duplicate groups. Choose action:\n\n1) Move duplicates to folder\n2) Delete duplicates (send2trash if available)\n3) Do nothing"
        choice = simpledialog.askinteger("Duplicates", msg, minvalue=1, maxvalue=3)
        if choice is None or choice==3:
            self.log("Duplicates check aborted by user.")
            return
        if choice==1:
            # ask target folder
            target = filedialog.askdirectory(title="Select folder to move duplicates into")
            if not target:
                return
            for group in duplicates:
                # keep first, move rest
                keep = group[0]
                for p in group[1:]:
                    try:
                        dest = os.path.join(target, os.path.basename(p))
                        shutil.move(p, dest)
                        self.log(f"Moved duplicate {p} -> {dest}")
                    except Exception as ex:
                        self.log(f"Failed moving {p}: {ex}")
        elif choice==2:
            if not SEND2TRASH_AVAILABLE:
                if not messagebox.askyesno("Warning", "send2trash not available — this will permanently delete files. Continue?"):
                    return
            for group in duplicates:
                for p in group[1:]:
                    try:
                        if SEND2TRASH_AVAILABLE:
                            send2trash(p)
                        else:
                            os.remove(p)
                        self.log(f"Deleted duplicate {p}")
                    except Exception as ex:
                        self.log(f"Failed deleting {p}: {ex}")
        self.refresh_file_list()
        messagebox.showinfo("Done", "Duplicates handling complete.")

    # ---------------- Undo ----------------
    def undo_last(self):
        store = load_undo_store()
        ops = store.get("operations", [])
        if not ops:
            messagebox.showinfo("Nothing to undo", "No previous operations found.")
            return
        last = ops.pop()  # last operation is list of moves
        failures = []
        for mv in last:
            src = mv.get("dest")
            dest = mv.get("src")
            try:
                # move back
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(src, dest)
                else:
                    failures.append(src)
            except Exception as ex:
                failures.append(f"{src}: {ex}")
        save_undo_store({"operations": ops})
        if failures:
            self.log(f"Undo completed with failures: {failures}")
            messagebox.showwarning("Undo", f"Completed with failures. See log.")
        else:
            self.log("Undo completed successfully.")
            messagebox.showinfo("Undo", "Last operation undone.")

    # ---------------- Monitor ----------------
    def _start_monitor(self, folder: str):
        if not WATCHDOG_AVAILABLE:
            return
        if self.monitor_observer:
            try:
                self.monitor_observer.stop()
                self.monitor_observer.join(timeout=1)
            except Exception:
                pass
        handler = NewFileHandler(self)
        obs = Observer()
        obs.schedule(handler, folder, recursive=False)
        obs.start()
        self.monitor_observer = obs
        self.log(f"Started monitoring {folder} for new files.")

    def _stop_monitor(self):
        if self.monitor_observer:
            try:
                self.monitor_observer.stop()
                self.monitor_observer.join(timeout=1)
            except Exception:
                pass
            self.monitor_observer = None
            self.log("Stopped monitoring source folder.")

    def toggle_monitor(self):
        if not WATCHDOG_AVAILABLE:
            messagebox.showwarning("Not available", "watchdog python package not installed.")
            return
        if self.monitor_var.get():
            if not getattr(self,'src_dir',None):
                messagebox.showinfo("Select folder", "Select source folder before enabling monitoring.")
                self.monitor_var.set(0)
                return
            self._start_monitor(self.src_dir)
        else:
            self._stop_monitor()

    def on_new_file_detected(self, path: str):
        # add to list
        self.log(f"New file detected: {path}")
        self._add_file_entry(path)
        self.refresh_file_list()

    # ---------------- Theme ----------------
    def toggle_dark(self):
        self.dark_mode = not self.dark_mode
        self.settings['dark_mode'] = self.dark_mode
        save_settings(self.settings)
        if self.dark_mode:
            self._set_dark_theme()
        else:
            self._set_light_theme()

    def _set_dark_theme(self):
        try:
            bg = "#2e2e2e"
            fg = "#eaeaea"
            self.root.configure(bg=bg)
            self.style.configure(".", background=bg, foreground=fg)
            self.style.configure("TLabel", background=bg, foreground=fg)
            self.style.configure("TFrame", background=bg)
            self.style.configure("TButton", background="#444444", foreground=fg)
            self.log("Dark mode enabled.")
        except Exception:
            pass

    def _set_light_theme(self):
        try:
            self.root.configure(bg=None)
            self.style.theme_use('default')
            self.log("Light mode enabled.")
        except Exception:
            pass

    # ---------------- Organize operation ----------------
    def organize(self):
        if not getattr(self,"src_dir",None) or not getattr(self,"dst_dir",None):
            messagebox.showerror("Missing folders", "Select source and destination folders first.")
            return
        method = self.method_var.get()
        keyword = self.keyword_var.get().strip().lower()
        prefer_exif = bool(self.exif_var.get())
        dry = bool(self.dry_var.get())
        do_copy = bool(self.copy_var.get())

        selected_entries = [e for e in self.files if e.get("_var",IntVar(value=1)).get()==1]
        if not selected_entries:
            messagebox.showinfo("No files", "No selected files to organize.")
            return

        total = len(selected_entries)
        self.progress_overall['value'] = 0
        operations = []  # for undo: list of {"src":orig,"dest":new}

        for idx, e in enumerate(selected_entries, start=1):
            src = e["path"]
            dest_folder = None

            try:
                # determine folder rules
                if method == "type":
                    dest_folder = guess_type(src)
                elif method == "extension":
                    ext = os.path.splitext(src)[1][1:].upper() or "NO_EXT"
                    dest_folder = ext
                elif method == "size":
                    dest_folder = size_category(os.path.getsize(src))
                elif method == "date":
                    # prefer EXIF date for images
                    dt = None
                    if prefer_exif and guess_type(src)=="Images":
                        dt = exif_date(src)
                    if not dt:
                        dt = datetime.fromtimestamp(os.path.getmtime(src))
                    dest_folder = f"{dt.year}/{dt.strftime('%B')}"
                elif method == "exif":
                    dt = exif_date(src)
                    if dt:
                        dest_folder = f"{dt.year}/{dt.strftime('%B')}"
                    else:
                        dest_folder = "No_EXIF"
                elif method == "keyword":
                    dest_folder = "Matches" if keyword and keyword in os.path.basename(src).lower() else "No_Match"
                else:
                    dest_folder = "Other"

                final_folder = os.path.join(self.dst_dir, dest_folder)
                os.makedirs(final_folder, exist_ok=True)
                dest_path = os.path.join(final_folder, os.path.basename(src))

                if dry:
                    self.log(f"[DRY] {src} -> {dest_path}")
                else:
                    if do_copy:
                        shutil.copy2(src, dest_path)
                        self.log(f"Copied: {src} -> {dest_path}")
                    else:
                        shutil.move(src, dest_path)
                        self.log(f"Moved: {src} -> {dest_path}")
                    # record operation for undo
                    operations.append({"src": src, "dest": dest_path})
            except Exception as ex:
                self.log(f"Failed processing {src}: {ex}")

            # progress
            self.progress_overall['value'] = int(100 * idx / total)
            self.progress_current['value'] = 0
            self.root.update_idletasks()

        # store undo if any real operations
        if operations and not dry:
            store = load_undo_store()
            ops = store.get("operations", [])
            ops.append(operations)
            store["operations"] = ops
            save_undo_store(store)

        self.log("Organize operation completed.")
        messagebox.showinfo("Done", "Organize operation completed.")

    # ---------------- Refresh / misc ----------------
    def refresh(self):
        if getattr(self,'src_dir',None):
            self.scan_folder(self.src_dir)
        else:
            self.log("No source folder selected.")

# ----------------- Runner -----------------
def main():
    root = Tk()
    app = FileOrganizerPRO(root)

    # attach menus
    men = Menu(root)
    root.config(menu=men)
    fm = Menu(men, tearoff=0)
    men.add_cascade(label="File", menu=fm)
    fm.add_command(label="Select Source", command=app.select_source)
    fm.add_command(label="Select Destination", command=app.select_dest)
    fm.add_separator()
    fm.add_command(label="Exit", command=root.quit)

    helpm = Menu(men, tearoff=0)
    men.add_cascade(label="Help", menu=helpm)
    helpm.add_command(label="About", command=lambda: messagebox.showinfo("About", "File Organizer PRO\nFeatures: duplicates, undo, drag-drop, monitor, EXIF"))
    root.geometry("1100x700")
    root.mainloop()

if __name__ == "__main__":
    main()
