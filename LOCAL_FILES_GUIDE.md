# Local Zoom Recording Support

Great news! Zoom Insights now supports processing **locally saved Zoom recordings** without needing a Zoom Pro+ account or cloud API access.

## TL;DR - Quick Start

```bash
# 1. Set your Groq API key (only requirement!)
export GROQ_API_KEY="gsk_your_key_here"

# 2. Process a local recording
zoom-insights ~/Downloads/recording.mp4 --local

# 3. View the report
cat output/recording/report.md
```

That's it! No Zoom credentials needed.

## What Changed?

### New CLI Flags

```bash
zoom-insights <file_path> --local [options]
```

| Flag | Description |
|------|-------------|
| `--local` | Enable local file mode (required for local files) |
| `--title "Custom Title"` | Override meeting title (optional; defaults to filename) |
| `--debug` | Enable debug logging (optional) |

### New Features

- ✅ Process any audio/video file (MP4, M4A, MOV, MP3, WAV, etc.)
- ✅ No Zoom Pro+ plan required
- ✅ No Zoom credentials needed (only Groq API key)
- ✅ Batch process multiple recordings
- ✅ Same high-quality insights as cloud version
- ✅ Automatic cleanup of temporary files
- ✅ Idempotency (skip already-processed files)

## Usage Examples

### Single File

```bash
# Basic
zoom-insights ~/Downloads/team_meeting.mp4 --local

# With custom title
zoom-insights ~/Downloads/meeting.mp4 --local --title "Q4 Planning"

# With debug logging
zoom-insights ~/Downloads/meeting.mp4 --local --debug
```

### Batch Processing

Use the provided script:

```bash
# Process all MP4/M4A files in a directory
scripts/process_local_recordings.sh ~/Zoom_Recordings

# With debug output
scripts/process_local_recordings.sh ~/Zoom_Recordings --debug
```

Or create your own bash loop:

```bash
export GROQ_API_KEY="gsk_..."

for file in ~/Recordings/*.mp4; do
  echo "Processing $file..."
  zoom-insights "$file" --local
done
```

## How It Works

The local mode skips these steps:
- ❌ Zoom OAuth authentication
- ❌ Cloud recording listing/fetching
- ❌ Downloading from Zoom servers

And goes directly to:
1. **Copy** file to work directory
2. **Compress** to 16kHz mono Opus (~90% size reduction)
3. **Segment** if file is over 24 MB
4. **Transcribe** using Groq Whisper
5. **Analyze** using map-reduce with Groq LLM
6. **Report** (Markdown + JSON + text)
7. **Cleanup** temporary files

## Supported File Formats

Works with any format ffmpeg supports:

**Video:**
- MP4, MOV, MKV, AVI, FLV, WebM, 3GP

**Audio:**
- M4A, MP3, WAV, OGG, FLAC, OPUS, AAC, ALAC

**Zoom native formats:**
- `.mp4` (video recording, standard)
- `.m4a` (audio-only recording)

## Configuration

### Environment Variables Required

```bash
# Always required
export GROQ_API_KEY="gsk_your_groq_key"

# Optional (defaults shown)
export LOG_LEVEL="INFO"  # or DEBUG, WARNING, ERROR
```

### No .env File Needed

For local-only processing, you don't need a `.env` file. Just set `GROQ_API_KEY`:

```bash
export GROQ_API_KEY="gsk_xxx"
zoom-insights recording.mp4 --local
```

## Output Structure

```
output/
└── recording/                    # Sanitized from --title or filename
    ├── report.md                 # Human-readable markdown
    ├── insights.json             # Machine-readable JSON
    └── transcript.txt            # Full meeting transcript
```

### Example report.md

```markdown
# Team Standup - Dec 15

## Summary
Quick sync on Q4 priorities and blockers. Discussed timeline and team capacity.

## Key Points
- Q4 budget approved ($2M)
- Timeline: Oct-Dec 2024
- 3 new hires starting next month

## Decisions
- Approved Q4 roadmap
- Postponed feature X to Q1 2025

## Action Items
- **Alice** — Finalize budget docs (due: 2024-12-20)
- **Unassigned** — Send team kickoff invite

## Open Questions
- Overseas hiring approval status?

## Notable Quotes
> "We need to ship this by EOQ, but not at the cost of quality."
```

