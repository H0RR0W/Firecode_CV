import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# On Render: set DATA_DIR=/data (persistent disk mount point)
# Locally: falls back to project directory
_DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR)))

STORAGE_DIR = BASE_DIR / "storage"
CV_DIR = _DATA_DIR / "cvs"
LOGO_PATH = STORAGE_DIR / "firecode_logo.png"
DB_PATH = _DATA_DIR / "cv_data.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

SECRET_KEY = os.environ.get("SECRET_KEY", "firecode-cv-secret-key-change-in-prod")
SESSION_MAX_AGE = 28800  # 8 hours
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
