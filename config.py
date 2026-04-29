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
