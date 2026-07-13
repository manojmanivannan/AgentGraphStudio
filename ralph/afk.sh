#!/bin/bash
set -eo pipefail

if [ -z "$1" ]; then
    echo "Usage: $0 <iterations>"
    exit 1
fi

for ((i=1; i<=$1; i++)); do

    commits=$(git log -n 5 --format="%H%n%ad%n%B---" --date=short 2>/dev/null || echo "No commits found")
    issues=$(cat issues/*.md 2>/dev/null || echo "No issues found")
    prompt=$(cat ralph/prompt.md)

    full_prompt=$(cat <<EOF
Previous commits:

$commits

Issues:

$issues

$prompt
EOF
)

    result=$(copilot --allow-all -p "$full_prompt")

    echo "$result"

    if [[ "$result" == *"<promise>NO MORE TASKS</promise>"* ]]; then
        echo "Ralph complete after $i iterations."
        exit 0
    fi

done