#!/bin/bash
set -e 

MODEL_NAME="my-custom-qwen"
MODEL_PATH="/tmp/Modelfile" 

echo "--- Starting LLM Service Setup ---"

# 1. Start Ollama server in the background
echo "1. Starting Ollama server in background (PID recording)..."
# Use 'exec' to replace the current shell process with ollama serve,
# but we need it running in the background for setup, so we use '&'
ollama serve &
OLLAMA_PID=$!

# 2. Wait for the server to become responsive internally
echo "2. Waiting for Ollama CLI to connect to the server..."
# The 'ollama list' command requires the server to be fully initialized.
# We loop until the command succeeds (exit code 0).
until ollama list > /dev/null 2>&1; do
    echo "   ... server starting, waiting 1s"
    sleep 1
done
echo "   ... Ollama server is ready."

# 3. Check if the custom model is registered, and if not, create it
if ! ollama show "$MODEL_NAME" > /dev/null 2>&1; then
    echo "3. Model '$MODEL_NAME' not found. Creating it now..."
    
    # Register the model. This is the setup step.
    ollama create "$MODEL_NAME" -f "$MODEL_PATH"
    
    echo "   ... Model '$MODEL_NAME' created successfully."
else
    echo "3. Model '$MODEL_NAME' already exists. Skipping creation."
fi

# 4. Stop the temporary background process
echo "4. Setup complete. Stopping temporary background server (PID: $OLLAMA_PID)."
kill $OLLAMA_PID
# Wait for the background process to actually exit
wait $OLLAMA_PID 2>/dev/null || true

echo "5. Starting Ollama server in foreground (main process)..."
# 5. Execute the final command to start the server in the foreground
# This keeps the container running and ready to serve requests.
exec ollama serve