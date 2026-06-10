import os
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

# Secrets
JWT_SECRET = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
YELP_API_KEY = os.getenv("YELP_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Security context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Language settings
ACCEPTED_LANGUAGES = ["en", "es", "fr"]
LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "fr": "French"}

# Runtime configuration
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC")
NO_DB_MODE = os.getenv("NO_DB_MODE", "true").lower() == "true"
BFF_SHARED_SECRET = os.getenv("BFF_SHARED_SECRET")

ALLOWED_AUDIO_EXTENSIONS = [".wav", ".mp3", ".webm", ".ogg", ".m4a", ".mp4", ".flac"]
