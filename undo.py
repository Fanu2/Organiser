"""
undo.py
Undo manager for File Organizer PRO.

Stores move/copy operations in:
~/.file_organizer_pro_undo.json

Each undo entry is a list of:
    {
        "src": original_path,
        "dest": new_path_after_move
    }
so "undo" simply moves file back to src.
"""

import os
import json
from tkinter import messagebox
import ttkbootstrap as tb

UNDO_FILE = os.path.expanduser("~/.file_organizer_pro_undo.json")


# ----------------------------------------------------------------------
# Utility functions for storage
# ----------------------------------------------------------------------
def read_store():
    """Return undo store dict."""
    if os.path.exists(UNDO_FILE):
        try:
            with open(UNDO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"ops": []}
    return {"ops": []}


def write_store(store):
    """Write undo store dict."""
    try:
        with open(UNDO_FILE, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except Exception:
        pass


def write_undo_operation(ops):
    """
    Append list of move/copy operations to undo storage.
    ops = [ {"src": ..., "dest": ...}, ... ]
    """
    store = read_store()
    arr = store.get("ops", [])
    arr.append(ops)
    store["ops"] = arr
    write_store(store)


# ----------------------------------------------------------------------
# Undo Manager Class
# ----------------------------------------------------------------------
class UndoManager:
    def __init__(self):
        pass

    def undo_last(self):
        store = read_store()
        ops = store.get("ops", [])

        if not ops:
            messagebox.showinfo("Undo", "No operations to undo.")
            return

        last = ops.pop()
        failures = []

        # Undo actions
        for mv in last:
            source_after_move = mv.get("dest")
            original_location = mv.get("src")

            if not source_after_move or not original_location:
                continue

            try:
                # Ensure destination folder exists
                os.makedirs(os.path.dirname(original_location), exist_ok=True)

                # Move file back
                if os.path.exists(source_after_move):
                    os.rename(source_after_move, original_location)

            except Exception as e:
                failures.append(str(e))

        # Save updated store
        store["ops"] = ops
        write_store(store)

        if failures:
            messagebox.showwarning(
                "Undo (Partial)",
                "Undo completed with some errors:\n\n" + "\n".join(failures)
            )
        else:
            messagebox.showinfo("Undo", "Undo operation successfully restored files.")

    # ------------------------------------------------------------------
    # Show complete undo history
    # ------------------------------------------------------------------
    def view_history(self):
        store = read_store()
        ops = store.get("ops", [])

        win = tb.Toplevel()
        win.title("Undo History")

        text = tb.Text(win, width=100, height=30)
        text.pack(fill="both", expand=True)

        if not ops:
            text.insert("end", "No undo history available.")
            return

        for i, op in enumerate(ops, start=1):
            text.insert("end", f"=== Operation #{i}: {len(op)} moves ===\n")
            for mv in op:
                text.insert("end", f"  {mv.get('src')}  →  {mv.get('dest')}\n")
            text.insert("end", "\n")

        text.see("end")

