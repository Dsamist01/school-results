import io
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime

from flask import current_app


def build_backup_zip():
    """Builds an in-memory zip containing a safe, consistent copy of the live
    SQLite database plus every uploaded logo/student photo. Uses SQLite's
    online backup API (rather than a raw file copy) so a backup taken while
    the app is being actively used can't end up corrupted or half-written.

    Returns (buffer, filename).
    """
    root = current_app.root_path
    db_path = os.path.join(root, "instance", "results.db")
    uploads_dir = os.path.join(root, "instance", "uploads")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(db_path):
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".db")
                os.close(fd)
                src_conn = sqlite3.connect(db_path)
                dest_conn = sqlite3.connect(tmp_path)
                with dest_conn:
                    src_conn.backup(dest_conn)
                src_conn.close()
                dest_conn.close()
                zf.write(tmp_path, arcname="results.db")
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

        if os.path.exists(uploads_dir):
            for dirpath, _dirnames, filenames in os.walk(uploads_dir):
                for fname in filenames:
                    if fname == ".gitkeep":
                        continue
                    full_path = os.path.join(dirpath, fname)
                    arcname = os.path.join("uploads", os.path.relpath(full_path, uploads_dir))
                    zf.write(full_path, arcname=arcname)

    buf.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"school_results_backup_{timestamp}.zip"
    return buf, filename
