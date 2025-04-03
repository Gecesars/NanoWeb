# config.py
import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:123@localhost:5432/nanoweb"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Folder to store uploaded antenna files
    UPLOAD_FOLDER = os.path.join("static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # Folder to store calibration files
    CALIBRATION_FOLDER = os.path.join("calibrations")
    if not os.path.exists(CALIBRATION_FOLDER):
        os.makedirs(CALIBRATION_FOLDER)
