# Source - https://stackoverflow.com/a/78501628
# Posted by datawookie
# Retrieved 2026-05-09, License - CC BY-SA 4.0

#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

# Parse LLM Model from environment variable
llm_name=""
if [ -n "$LLM_MODEL" ]; then
    if [[ $LLM_MODEL == */* ]]; then
        if [[ $LLM_MODEL == ollama_chat/* ]]; then
            llm_name="${LLM_MODEL#ollama_chat/}"
        elif [[ $LLM_MODEL == ollama/* ]]; then
            llm_name="${LLM_MODEL#ollama/}"
        fi
    else
        llm_name="$LLM_MODEL"
    fi
fi

# Fallback to default if no valid Ollama LLM model was configured
if [ -z "$llm_name" ]; then
    llm_name="gemma4:31b"
fi

# Parse Embedder Model from environment variable
embedder_name=""
if [ -n "$MEM0_EMBEDDER_MODEL" ]; then
    if [[ $MEM0_EMBEDDER_MODEL == */* ]]; then
        if [[ $MEM0_EMBEDDER_MODEL == ollama_chat/* ]]; then
            embedder_name="${MEM0_EMBEDDER_MODEL#ollama_chat/}"
        elif [[ $MEM0_EMBEDDER_MODEL == ollama/* ]]; then
            embedder_name="${MEM0_EMBEDDER_MODEL#ollama/}"
        fi
    else
        embedder_name="$MEM0_EMBEDDER_MODEL"
    fi
fi

echo "🔴 Retrieve LLM model: $llm_name..."
ollama pull "$llm_name"

if [ -n "$embedder_name" ]; then
    echo "🔴 Retrieve Embedder model: $embedder_name..."
    ollama pull "$embedder_name"
fi

echo "🟢 Done!"

# Wait for Ollama process to finish.
wait $pid

