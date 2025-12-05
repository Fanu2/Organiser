"""
utils.py
Common helper functions for File Organizer PRO.
"""

import os
import json
import hashlib
import time
from PIL import Image, ExifTags

# -------------------------------------------------------------------
# SETTINGS STORAGE
# -------------------------------------------------------------------
SETTINGS_PATH = os.path.expanduser("~/.file_organizer_pro_settings.json")


def load_settings():
    """Load settings from JSON file."""
    try:
        if os.path.exists(SETTINGS_PATH):
            return json.load(open(SETTINGS_PATH, "r", encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_settings(settings):
    """Save app settings."""
    try:
        json.dump(settings, open(SETTINGS_PATH, "w", encoding="utf-8"), indent=2)
    except Exception:
        pass


# -------------------------------------------------------------------
# FILE TYPE DETECTION
# -------------------------------------------------------------------
def video_or_image_type(path):
    """Return category: Images, Videos, Audio, Documents, Other."""
    ext = os.path.splitext(path)[1].lower()

    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp"):
        return "Images"
    if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return "Videos"
    if ext in (".mp3", ".wav", ".m4a", ".flac", ".aac"):
        return "Audio"
    if ext in (".pdf", ".docx", ".txt", ".pptx", ".xlsx"):
        return "Documents"

    return "Other"


# -------------------------------------------------------------------
# FILE SIZE CATEGORY
# -------------------------------------------------------------------
def get_size_category(size_bytes):
    """Categorize file size into Small/Medium/Large/Huge."""
    if size_bytes < 1_000_000:
        return "Small (<1 MB)"
    if size_bytes < 10_000_000:
        return "Medium (1–10 MB)"
    if size_bytes < 100_000_000:
        return "Large (10–100 MB)"
    return "Huge (>100 MB)"


# -------------------------------------------------------------------
# EXIF DATE EXTRACTION
# -------------------------------------------------------------------
def exif_date(path):
    """
    Extract EXIF timestamp → returns datetime object or None.
    """
    try:
        img = Image.open(path)
        exif = img._getexif()
        if not exif:
            return None

        tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}

        for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            if key in tag_map:
                ts = tag_map[key]
                try:
                    import datetime
                    return datetime.datetime.strptime(ts, "%Y:%m:%d %H:%M:%S")
                except Exception:
                    return None
    except Exception:
        return None

    return None


# -------------------------------------------------------------------
# FILE HASHING (used by duplicate_finder)
# -------------------------------------------------------------------
def file_hash(path, block_size=65536):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(block_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


# -------------------------------------------------------------------
# TIME UTILS
# -------------------------------------------------------------------
def human_time(seconds):
    """Return formatted HH:MM:SS."""
    try:
        return time.strftime("%H:%M:%S", time.gmtime(seconds))
    except Exception:
        return "Unknown"


# -------------------------------------------------------------------
# UNDO STORAGE INTEGRATION
# -------------------------------------------------------------------
def write_undo_operation(operations):
    """
    operations = [ {src:..., dest:...}, ... ]
    Delegate to undo.py storage system.
    """
    from undo import read_store, write_store
    store = read_store()
    arr = store.get("ops", [])
    arr.append(operations)
    store["ops"] = arr
    write_store(store)

