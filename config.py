from pathlib import Path

BASE_DIR = Path(__file__).parent
STORAGE_DIR = BASE_DIR / "storage"
CV_DIR = STORAGE_DIR / "cvs"
LOGO_PATH = STORAGE_DIR / "firecode_logo.png"
DB_PATH = BASE_DIR / "cv_data.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

SECRET_KEY = "firecode-cv-secret-key-change-in-prod"
SESSION_MAX_AGE = 28800  # 8 hours
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
