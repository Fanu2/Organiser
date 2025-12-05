"""
thumbnail_viewer.py
Handles image previews and thumbnail grid display.

Current implementation:
 - Shows a thumbnail preview when a file is selected
 - Supports “display_selected(list_of_paths)” callback
 - Provides a foundation to expand into a full gallery mode later
"""

import os
from PIL import Image, ImageTk
import ttkbootstrap as tb


class ThumbnailViewer:
    def __init__(self, app):
        self.app = app
        self.frame = None
        self.canvas = None
        self.last_image_obj = None  # prevent garbage collection

    # -----------------------------------------------------------
    # Build UI (called from main.py)
    # -----------------------------------------------------------
    def build_ui(self, parent):
        self.frame = tb.Frame(parent)
        self.frame.pack(fill="both", expand=True)

        tb.Label(self.frame, text="Preview / Thumbnail View:", font=("Arial", 11, "bold"))\
            .pack(anchor="w", pady=(0, 5))

        # Canvas where preview image will be displayed
        self.canvas = tb.Canvas(self.frame, bg="#222")
        self.canvas.pack(fill="both", expand=True)

    # -----------------------------------------------------------
    # Display a single image (preview button)
    # -----------------------------------------------------------
    def display(self, path):
        """Show a preview of the image/video thumbnail."""
        if not os.path.exists(path):
            return

        # Attempt to load image with pillow
        try:
            img = Image.open(path)

            # Resize to fit the canvas
            canvas_w = max(200, self.canvas.winfo_width())
            canvas_h = max(200, self.canvas.winfo_height())
            img.thumbnail((canvas_w - 20, canvas_h - 20))

            tk_img = ImageTk.PhotoImage(img)
            self.last_image_obj = tk_img  # keep reference

            self.canvas.delete("all")
            self.canvas.create_image(canvas_w // 2, canvas_h // 2, image=tk_img)

        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw",
                text=f"Preview error:\n{e}", fill="white")

    # -----------------------------------------------------------
    # Display first of selected files
    # (called automatically when selection changes)
    # -----------------------------------------------------------
    def display_selected(self, paths):
        """Display preview of the FIRST selected image."""
        if not paths:
            self.canvas.delete("all")
            return
        first = paths[0]
        # Only try preview if it's an image
        ext = os.path.splitext(first)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"):
            self.display(first)
        else:
            # Non-image → show icon or text
            self.canvas.delete("all")
            self.canvas.create_text(
                10, 10, anchor="nw",
                text=f"Selected file:\n{os.path.basename(first)}",
                fill="white"
            )

