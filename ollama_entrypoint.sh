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

echo "🔴 Retrieve model..."
ollama pull granite4.1:8b
echo "🟢 Done!"

# Wait for Ollama process to finish.
wait $pid