## Troubleshooting

### "File not found"
```bash
# Use absolute path
zoom-insights /Users/name/Downloads/recording.mp4 --local

# Or from file's directory
cd ~/Downloads
zoom-insights ./recording.mp4 --local
```

### "Unknown file type"
Ensure file is a valid audio/video format. Test with ffmpeg:
```bash
ffprobe recording.mp4
ffmpeg -i recording.mp4 -f null -  # Validate without writing
```

### "File already processed"
Remove from idempotency log:
```bash
rm work/completed.log
zoom-insights recording.mp4 --local
```

### "Transcription takes too long"
Long recordings (>1 hour) are segmented into 15-minute chunks. Groq free tier has rate limits (~6,000 tokens/min). This is normal and tool auto-retries with backoff.

**Tip:** Process during off-peak hours to avoid rate limiting.

### "Out of memory" on very large files
If you have a multi-hour recording:
1. Pre-split with ffmpeg: `ffmpeg -i big.mp4 -segment_time 1800 -c copy out%03d.mp4`
2. Process each segment separately
3. Combine transcripts manually

## Performance Notes

| File Size | Time Estimate |
|-----------|---------------|
| 30 min (100-200 MB) | 10-15 minutes |
| 1 hour (300-500 MB) | 20-30 minutes |
| 2 hours (800 MB+) | 45-60 minutes |

*Times vary based on:*
- Groq rate limiting (6,000 tokens/min)
- File complexity (audio quality, speech rate)
- System specs (CPU for ffmpeg compression)

## When to Use What

| Mode | When to Use | Requirements |
|------|-----------|---|
| **Cloud** (`zoom-insights 0`) | Access Zoom cloud recordings | Zoom Pro+, OAuth setup |
| **Local** (`--local`) | Process downloaded files | Just Groq API key |
| **Both** | Flexible workflow | Both setups |

## Limits & Gotchas

### File Size
- Max upload to Groq: 25 MB (auto-compressed before)
- Practical limit: Anything < 500 MB works fine
- Very large files (>1 GB): consider pre-segmenting

### Accuracy
- Depends on audio quality (noise, accents, speed)
- Works best with clear speech at normal pace
- Multi-speaker meetings: no speaker labels (future feature)

### Rate Limiting
- Groq free tier: ~6,000 tokens/minute for LLM
- Tool retries automatically with exponential backoff
- Batch processing: add `sleep 5` between files

## Privacy

**Local mode is VERY private:**
- Audio never touches Zoom servers
- Only sent to Groq (same as cloud mode)
- Transcripts and insights generated locally
- Work files cleaned up automatically
- Completed log is optional (rm `work/completed.log` to disable)

See main [README.md](README.md#privacy-note) for Groq privacy details.

## Advanced: Custom Batch Processing

Create `my_batch.sh`:

```bash
#!/bin/bash
set -e

GROQ_API_KEY="${GROQ_API_KEY:?Error: Set GROQ_API_KEY}"

RECORDINGS=(
    "~/Downloads/meeting_1.mp4:Q4 Planning"
    "~/Downloads/meeting_2.mp4:Team Standup"
    "~/Downloads/meeting_3.mp4:Product Roadmap"
)

for entry in "${RECORDINGS[@]}"; do
    IFS=':' read -r file title <<< "$entry"
    echo "Processing: $title"
    zoom-insights "$file" --local --title "$title"
done
```

Then run:
```bash
chmod +x my_batch.sh
./my_batch.sh
```

## Questions?

- 📖 See main [README.md](README.md)
- 🐛 Check troubleshooting section
- 📝 Run with `--debug` for detailed logs
- 💬 All tests pass: `pytest tests/ -q`

---

Happy transcribing! 🎉
