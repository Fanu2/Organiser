"""
organizer.py
Main organizing logic for File Organizer PRO.
Handles scanning, computing destinations, preview, and moving/copying.
"""

import os
import shutil
import time
from tkinter import filedialog, messagebox, IntVar, StringVar
import ttkbootstrap as tb

from utils import (
    video_or_image_type,
    get_size_category,
    exif_date,
    human_time,
    write_undo_operation
)


class Organizer:
    def __init__(self, app):
        self.app = app
        self.files = []  # list of dicts {path, name, selected}
        self.dst_dir = app.settings.get("last_dest", "")
        self.on_selection_change = None

        # Organizing options
        self.method_var = StringVar(value="type")
        self.keyword_var = StringVar("")
        self.dry_run_var = IntVar(value=1)
        self.copy_var = IntVar(value=0)
        self.pref_exif_var = IntVar(value=1)

    # --------------------------------------------------------------------
    # UI Builders (called from main.py)
    # --------------------------------------------------------------------
    def build_options_ui(self, parent):
        frame = tb.Frame(parent)
        frame.pack(fill="x")

        # ---------- Organize by ----------
        tb.Label(frame, text="Organize by:").grid(row=0, column=0, sticky="w")

        tb.Radiobutton(frame, text="Type",        variable=self.method_var, value="type").grid(row=0, column=1)
        tb.Radiobutton(frame, text="Extension",   variable=self.method_var, value="extension").grid(row=0, column=2)
        tb.Radiobutton(frame, text="Size",        variable=self.method_var, value="size").grid(row=0, column=3)
        tb.Radiobutton(frame, text="Date",        variable=self.method_var, value="date").grid(row=0, column=4)
        tb.Radiobutton(frame, text="EXIF Date",   variable=self.method_var, value="exif").grid(row=0, column=5)
        tb.Radiobutton(frame, text="Keyword",     variable=self.method_var, value="keyword").grid(row=0, column=6)

        # ---------- Keyword ----------
        tb.Label(frame, text="Keyword:").grid(row=1, column=0, sticky="w")
        tb.Entry(frame, textvariable=self.keyword_var).grid(row=1, column=1, columnspan=3, sticky="we")

        # ---------- Options ----------
        tb.Checkbutton(frame, text="Prefer EXIF date for images", variable=self.pref_exif_var)\
            .grid(row=1, column=4, sticky="w")

        tb.Checkbutton(frame, text="Dry Run (no move/copy)", variable=self.dry_run_var)\
            .grid(row=1, column=5, sticky="w")

        tb.Checkbutton(frame, text="Copy instead of move", variable=self.copy_var)\
            .grid(row=1, column=6, sticky="w")

    def build_file_list_ui(self, parent):
        tb.Label(parent, text="Files:").pack(anchor="w")

        canvas = tb.Canvas(parent, height=500)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar = tb.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="left", fill="y")

        inner = tb.Frame(canvas)
        self.files_canvas = canvas
        self.files_inner = inner

        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

    def build_controls_ui(self, parent):
        tb.Label(parent, text="Actions:", font=("Arial", 11, "bold")).pack(anchor="w", pady=(0, 4))

        tb.Button(parent, text="Refresh", bootstyle="secondary-outline",
                  command=self.refresh).pack(fill="x", pady=2)

        tb.Button(parent, text="Preview Plan", bootstyle="primary-outline",
                  command=self.preview_plan).pack(fill="x", pady=2)

        tb.Button(parent, text="Organize Now", bootstyle="success",
                  command=self.run_organize).pack(fill="x", pady=2)

    # --------------------------------------------------------------------
    # File List Management
    # --------------------------------------------------------------------
    def scan_folder(self, folder):
        self.files.clear()
        for fname in sorted(os.listdir(folder)):
            path = os.path.join(folder, fname)
            if os.path.isfile(path):
                entry = {
                    "path": path,
                    "name": fname,
                    "selected": IntVar(value=1)
                }
                self.files.append(entry)

        self.refresh_file_list()
        self.app.status.config(text=f"Loaded {len(self.files)} files.")

    def add_files(self):
        files = filedialog.askopenfilenames(title="Add files")
        for p in files:
            entry = {
                "path": p,
                "name": os.path.basename(p),
                "selected": IntVar(value=1)
            }
            self.files.append(entry)
        self.refresh_file_list()

    def _add_file_entry(self, path):
        """Called by FolderMonitor when new file appears"""
        name = os.path.basename(path)
        entry = {"path": path, "name": name, "selected": IntVar(value=1)}
        self.files.append(entry)

    def refresh(self):
        """Refresh list from last source"""
        src = self.app.settings.get("last_source")
        if src and os.path.isdir(src):
            self.scan_folder(src)

    def refresh_file_list(self):
        # Clear UI
        for w in self.files_inner.winfo_children():
            w.destroy()

        # Add rows
        for info in self.files:
            row = tb.Frame(self.files_inner)
            row.pack(fill="x", pady=2)

            tb.Checkbutton(row, variable=info["selected"]).pack(side="left")
            tb.Label(row, text=info["name"], width=50, anchor="w").pack(side="left")

            tb.Button(row, text="Preview", bootstyle="secondary-outline",
                      command=lambda p=info["path"]: self.app.thumbnail.display(p))\
                .pack(side="right")

        # Update preview if needed
        if self.on_selection_change:
            selected_paths = [f["path"] for f in self.files if f["selected"].get() == 1]
            self.on_selection_change(selected_paths)

    # --------------------------------------------------------------------
    # Destination folder logic
    # --------------------------------------------------------------------
    def compute_dest_folder(self, src):
        method = self.method_var.get()
        kw = self.keyword_var.get().strip().lower()

        if method == "type":
            return video_or_image_type(src)

        elif method == "extension":
            ext = os.path.splitext(src)[1][1:].upper() or "NO_EXT"
            return ext

        elif method == "size":
            size_bytes = os.path.getsize(src)
            return get_size_category(size_bytes)

        elif method == "date":
            if self.pref_exif_var.get() and video_or_image_type(src) == "Images":
                dt = exif_date(src)
            else:
                dt = None

            if not dt:
                ts = os.path.getmtime(src)
                dt = time.localtime(ts)
                return f"{dt.tm_year}/{time.strftime('%B', dt)}"
            else:
                return f"{dt.year}/{dt.strftime('%B')}"

        elif method == "exif":
            dt = exif_date(src)
            if dt:
                return f"{dt.year}/{dt.strftime('%B')}"
            return "No_EXIF"

        elif method == "keyword":
            base = os.path.basename(src).lower()
            return "Matches" if kw and kw in base else "No_Match"

        return "Other"

    # --------------------------------------------------------------------
    # Preview plan
    # --------------------------------------------------------------------
    def preview_plan(self, confirm_only=False):
        plan = []
        for f in self.files:
            if f["selected"].get() != 1:
                continue

            rel_folder = self.compute_dest_folder(f["path"])
            plan.append((f["path"], rel_folder))

        # Build summary
        summary = f"Files selected: {len(plan)}\n\n"
        dest_map = {}

        for src, folder in plan:
            dest_map.setdefault(folder, []).append(os.path.basename(src))

        for folder, files in dest_map.items():
            summary += f"[{folder}]  →  {len(files)} files\n"

        # If only confirmation required
        if confirm_only:
            return messagebox.askyesno("Confirm Organization", summary + "\nProceed?")

        # Create preview window
        win = tb.Toplevel(self.app.root)
        win.title("Preview Organization Plan")

        text = tb.Text(win, height=20, width=80)
        text.pack(fill="both", expand=True)
        text.insert("end", summary)

        tb.Button(win, text="Proceed", bootstyle="success",
                  command=lambda: (win.destroy(), self.run_organize())).pack(side="left", padx=8, pady=8)

        tb.Button(win, text="Cancel", bootstyle="danger-outline",
                  command=win.destroy).pack(side="right", padx=8, pady=8)

        return True

    # --------------------------------------------------------------------
    # Run organization
    # --------------------------------------------------------------------
    def run_organize(self):
        dst_root = self.dst_dir or self.app.settings.get("last_dest")

        if not dst_root:
            messagebox.showerror("No destination", "Please select a destination folder first.")
            return

        selected_files = [f for f in self.files if f["selected"].get() == 1]

        if not selected_files:
            messagebox.showinfo("No files", "No selected files.")
            return

        operations = []
        done = 0
        total = len(selected_files)

        for f in selected_files:
            src = f["path"]
            rel_folder = self.compute_dest_folder(src)
            final_folder = os.path.join(dst_root, rel_folder)
            os.makedirs(final_folder, exist_ok=True)

            dest_path = os.path.join(final_folder, os.path.basename(src))

            try:
                if not self.dry_run_var.get():
                    if self.copy_var.get():
                        shutil.copy2(src, dest_path)
                    else:
                        shutil.move(src, dest_path)

                    operations.append({"src": src, "dest": dest_path})

                done += 1
                self.app.status.config(text=f"Processed {done}/{total}")

            except Exception as e:
                messagebox.showwarning("Error", f"Failed on {src}:\n{e}")

        # Save undo history if real move/copy mode
        if operations and not self.dry_run_var.get():
            write_undo_operation(operations)

        messagebox.showinfo("Completed", f"Processed {done}/{total} files.")

