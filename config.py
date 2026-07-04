import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "results.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB upload limit

    # School identity defaults (editable later in Admin > School Settings)
    SCHOOL_NAME = os.environ.get("SCHOOL_NAME", "Your School Name")
    MAX_CLASSES = 20

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
    MAX_IMAGE_SIZE_MB = 3
