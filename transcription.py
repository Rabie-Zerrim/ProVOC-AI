import os
import uuid
import asyncio
import whisper
import torch
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from groq import Groq

from config import ACCEPTED_LANGUAGES, WHISPER_MODEL, GROQ_API_KEY

router = APIRouter(prefix="/api", tags=["transcription"])

USE_GROQ_WHISPER = os.getenv("GROQ_WHISPER", "false").lower() == "true"
_groq_whisper = Groq(api_key=GROQ_API_KEY)

device = "cuda" if torch.cuda.is_available() else "cpu"
if not USE_GROQ_WHISPER:
    print(f"Loading Whisper on {device}...")
    whisper_model = whisper.load_model(WHISPER_MODEL).to(device)
else:
    whisper_model = None

USE_FINETUNED = os.getenv("USE_FINETUNED_WHISPER", "false").lower() == "true"
FINETUNED_PATH = os.getenv("FINETUNED_WHISPER_PATH", "./whisper-provoc-small/final")

ft_processor = None
ft_model = None

if USE_FINETUNED and os.path.exists(FINETUNED_PATH):
    from transformers import WhisperProcessor, WhisperForConditionalGeneration
    print(f"Loading fine-tuned Whisper from {FINETUNED_PATH}...")
    ft_processor = WhisperProcessor.from_pretrained(FINETUNED_PATH)
    ft_model = WhisperForConditionalGeneration.from_pretrained(
        FINETUNED_PATH).to(device)
    print("Fine-tuned Whisper loaded.")
else:
    print(f"Using baseline Whisper {WHISPER_MODEL}")


def _write_file(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


@router.get("/health-check/transcribe")
async def health_check() -> dict:
    if USE_FINETUNED and ft_model is not None:
        model_label = "fine-tuned whisper-provoc-v1"
        finetuned_active = True
    else:
        model_label = f"baseline whisper-{WHISPER_MODEL}"
        finetuned_active = False
    return {
        "status": "ok",
        "whisper": "loaded",
        "model": model_label,
        "finetuned": finetuned_active,
        "device": str(device),
        "db_mode": "no-database-mock",
    }


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str = Form("auto"),
    task: str = Form("transcribe"),
) -> dict:
    if language != "auto" and language not in ACCEPTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Language must be 'auto' or one of: {', '.join(ACCEPTED_LANGUAGES)}",
        )
    temp_filename = f"temp_{uuid.uuid4()}.webm"
    try:
        content = await audio.read()
        await asyncio.to_thread(_write_file, temp_filename, content)

        if USE_GROQ_WHISPER:
            with open(temp_filename, "rb") as f:
                filename = audio.filename or temp_filename
                safe_filename = filename if filename.endswith(('.m4a', '.mp3', '.wav', '.mp4', '.webm')) else filename + '.m4a'
                groq_result = _groq_whisper.audio.transcriptions.create(
                    file=(safe_filename, f.read()),
                    model="whisper-large-v3-turbo",
                    response_format="verbose_json",
                )
            print(f"[groq] transcription text: '{groq_result.text}'")
            print(f"[groq] transcription language: '{groq_result.language}'")
            transcription = groq_result.text.strip()
            _lang_map = {"english": "en", "french": "fr", "spanish": "es"}
            detected_language = _lang_map.get(groq_result.language, groq_result.language)
            confidence = None
            print(f"Groq Whisper: lang={detected_language}")
        elif USE_FINETUNED and ft_model is not None:
            import librosa
            import numpy as np
            audio_array, _ = librosa.load(temp_filename, sr=16000)
            inputs = ft_processor(
                audio_array, sampling_rate=16000, return_tensors="pt"
            ).input_features.to(device)
            with torch.no_grad():
                output = ft_model.generate(
                    inputs,
                    return_dict_in_generate=True,
                    output_scores=True,
                    max_new_tokens=128,
                )
            transcription = ft_processor.batch_decode(
                output.sequences, skip_special_tokens=True
            )[0].strip()
            # compute_transition_scores handles the forced-prefix offset correctly
            transition_scores = ft_model.compute_transition_scores(
                output.sequences, output.scores, normalize_logits=True
            )
            avg_logprob = transition_scores[0].mean().item()
            confidence = round(float(np.exp(avg_logprob)) * 100, 1)
            detected_language = language if language != "auto" else "en"
            print(f"Fine-tuned Whisper processing: lang={language}, confidence={confidence}%")
        else:
            options = {}
            if language != "auto":
                options["language"] = language
            options["task"] = task
            print(f"Whisper processing: lang={language}, task={task}")
            result = whisper_model.transcribe(temp_filename, **options)
            transcription = result["text"].strip()
            detected_language = result.get("language", "unknown")
            import numpy as np
            confidence = round(float(np.exp(result.get("avg_logprob", -1))) * 100, 1)
            print(f"Baseline Whisper: lang={detected_language}, confidence={confidence}%")

        if detected_language not in ACCEPTED_LANGUAGES:
            return {
                "success": False,
                "error": f"Detected language '{detected_language}' is not supported. Please speak in English, French, or Spanish.",
            }
        return {
            "success": True,
            "transcription": transcription,
            "language": detected_language,
            "confidence": confidence,
        }
    except Exception as e:
        print(f"Whisper Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
