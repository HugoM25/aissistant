# backend/src/main.py
import os
import httpx
from fastapi import FastAPI, HTTPException
from typing import Dict

# --- Configuration ---
# Read service URLs from environment variables set in docker-compose.yml
LLM_URL = os.getenv("LLM_URL", "http://llm_service:11434")

# --- FastAPI Setup ---
app = FastAPI(title="LLM Connection Test Backend")
http_client = httpx.Client(timeout=120.0) # Using a synchronous client for simplicity

SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Provide clear and concise answers. Like someone speaking "
)


# --- Core Functionality ---

def get_llm_response(prompt: str) -> str:
    """Calls the local Ollama service and returns the response."""
    try:
        # 1. Define the API request payload
        payload = {
            "model": "my-custom-qwen", 
            "prompt": prompt, 
            "stream": False 
        }
        
        # 2. Send the POST request to the Ollama container via the internal network URL
        response = http_client.post(
            f"{LLM_URL}/api/generate",
            json=payload
        )
        response.raise_for_status() # Raise exception for 4xx or 5xx errors
        
        # 3. Parse the response and extract the generated text
        return response.json().get("response", "ERROR: LLM returned empty response field.")
        
    except httpx.ConnectError:
        return f"ERROR: Could not connect to LLM service at {LLM_URL}. Check Docker network/ports."
    except httpx.HTTPStatusError as e:
        return f"ERROR: LLM API returned status {e.response.status_code}. Response: {e.response.text}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"

# --- API Endpoints ---

@app.get("/")
def check_health() -> Dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "Backend API running", "LLM_Target": LLM_URL}

@app.get("/llm-test")
def llm_test_endpoint() -> Dict[str, str]:
    """Tests the full connection to the LLM service."""
    
    test_prompt = "Say 'Hello, LLM world!' and nothing else."
    
    # Get the response from the LLM container
    llm_output = get_llm_response(test_prompt)
    
    # Check if the connection failed
    if llm_output.startswith("ERROR"):
        raise HTTPException(status_code=503, detail=llm_output)
    
    return {"prompt_sent": test_prompt, "llm_response": llm_output}

@app.get("/llm-custom-test")
def llm_custom_test_endpoint() -> Dict[str, str]:
    """Tests the LLM service with a custom prompt."""
    
    custom_prompt = "Provide a brief summary of the benefits of using FastAPI for building APIs."
    
    # Get the response from the LLM container
    llm_output = get_llm_response(custom_prompt)
    
    # Check if the connection failed
    if llm_output.startswith("ERROR"):
        raise HTTPException(status_code=503, detail=llm_output)
    
    return {"prompt_sent": custom_prompt, "llm_response": llm_output}