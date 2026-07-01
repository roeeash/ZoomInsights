#!/bin/bash
#
# Batch process local Zoom recordings
# Usage: ./process_local_recordings.sh /path/to/recordings/folder [--debug]
#

set -e

RECORDINGS_DIR="${1:-.}"
DEBUG_FLAG="${2:-}"

if [ ! -d "$RECORDINGS_DIR" ]; then
    echo "Error: Directory not found: $RECORDINGS_DIR"
    echo "Usage: $0 /path/to/recordings [--debug]"
    exit 1
fi

# Check Groq API key is set
if [ -z "$GROQ_API_KEY" ]; then
    echo "Error: GROQ_API_KEY environment variable not set"
    echo "Set it with: export GROQ_API_KEY='your_key_here'"
    exit 1
fi

echo "Processing Zoom recordings in: $RECORDINGS_DIR"
echo "=========================================="

# Count files
TOTAL=$(find "$RECORDINGS_DIR" -maxdepth 1 -type f \( -iname "*.mp4" -o -iname "*.m4a" -o -iname "*.mov" \) | wc -l)

if [ "$TOTAL" -eq 0 ]; then
    echo "No recordings found in $RECORDINGS_DIR"
    echo "Looking for: .mp4, .m4a, .mov files"
    exit 0
fi

echo "Found $TOTAL recording(s)"
echo ""

COUNT=0
for file in "$RECORDINGS_DIR"/*.mp4 "$RECORDINGS_DIR"/*.m4a "$RECORDINGS_DIR"/*.mov; do
    [ -e "$file" ] || continue

    COUNT=$((COUNT + 1))
    FILENAME=$(basename "$file")
    TITLE="${FILENAME%.*}"  # Remove extension

    echo "[$COUNT/$TOTAL] Processing: $FILENAME"

    # Process with zoom-insights
    if zoom-insights "$file" --local --title "$TITLE" $DEBUG_FLAG; then
        echo "✓ Completed: $TITLE"
        echo ""
    else
        echo "✗ Failed: $FILENAME (check logs with --debug flag)"
        echo ""
    fi

    # Small delay to avoid rate limiting
    sleep 2
done

echo "=========================================="
echo "Batch processing complete!"
echo "Results saved to: output/"
echo ""
echo "View reports:"
echo "  ls -la output/"
echo "  open output/*/report.md  (macOS)"
echo "  xdg-open output/*/report.md  (Linux)"
