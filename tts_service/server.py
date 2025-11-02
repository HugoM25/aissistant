import os
import io
import time
import wave
from typing import Dict, Any, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from piper.voice import PiperVoice 

# --- 1. Configuration ---

# These paths MUST match the files copied into the /app directory in Dockerfile.tts
MODEL_PATH = "/app/fr_FR-siwis-medium.onnx" 
CONFIG_PATH = "/app/fr_FR-siwis-medium.json" 
VOICE_NAME = "fr_FR-siwis-medium"

# --- 2. Model Initialization ---

voice_engine: Union[PiperVoice, None] = None

try:
    start_time = time.time()
    print(f"Loading Piper TTS Model from path: {MODEL_PATH}")
    
    # Load the Voice configuration and engine instance
    voice_engine = PiperVoice.load(MODEL_PATH, CONFIG_PATH)
    
    print(f"Model loaded successfully in {round(time.time() - start_time, 2)} seconds.")
except Exception as e:
    # Log the failure but allow the API to start up to serve the health check
    print(f"FATAL ERROR LOADING PIPER TTS MODEL. Check model files: {e}")
    # The 'voice_engine' remains None if loading fails.

# --- 3. API Input Model ---

class TTSRequest(BaseModel):
    text: str
    speaker_id: int = 0

# --- 4. Synchronous Core Logic (The function that runs off the main thread) ---

def perform_synthesis_sync(text: str, file_handle: io.BytesIO):
    """
    Synchronous function that calls the blocking Piper method safely.
    It raises a standard exception if synthesis fails.
    """
    if not voice_engine:
         raise RuntimeError("TTS engine is not initialized.")
         
    # We rely on the caller to ensure this model is single-speaker, 
    # so we do not pass the speaker_id argument.
    
    try:
        with wave.open(file_handle, 'wb') as wav_file:
            # Perform the synthesis call
            voice_engine.synthesize(
                text, 
                wav_file
            )
    except Exception as e:
        # Catch any low-level exception from C++ or Piper and re-raise as Python error
        raise RuntimeError(f"Piper synthesis failed during execution: {e}")


# --- 5. FastAPI Setup and Endpoints ---

app = FastAPI(title="Piper TTS Service")

@app.get("/")
def health_check() -> Dict[str, Union[str, bool]]:
    """Confirms the API is running and model status."""
    return {
        "status": "ok" if voice_engine else "error", 
        "model_loaded": bool(voice_engine),
        "voice_name": VOICE_NAME
    }

@app.post("/synthesize") # REMOVED response_class=dict
async def synthesize_speech(request: TTSRequest):
    """Generates audio for the given text and returns it as a hex string."""
    if not voice_engine: 
        raise HTTPException(status_code=503, detail="TTS model failed to load or initialize.")
    
    start_time = time.time()
    
    try:
        audio_stream = io.BytesIO()
        
        # CRITICAL: Execute the synchronous logic off the main thread
        await run_in_threadpool(
            perform_synthesis_sync,
            request.text,
            audio_stream
        )
        
        # Get the raw WAV audio data
        wav_bytes = audio_stream.getvalue()
        
        return {
            "status": "success",
            "audio_bytes_hex": wav_bytes.hex(),
            "message": f"Synthesized {len(wav_bytes)} bytes of audio.",
            "inference_time_s": round(time.time() - start_time, 3)
        }
    except RuntimeError as e:
        # Catch the specific RuntimeError raised from the synthesis thread
        print(f"TTS Synthesis Runtime Error: {e}")
        # Convert it to a proper FastAPI HTTPException
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {e}")
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected Error: {e}")
        raise HTTPException(status_code=500, detail=f"An unknown error occurred: {e}")