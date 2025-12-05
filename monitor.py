"""
monitor.py
Folder monitoring system for File Organizer PRO.

Uses watchdog (if installed) to detect new files in real-time
and automatically add them to the file list.

If watchdog is missing, the monitor falls back to a dummy mode
and simply notifies the user.
"""

import time

# Attempt to load watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False
    # Dummy fallback classes
    class FileSystemEventHandler:
        pass
    class Observer:
        def schedule(self, *a, **k): pass
        def start(self): pass
        def stop(self): pass
        def join(self, *a, **k): pass


class _Handler(FileSystemEventHandler):
    """
    Internal event handler that notifies Organizer
    when new files appear.
    """
    def __init__(self, organizer):
        self.organizer = organizer

    def on_created(self, event):
        if not event.is_directory:
            # Allow file to finish writing
            time.sleep(0.5)
            self.organizer._add_file_entry(event.src_path)
            self.organizer.refresh_file_list()


class FolderMonitor:
    """
    Toggles folder monitoring on/off.
    """
    def __init__(self, app):
        self.app = app
        self.observer = None
        self.folder = None

    # -------------------------------------------------------------
    def toggle(self):
        """Toggle monitoring of the last-selected source folder."""
        if not WATCHDOG_AVAILABLE:
            self.app.status.config(text="Watchdog not installed.")
            return

        # Stop if already running
        if self.observer:
            self.stop()
            return

        # Start new monitoring session
        folder = self.app.settings.get("last_source")
        if not folder:
            self.app.status.config(text="No source folder selected.")
            return

        self.start(folder)

    # -------------------------------------------------------------
    def start(self, folder):
        """Start monitoring a folder."""
        self.stop()

        self.folder = folder
        handler = _Handler(self.app.organizer)
        self.observer = Observer()

        try:
            self.observer.schedule(handler, folder, recursive=False)
            self.observer.start()
            self.app.status.config(text=f"Monitoring {folder}")
        except Exception as e:
            self.app.status.config(text=f"Monitor error: {e}")
            self.observer = None

    # -------------------------------------------------------------
    def stop(self):
        """Stop folder monitoring."""
        if self.observer:
            try:
                self.observer.stop()
                self.observer.join(timeout=1)
            except Exception:
                pass

        self.observer = None
        self.app.status.config(text="Monitoring stopped.")

