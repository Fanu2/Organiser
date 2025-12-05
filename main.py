#!/usr/bin/env python3
"""
Main GUI for File Organizer PRO (ttkbootstrap)
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as tb

from organizer import Organizer
from duplicate_finder import DuplicateFinder
from undo import UndoManager
from monitor import FolderMonitor
from thumbnail_viewer import ThumbnailViewer
from utils import load_settings, save_settings

SETTINGS_PATH = os.path.expanduser("~/.file_organizer_pro_settings.json")


class App:
    def __init__(self):
        # main window
        self.root = tb.Window(
            title="File Organizer PRO",
            themename="darkly",
            size=(1200, 800)
        )

        # settings & modules
        self.settings = load_settings()
        self.organizer = Organizer(self)
        self.dup_finder = DuplicateFinder(self)
        self.undo_mgr = UndoManager()
        self.monitor = FolderMonitor(self)
        self.thumbnail = ThumbnailViewer(self)

        # build gui
        self._build_ui()

        # auto-load last source if exists
        last_src = self.settings.get("last_source")
        if last_src and os.path.isdir(last_src):
            self.organizer.scan_folder(last_src)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _build_ui(self):
        root = self.root

        # ---------------- Top Toolbar ----------------
        toolbar = tb.Frame(root)
        toolbar.pack(fill="x", padx=8, pady=6)

        tb.Button(toolbar, text="Select Source", bootstyle="secondary-outline",
                  command=self._select_source).pack(side="left", padx=4)

        tb.Button(toolbar, text="Select Destination", bootstyle="secondary-outline",
                  command=self._select_dest).pack(side="left", padx=4)

        tb.Button(toolbar, text="Add Files", bootstyle="secondary-outline",
                  command=self.organizer.add_files).pack(side="left", padx=4)

        tb.Button(toolbar, text="Find Duplicates", bootstyle="warning-outline",
                  command=self._find_duplicates).pack(side="left", padx=4)

        tb.Button(toolbar, text="Undo", bootstyle="info-outline",
                  command=self._undo).pack(side="left", padx=4)

        tb.Button(toolbar, text="Toggle Monitor", bootstyle="secondary-outline",
                  command=self.monitor.toggle).pack(side="left", padx=4)

        # ---------------- Options Frame ----------------
        options_frame = tb.Labelframe(root, text="Options", padding=10)
        options_frame.pack(fill="x", padx=8, pady=(0, 8))

        self.organizer.build_options_ui(options_frame)

        # ---------------- Main PanedWindow ----------------
        content = tb.Panedwindow(root, orient="horizontal")
        content.pack(fill="both", expand=True, padx=8)

        # left: file list
        left = tb.Frame(content)
        content.add(left, weight=3)
        self.organizer.build_file_list_ui(left)

        # right: preview + controls
        right = tb.Frame(content)
        content.add(right, weight=2)
        self.thumbnail.build_ui(right)
        self.organizer.build_controls_ui(right)

        # ---------------- Bottom Toolbar ----------------
        bottom = tb.Frame(root)
        bottom.pack(side="bottom", fill="x", padx=8, pady=8)

        # ORGANIZE button
        self.organize_btn = tb.Button(
            bottom,
            text="🚀 ORGANIZE NOW",
            bootstyle="success",
            command=self._preview_then_run
        )
        self.organize_btn.pack(side="left", padx=6)

        tb.Button(bottom, text="Preview", bootstyle="primary-outline",
                  command=self._preview_plan).pack(side="left", padx=6)

        tb.Button(bottom, text="Refresh", bootstyle="secondary-outline",
                  command=self.organizer.refresh).pack(side="left", padx=6)

        tb.Button(bottom, text="Undo History", bootstyle="info-outline",
                  command=self._view_undo_history).pack(side="left", padx=6)

        # status
        self.status = tb.Label(bottom, text="Ready", bootstyle="muted")
        self.status.pack(side="right")

        # connect file selection → preview change
        self.organizer.on_selection_change = self.thumbnail.display_selected

    # --------------------------------------------------------
    # Toolbar actions
    # --------------------------------------------------------
    def _select_source(self):
        d = filedialog.askdirectory(title="Select source folder")
        if d:
            self.settings['last_source'] = d
            save_settings(self.settings)
            self.organizer.scan_folder(d)

    def _select_dest(self):
        d = filedialog.askdirectory(title="Select destination folder")
        if d:
            self.settings['last_dest'] = d
            save_settings(self.settings)
            self.organizer.dst_dir = d

    def _find_duplicates(self):
        threading.Thread(
            target=self.dup_finder.find_duplicates_ui,
            daemon=True
        ).start()

    def _undo(self):
        self.undo_mgr.undo_last()

    def _view_undo_history(self):
        self.undo_mgr.view_history()

    def _preview_plan(self):
        self.organizer.preview_plan()

    def _preview_then_run(self):
        confirmed = self.organizer.preview_plan(confirm_only=True)
        if confirmed:
            threading.Thread(
                target=self.organizer.run_organize,
                daemon=True
            ).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()

