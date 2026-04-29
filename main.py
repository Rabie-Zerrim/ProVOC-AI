import os
import uuid
import whisper
import torch
import time
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

from database import get_milvus
from config import OPENAI_API_KEY, JWT_SECRET, ALGORITHM

# Import routers
from auth import router as auth_router, get_current_user
from yelp import router as yelp_router
from lists import router as lists_router
from memos import router as memos_router
from tasks import router as tasks_router

load_dotenv()

from groq import Groq
from config import GROQ_API_KEY
client_ai = Groq(api_key=GROQ_API_KEY)
milvus_client = get_milvus()

# Whisper Model
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading Whisper on {device}...")
whisper_model = whisper.load_model("tiny").to(device)

app = FastAPI(title="Focusaurus LIGHT-MODE (Zero-DB) Backend")

from fastapi import Request
import time

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    print(f"DEBUG: Incoming {request.method} to {request.url.path}")
    response = await call_next(request)
    process_time = time.time() - start_time
    print(f"DEBUG: Finished {request.method} {request.url.path} in {process_time:.2f}s with status {response.status_code}")
    return response

@app.get("/api/health-check/transcribe")
async def health_check():
    return {
        "status": "ok", 
        "whisper": "ready", 
        "device": str(device),
        "db_mode": "no-database-mock"
    }

# Register Routers
app.include_router(auth_router)
app.include_router(yelp_router)
app.include_router(lists_router)
app.include_router(memos_router)
app.include_router(tasks_router)

# CORS PROMISCUOUS MODE FOR TESTING
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# AI Assistant Logic
async def analyze_with_gpt(prompt: str, context: str = ""):
    try:
        response = client_ai.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant for Focusaurus."},
                {"role": "user", "content": f"{context}\n\nTask: {prompt}"}
            ],
            temperature=0.7,
            max_tokens=300
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Response (Placeholder): {prompt[:50]}..."

# Routes
from fastapi import Form

@app.post("/api/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...), 
    language: str = Form("auto"),
    task: str = Form("transcribe")
):
    temp_filename = f"temp_{uuid.uuid4()}.webm"
    try:
        with open(temp_filename, "wb") as buffer:
            content = await audio.read()
            buffer.write(content)
        
        options = {}
        if language != "auto": options["language"] = language
        options["task"] = task
        
        print(f"Whisper processing: lang={language}, task={task}")
        result = whisper_model.transcribe(temp_filename, **options)
        return {
            "success": True, 
            "transcription": result["text"].strip(),
            "language": result.get("language", "unknown")
        }
    except Exception as e:
        print(f"Whisper Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

@app.get("/api/pending-reviews")
async def get_root_pending_reviews():
    """MODE NO-DB : Retourne une liste vide pour éviter les erreurs segcore"""
    return []

@app.post("/api/record-review")
async def record_root_review(businessId: str, businessName: str, reviewText: str):
    """MODE NO-DB : Succès automatique"""
    return {"success": True, "reviewId": str(uuid.uuid4())}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
