#!/bin/bash
# Interactive recording selector and processor
# Usage: ./docker/select-and-process.sh [--jira] [--notify WEBHOOK_URL]

JIRA_FLAG=""
NOTIFY_FLAG=""
NOTIFY_URL=""

# Parse optional flags
while [[ $# -gt 0 ]]; do
    case $1 in
        --jira)
            JIRA_FLAG="--jira"
            shift
            ;;
        --notify)
            NOTIFY_FLAG="--notify"
            NOTIFY_URL="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--jira] [--notify WEBHOOK_URL]"
            exit 1
            ;;
    esac
done

# List recent recordings
echo "Fetching recent recordings..."
RECORDINGS=$(docker compose run --rm zoom-insights 2>&1)

# Extract lines that look like recording entries (lines starting with [number])
PARSED=$(echo "$RECORDINGS" | grep -E '^\[[0-9]+\]' || true)

if [ -z "$PARSED" ]; then
    echo "Error: Could not fetch recordings. Make sure your .env is configured correctly."
    echo ""
    echo "Please verify:"
    echo "  1. .env file exists with ZOOM credentials"
    echo "  2. Docker image is built: make build"
    echo "  3. Or try manual mode: make process UUID=<your-uuid>"
    exit 1
fi

# Display recordings with 1-indexed numbering
echo ""
echo "Recent recordings:"
echo "$PARSED" | while read line; do
    echo "  $line"
done
echo ""

# Count total recordings
COUNT=$(echo "$PARSED" | wc -l)

# Prompt user to select by index
read -p "Select recording index (0-$((COUNT-1))): " SELECTED_INDEX

# Validate selection
if ! [[ "$SELECTED_INDEX" =~ ^[0-9]+$ ]] || [ "$SELECTED_INDEX" -lt 0 ] || [ "$SELECTED_INDEX" -gt "$((COUNT-1))" ]; then
    echo "Invalid selection."
    exit 1
fi

# Extract the selected line
SELECTED_LINE=$(echo "$PARSED" | sed -n "$((SELECTED_INDEX+1))p")

# Extract UUID from the selected line (everything after the last space or in parentheses)
# Format expected: "[0] 2024-01-15 Meeting Title (uuid-string)" or "[0] 2024-01-15 uuid-string"
SELECTED_UUID=$(echo "$SELECTED_LINE" | grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|/[a-zA-Z0-9=]+' | head -1)

if [ -z "$SELECTED_UUID" ]; then
    echo "Error: Could not extract UUID from selected recording."
    echo "Selected line: $SELECTED_LINE"
    exit 1
fi

echo ""
echo "Processing: $SELECTED_LINE"
echo ""

# Run the process command with selected UUID
CMD="docker compose run --rm zoom-insights '$SELECTED_UUID'"

if [ -n "$JIRA_FLAG" ]; then
    CMD="$CMD --jira"
fi

if [ -n "$NOTIFY_FLAG" ]; then
    CMD="$CMD --notify '$NOTIFY_URL'"
fi

eval "$CMD"
