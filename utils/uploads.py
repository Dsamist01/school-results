import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app


def _allowed(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]


def save_image(file_storage, subfolder):
    """Saves an uploaded image under static/uploads/<subfolder>/ with a unique
    filename. Returns the path relative to the static folder (suitable for
    url_for('static', filename=...)) or None if no valid file was given."""
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed(file_storage.filename):
        raise ValueError("Only image files (png, jpg, jpeg, gif, webp) are allowed.")

    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(folder, exist_ok=True)

    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filename = secure_filename(filename)
    full_path = os.path.join(folder, filename)
    file_storage.save(full_path)

    return f"uploads/{subfolder}/{filename}"


def delete_image(relative_path):
    """Deletes a previously saved image given its static-relative path."""
    if not relative_path:
        return
    full_path = os.path.join(current_app.root_path, "static", relative_path)
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass
