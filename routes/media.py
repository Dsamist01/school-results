from flask import Blueprint, current_app, send_from_directory, abort
from flask_login import login_required

media_bp = Blueprint("media", __name__)


@media_bp.route("/media/<path:filename>")
@login_required
def serve_upload(filename):
    """Serves photos/logos saved under instance/uploads/. Kept behind login
    since these are internal-only school records, not public assets.
    Accepts old-style paths that still have a leading 'uploads/' for
    backward compatibility with images saved before the upload folder
    moved under instance/."""
    if filename.startswith("uploads/"):
        filename = filename[len("uploads/"):]
    try:
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
    except (FileNotFoundError, NotADirectoryError):
        abort(404)
