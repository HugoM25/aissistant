# backend/src/main.py
import os
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from urllib.parse import quote


from agent import Agent

# --- Configuration ---
# Read service URLs from environment variables set in docker-compose.yml
LLM_URL = os.getenv("LLM_URL", "http://llm_service:11434")
STT_URL = os.getenv("STT_URL", "http://stt_service:5000")
TTS_URL = os.getenv("TTS_URL", "http://tts_service:5001")

# --- FastAPI Setup ---
app = FastAPI(title="LLM Connection Test Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Transcribed-Text", "X-LLM-Response"],  # Expose custom headers
)
http_client = httpx.Client(timeout=120.0) # Using a synchronous client for simplicity

SYSTEM_PROMPT = """
You are a highly capable and helpful home assistant. Your primary goal is to fulfill user requests. Do not use emojis in your responses.
"""

# --- Core Functionality ---
@app.get("/health")
def health_check():
    """Health check endpoint to verify backend and service connectivity."""
    status = {
        "backend": "ok",
        "llm_service": "unknown",
        "stt_service": "unknown",
        "tts_service": "unknown"
    }
    
    # Check LLM ollama service
    try:
        llm_response = http_client.get(f"{LLM_URL}/api/version")
        if llm_response.status_code == 200:
            status["llm_service"] = "ok"
    except Exception as e:
        status["llm_service"] = f"error: {str(e)}"

    # Check STT service
    try:
        stt_response = http_client.get(f"{STT_URL}/")
        status["stt_service"] = stt_response.json().get("status", "error")
    except Exception as e:
        status["stt_service"] = f"error: {str(e)}"
    
    # Check TTS service
    try:
        tts_response = http_client.get(f"{TTS_URL}/")
        status["tts_service"] = tts_response.json().get("status", "error")
    except Exception as e:
        status["tts_service"] = f"error: {str(e)}"
    
    return status

def get_transcription(client: httpx.Client, stt_url: str, audio_bytes: bytes, filename: str, content_type: str) -> str:
    files = {
        "audio_file": (filename or "recording.wav", audio_bytes, content_type or "audio/wav")
    }
    print(f"Sending audio to STT service: {stt_url}/transcribe")
    resp = client.post(f"{stt_url}/transcribe", files=files)
    print(f"STT Response status: {resp.status_code}")
    print(f"STT Response: {resp.text}")
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"STT service failed: {resp.text}")
    data = resp.json()
    transcribed = data.get("result", "") or data.get("text", "")
    if not transcribed:
        raise HTTPException(status_code=400, detail="No text transcribed from audio")
    return transcribed

def get_agent_answer(client: httpx.Client, llm_url: str, transcribed_text: str, model_name: str = "my-custom-qwen:latest") -> str:
    payload = {
        "model": model_name,
        "prompt": f"{SYSTEM_PROMPT}\n\nUser: {transcribed_text}\n\nAssistant:",
        "stream": False
    }
    print(f"Sending to LLM service: {llm_url}/api/generate")
    resp = client.post(f"{llm_url}/api/generate", json=payload)
    print(f"LLM Response status: {resp.status_code}")
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"LLM service failed: {resp.text}")
    llm_text = resp.json().get("response", "") or resp.json().get("text", "")
    if not llm_text:
        raise HTTPException(status_code=500, detail="No response from LLM")
    return llm_text

def generate_voice(client: httpx.Client, tts_url: str, text: str, speaker_id: int = 0) -> bytes:
    payload = {"text": text, "speaker_id": speaker_id}
    print(f"Sending to TTS service: {tts_url}/synthesize")
    resp = client.post(f"{tts_url}/synthesize", json=payload, headers={"Content-Type": "application/json"})
    print(f"TTS Response status: {resp.status_code}")
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"TTS service failed: {resp.text}")
    data = resp.json()
    if data.get("status") == "success":
        audio_hex = data.get("audio_bytes_hex")
        if not audio_hex:
            raise HTTPException(status_code=500, detail="TTS returned success but no audio_bytes_hex")
        audio_bytes = bytes.fromhex(audio_hex)
        print(f"Decoded audio size: {len(audio_bytes)} bytes")
        return audio_bytes
    else:
        error_detail = data.get("detail", "Unknown TTS error")
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {error_detail}")


@app.post("/process-audio")
async def process_audio(audio: UploadFile = File(...)):
    """
    Complete audio processing pipeline using extracted helpers:
    1. Transcribe audio using STT service
    2. Generate response using LLM service
    3. Convert response to speech using TTS service
    4. Return audio file
    """
    try:
        audio_content = await audio.read()
        transcribed_text = get_transcription(http_client, STT_URL, audio_content, audio.filename or "recording.wav", audio.content_type or "audio/wav")
        print(f"Transcribed text: {transcribed_text}")

        llm_text = get_agent_answer(http_client, LLM_URL, transcribed_text)
        print(f"LLM Response: {llm_text}")

        audio_bytes = generate_voice(http_client, TTS_URL, llm_text, speaker_id=0)

        return Response(
            content=audio_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=response.wav",
                "Content-Length": str(len(audio_bytes)),
                "X-Transcribed-Text": quote(transcribed_text),
                "X-LLM-Response": quote(llm_text)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing audio: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")