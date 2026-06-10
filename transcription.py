import os
import uuid
import asyncio
from pathlib import Path

import whisper
import torch
from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from config import ACCEPTED_LANGUAGES, WHISPER_MODEL
from audio.processor import AudioProcessor, UnsupportedFormatError
from audio.emotion import EmotionRecognizer

router = APIRouter(prefix="/api", tags=["transcription"])

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Loading Whisper on {device}...")
whisper_model = whisper.load_model(WHISPER_MODEL).to(device)

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

    processor = AudioProcessor()

    # Validate format before touching the file system
    filename = audio.filename or "upload.webm"
    try:
        processor.validate_audio_type(filename, audio.content_type or "")
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ext = Path(filename).suffix or ".webm"
    temp_filename = f"temp_{uuid.uuid4()}{ext}"
    processed_path: str | None = None

    try:
        content = await audio.read()
        await asyncio.to_thread(_write_file, temp_filename, content)

        # Convert to 16 kHz mono WAV and strip leading silence
        processed_path = await asyncio.to_thread(processor.process, temp_filename)

        if USE_FINETUNED and ft_model is not None:
            import librosa
            import numpy as np
            audio_array, _ = librosa.load(processed_path, sr=16000)
            inputs = ft_processor(
                audio_array, sampling_rate=16000, return_tensors="pt"
            ).input_features.to(device)
            with torch.no_grad():
                output = ft_model.generate(
                    inputs,
                    return_dict_in_generate=True,
                    output_scores=True,
                )
            transcription = ft_processor.batch_decode(
                output.sequences, skip_special_tokens=True
            )[0].strip()
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
            result = whisper_model.transcribe(processed_path, **options)
            transcription = result["text"].strip()
            detected_language = result.get("language", "unknown")
            import numpy as np
            confidence = round(float(np.exp(result.get("avg_logprob", -1))) * 100, 1)
            print(f"Baseline Whisper: lang={detected_language}, confidence={confidence}%")

        if detected_language not in ACCEPTED_LANGUAGES:
            return {
                "success": False,
                "error": (
                    f"Detected language '{detected_language}' is not supported. "
                    "Please speak in English, French, or Spanish."
                ),
            }

        # Emotion detection — falls back to neutral if model unavailable
        emotion_recognizer = EmotionRecognizer.get_instance()
        emotion_result = await asyncio.to_thread(
            emotion_recognizer.predict, processed_path
        )

        return {
            "success": True,
            "transcription": transcription,
            "language": detected_language,
            "confidence": confidence,
            "emotion": emotion_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Whisper Error: {e}")
        return {"success": False, "error": str(e)}
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        if processed_path and os.path.exists(processed_path):
            os.remove(processed_path)
