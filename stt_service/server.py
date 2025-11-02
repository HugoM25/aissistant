# stt_service/server.py
import os
import uvicorn
import torch
import time
import io
from fastapi import FastAPI, UploadFile, File, HTTPException
from faster_whisper import WhisperModel

# --- Configuration ---
# 1. Define the model path and name (MUST match your volume mount/folder name)
# We assume the model folder is named exactly: models--Systran--faster-whisper-medium
MODEL_FOLDER_NAME = "models--Systran--faster-whisper-medium"
LOCAL_CACHE_ROOT = "/app/hf_cache" # Must match the container mount path in docker-compose.yml
SNAPSHOT_HASH = "08e178d48790749d25932bbc082711ddcfdfbc4f"

LOCAL_MODEL_PATH = os.path.join(
    LOCAL_CACHE_ROOT, 
    MODEL_FOLDER_NAME, 
    "snapshots", 
    SNAPSHOT_HASH
)

# 2. Hardware and Precision settings
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" # Recommended for speed on RTX 3070 Ti

# --- Model Initialization ---
# Initialize model globally to avoid re-loading on every request
model = None
try:
    print(f"Loading Faster Whisper Model from local path: {LOCAL_MODEL_PATH}")
    print(f"Device: {DEVICE}, Compute: {COMPUTE_TYPE}")
    
    # CRITICAL: Pass the local path to the constructor to load the pre-downloaded model
    model = WhisperModel(
        LOCAL_MODEL_PATH, 
        device=DEVICE, 
        compute_type=COMPUTE_TYPE
    )
    print("Model loaded successfully.")
except Exception as e:
    print(f"FATAL ERROR LOADING WHISPER MODEL: {e}")

# --- FastAPI Setup ---
app = FastAPI(title="Faster Whisper STT Service")

@app.get("/")
def health_check():
    """Confirms the API is running and model status."""
    return {
        "status": "ok" if model else "error", 
        "model": MODEL_FOLDER_NAME,
        "device": DEVICE
    }

@app.post("/transcribe")
async def transcribe_audio(
    audio_file: UploadFile = File(...), 
    language: str = None, 
    task: str = "transcribe" # Added 'task' for easy translation testing
) -> dict:
    """Receives an audio file (multipart form data) and returns the text."""
    if not model:
        raise HTTPException(status_code=503, detail="Whisper model failed to load.")
    
    start_time = time.time()
    
    try:
        # Read the file content into an in-memory buffer
        audio_bytes = await audio_file.read()
        audio_io = io.BytesIO(audio_bytes)

        # Faster Whisper processing
        segments, info = model.transcribe(
            audio_io, 
            beam_size=5, 
            language=language if language else None, 
            task=task # Use 'translate' task if requested
        )
        
        full_text = " ".join([segment.text for segment in segments])
        
        return {
            "result": full_text.strip(),
            "language": info.language,
            "inference_time_s": round(time.time() - start_time, 2),
        }
    except Exception as e:
        # Log the error internally
        print(f"Transcription Error: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

# CMD execution is handled by the Dockerfile.