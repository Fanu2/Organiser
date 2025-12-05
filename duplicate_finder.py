"""
duplicate_finder.py
Duplicate detection for File Organizer PRO.
Uses:
 - SHA-256 for exact duplicates
 - pHash (imagehash) for perceptual similarity
"""

import os
import threading
from tkinter import messagebox
import ttkbootstrap as tb
from PIL import Image
import imagehash
from utils import file_hash


class DuplicateFinder:
    def __init__(self, app):
        self.app = app

    # ------------------------------------------------------
    # Public method triggered by GUI
    # ------------------------------------------------------
    def find_duplicates_ui(self):
        # Selected files only
        files = [f["path"] for f in self.app.organizer.files if f["selected"].get() == 1]
        if not files:
            messagebox.showinfo("Duplicates", "No selected files to analyze.")
            return

        # Run in background thread (to avoid freezing UI)
        threading.Thread(target=self._run_find, args=(files,), daemon=True).start()

    # ------------------------------------------------------
    # Internal: compute hashes
    # ------------------------------------------------------
    def _run_find(self, files):
        # EXACT duplicates via SHA-256
        hash_map = {}
        for p in files:
            try:
                h = file_hash(p)
                hash_map.setdefault(h, []).append(p)
            except Exception:
                pass

        exact_groups = [group for group in hash_map.values() if len(group) > 1]

        # PERCEPTUAL duplicates for images via pHash
        phash_map = {}
        for p in files:
            try:
                img = Image.open(p)
                ph_val = str(imagehash.phash(img))
                phash_map.setdefault(ph_val, []).append(p)
            except Exception:
                pass

        perceptual_groups = [group for group in phash_map.values() if len(group) > 1]

        # Build summary
        summary = (
            f"Exact duplicates found: {len(exact_groups)} groups\n"
            f"Perceptual duplicates found: {len(perceptual_groups)} groups\n"
        )

        # Show summary window
        dlg = tb.Toplevel(self.app.root)
        dlg.title("Duplicate Summary")

        tb.Label(dlg, text=summary, font=("Arial", 12)).pack(padx=10, pady=10)

        tb.Button(
            dlg,
            text="View Details",
            bootstyle="info-outline",
            command=lambda: self._show_details(exact_groups, perceptual_groups)
        ).pack(pady=10)

        tb.Button(
            dlg,
            text="Close",
            bootstyle="danger-outline",
            command=dlg.destroy
        ).pack(pady=5)

    # ------------------------------------------------------
    # Show detailed duplicate lists
    # ------------------------------------------------------
    def _show_details(self, exact_groups, perceptual_groups):
        win = tb.Toplevel(self.app.root)
        win.title("Duplicate Details")

        text = tb.Text(win, width=100, height=30)
        text.pack(fill="both", expand=True)

        # --- exact duplicates ---
        text.insert("end", "===== EXACT DUPLICATES =====\n\n")
        if not exact_groups:
            text.insert("end", "No exact duplicates.\n\n")
        else:
            for group in exact_groups:
                for p in group:
                    text.insert("end", f"  {p}\n")
                text.insert("end", "\n")

        # --- perceptual duplicates ---
        text.insert("end", "\n===== PERCEPTUAL DUPLICATES (pHash) =====\n\n")
        if not perceptual_groups:
            text.insert("end", "No perceptual duplicates.\n\n")
        else:
            for group in perceptual_groups:
                for p in group:
                    text.insert("end", f"  {p}\n")
                text.insert("end", "\n")

        # auto-scroll
        text.see("end")

