"""
Configuration and Environment Settings for DUM DUM Group of Institution College FAQ Agent.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env file
load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)

# College Identity
COLLEGE_NAME = os.getenv("COLLEGE_NAME", "DUM DUM Group of Institution")
COLLEGE_TAGLINE = os.getenv("COLLEGE_TAGLINE", "Excellence in Education, Research & Integrity")
COLLEGE_CODE = os.getenv("COLLEGE_CODE", "DGD-2026")

# Gemini API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODELS_RAW = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite")
FALLBACK_MODELS = [m.strip() for m in FALLBACK_MODELS_RAW.split(",") if m.strip()]

# Storage Paths
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "data/college_faq.db")
UPLOADS_DIR = BASE_DIR / os.getenv("UPLOADS_DIR", "data/uploads")
GENERATED_DOCS_DIR = BASE_DIR / os.getenv("GENERATED_DOCS_DIR", "data/generated_docs")
SAMPLE_DOCS_DIR = BASE_DIR / "sample_docs"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)
SAMPLE_DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Security & Secrets
SESSION_SECRET = os.getenv("SESSION_SECRET", "dumdum-secret-key-default-2026")
PASSWORD_SALT = os.getenv("PASSWORD_SALT", "dumdum-institution-salt-2026")

# Upload Limits
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15"))
ALLOWED_EXTENSIONS = set(
    ext.strip().lower() for ext in os.getenv("ALLOWED_EXTENSIONS", ".pdf,.png,.jpg,.jpeg").split(",") if ext.strip()
)

# Email / SMTP Settings (Human-in-the-Loop Enforced)
SMTP_ENABLED = os.getenv("SMTP_ENABLED", "False").lower() in ("true", "1", "yes")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "office@dumdumgroup.edu")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "office@dumdumgroup.edu")
