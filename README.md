# Zoom Insights

Extract structured insights from Zoom Cloud Recordings using free-tier APIs (Groq Whisper + Groq LLM).

## What it does

This tool automates the process of analyzing Zoom meeting recordings:

1. **Downloads** your recording from Zoom Cloud
2. **Compresses** the audio to ~5-10% of original size (16 kHz mono Opus)
3. **Transcribes** using Groq's Whisper (or uses Zoom's optional built-in transcript)
4. **Extracts** structured insights: summary, key points, decisions, action items, questions
5. **Generates** a markdown report + JSON insights file + full transcript

Designed to run entirely on free tiers: Groq free Whisper (~2,000 requests/day) and Groq free LLM (~6,000 tokens/min).

## Why

- **Automation**: Go from recording → report without manual steps
- **Free**: No credit card required; uses free APIs only
- **Privacy**: Zoom + Groq; no third-party storage
- **Structured**: JSON schema for reliably parsing insights
- **Idempotent**: Re-run safely; skips already-processed recordings

## Setup

### Quick Start (Local Files - FREE!)

If you just want to process locally saved recordings:

```bash
# 1. Install
pip install -e .

# 2. Get Groq API key (free)
# Visit: https://console.groq.com

# 3. Set environment variable
export GROQ_API_KEY="your_groq_key_here"

# 4. Process a local file
zoom-insights ~/Downloads/recording.mp4 --local --title "Meeting Title"
```

That's it! No Zoom Pro+ or Zoom credentials needed.

### Full Setup (Zoom Cloud + Local Files)

#### Prerequisites

- Python 3.9+
- **ffmpeg**: `brew install ffmpeg` (macOS), `apt install ffmpeg` (Linux), or [Windows build](https://ffmpeg.org/download.html)
- **Groq API key**: Free tier at [console.groq.com](https://console.groq.com)
- **Zoom account** (optional): Pro+ plan for cloud recordings
  - **Not needed** if you only use local files
  - **Required** only if you want to download from Zoom Cloud

#### One-time Zoom App Setup (Optional - only for Zoom Cloud)

Skip this if you're only processing local files.

1. Go to [Zoom Marketplace → Develop → Build App](https://marketplace.zoom.us/docs/guides/getting-started/app-types/create-server-to-server-oauth-app)
2. Select **Server-to-Server OAuth** app type
3. Copy **Account ID, Client ID, Client Secret**
4. Add OAuth scopes:
   - `cloud_recording:read:list_user_recordings`
   - `cloud_recording:read:list_recording_files`

### Installation

```bash
git clone <repo>
cd zoom-insights
pip install -e .
```

#### For Zoom Cloud mode (optional):
```bash
cp .env.example .env
```

Edit `.env` and fill in (only if using Zoom Cloud):
```
ZOOM_ACCOUNT_ID=your_account_id
ZOOM_CLIENT_ID=your_client_id
ZOOM_CLIENT_SECRET=your_client_secret
GROQ_API_KEY=your_groq_api_key
```

#### For Local Files only:
Just set the environment variable:
```bash
export GROQ_API_KEY="your_groq_api_key"
```

No Zoom credentials needed!

## Usage

### Option 1: Process from Zoom Cloud (requires Pro+ account)

#### List recent recordings

```bash
zoom-insights list
# or just:
zoom-insights
```

Output:
```
Recent recordings:
  [0] 2024-12-15 10:00 Q4 Planning
  [1] 2024-12-14 14:30 Product Roadmap
  ...
```

#### Process a recording

By index:
```bash
zoom-insights 0
```

Or by UUID:
```bash
zoom-insights "meeting-uuid-xxx"
```

#### Use Zoom's transcript (if available)

If the meeting has cloud transcription enabled:
```bash
zoom-insights 0 --use-zoom-transcript
```

Falls back to Whisper if VTT unavailable.

### Option 2: Process Local Recordings (FREE - no Pro+ needed!)

If you have locally saved Zoom recordings (e.g., from Zoom's local recording feature), use `--local`:

```bash
# Process a local MP4/M4A file
zoom-insights /path/to/recording.mp4 --local

# With custom meeting title
zoom-insights /path/to/recording.mp4 --local --title "Q4 Planning Meeting"
```

**Why this is great:**
- No Zoom Pro+ plan required
- No Zoom Cloud API credentials needed
- Works with recordings you've already downloaded
- Same high-quality insights as cloud version
- Completely local processing (except for Groq API calls)

**Examples:**
```bash
# Home directory downloads
zoom-insights ~/Downloads/zoom_meeting.mp4 --local

# Specific folder
zoom-insights ~/Zoom_Recordings/meeting_2024_12_15.m4a --local --title "Team Standup"

# Current directory
zoom-insights ./recording.mp4 --local
```

### Enable debug logging

```bash
zoom-insights 0 --debug
# or with local files:
zoom-insights /path/to/recording.mp4 --local --debug
```

## Output

For a meeting titled "Q4 Planning", creates:

```
output/Q4_Planning/
├── report.md          # Markdown report (human-readable)
├── insights.json      # Structured JSON (machine-readable)
└── transcript.txt     # Full transcript
```

### Sample report.md

```markdown
# Q4 Planning

## Summary
Discussed Q4 strategy, budget allocation, and timeline. Approved $2M spend.

## Key Points
- Budget approved at $2M
- Timeline: Oct-Dec 2024
- Team expanded to 12 FTE

## Decisions
- Approved Q4 budget
- Postponed feature X to Q1 2025

## Action Items
- **Alice** — Finalize budget docs (due: 2024-12-20)
- **Bob** — Schedule team kickoff (due: 2024-12-10)
- **Unassigned** — Review market analysis

## Open Questions
- What about overseas hiring?
- Do we have compliance review scheduled?

## Notable Quotes
> "We need to move fast, but carefully."
> "Quality first, ship second."
```

### Sample insights.json

```json
{
  "summary": "Meeting discussed Q4 strategy and budget.",
  "key_points": ["Budget $2M", "Timeline Oct-Dec"],
  "decisions": ["Approved budget"],
  "action_items": [
    {
      "owner": "Alice",
      "task": "Finalize docs",
      "due": "2024-12-20"
    },
    {
      "owner": null,
      "task": "Review analysis",
      "due": null
    }
  ],
  "open_questions": ["Overseas hiring?"],
  "notable_quotes": ["We need to move fast."]
}
```

## Local File Processing Guide

### Supported Formats

Works with any audio/video format that ffmpeg supports:
- **Video**: MP4, MOV, MKV, AVI, WebM
- **Audio**: M4A, MP3, WAV, OGG, FLAC

### How to Export Zoom Recordings Locally

1. **During meeting (on Mac/Linux/Windows):**
   - When starting Zoom, you'll see "Record" button
   - Select "Record on this computer"
   - Zoom saves locally as MP4 or M4A

2. **From Zoom Cloud (if you have Pro+ but prefer local processing):**
   - Go to Zoom.us → Recordings
   - Find the meeting → Download

3. **From shared cloud link:**
   - Your meeting host may share a download link
   - Download the MP4/M4A file

### Complete Example

```bash
# 1. Set your Groq API key
export GROQ_API_KEY="gsk_xxxxxxxxxxxx"

# 2. Process a local recording
zoom-insights ~/Downloads/team_standup.mp4 --local --title "Dec 15 Standup"

# Output will appear in:
# output/Dec_15_Standup/
#   ├── report.md
#   ├── insights.json
#   └── transcript.txt
```

### Batch Processing Multiple Recordings

```bash
#!/bin/bash
export GROQ_API_KEY="gsk_xxxxxxxxxxxx"

for file in ~/Recordings/*.mp4; do
  echo "Processing $file..."
  zoom-insights "$file" --local
  sleep 5  # Rate limiting (optional)
done
```

Save as `process_batch.sh`, then run:
```bash
chmod +x process_batch.sh
./process_batch.sh
```

## Jira Integration

Export action items from your meeting insights directly into Jira Cloud as tickets.

### Setup

1. Get your Jira Cloud instance URL (e.g., `https://mycompany.atlassian.net`)
2. Generate an API token: Go to [account.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → Create API token
3. Get your Jira project key (e.g., `PROJ`)
4. Get your Jira email address (the one associated with your account)
5. Add to `.env`:

```
JIRA_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_api_token_here
JIRA_PROJECT_KEY=PROJ
```

### Creating Jira Tickets

After processing a meeting (which creates `output/<meeting>/insights.json`):

```bash
zoom-insights jira --insights output/<meeting>/insights.json
```

This command:
1. Reads the structured insights from the JSON file
2. Extracts all action items with owners and due dates
3. Creates one Jira ticket per action item
4. Links tickets back to the original meeting context

Output:
```
Created: PROJ-42 — https://yourcompany.atlassian.net/browse/PROJ-42
Created: PROJ-43 — https://yourcompany.atlassian.net/browse/PROJ-43
...
Created 3 ticket(s) in PROJ
```

### Ticket Details

Each created ticket includes:

- **Type**: Task
- **Title**: The action item description
- **Description**: Includes:
  - Meeting summary for context
  - Key points discussed
  - Full action item details
  - Owner name (or "Unassigned")
  - Due date (if specified in insights)
- **Project**: Your specified JIRA_PROJECT_KEY

### Best Practices

- Create tickets right after processing to capture fresh insights
- Review and update assignees in Jira if marked as "Unassigned"
- Use Jira's built-in "Fill with AI" to enrich ticket descriptions
- Customize ticket type in Jira workflow if you prefer different issue types
- Keep `.env` secrets safe (never commit to git)

## Troubleshooting

### "Forbidden 403: Access Denied"

**Cause**: Token lacks recording scope, or you're not the owner of the recording.

**Fix**:
- Verify you're the **host** of the meeting (or account owner)
- Check your OAuth app has `cloud_recording:read` scopes
- Regenerate a fresh token

### "ffmpeg not found"

**Fix**:
```bash
# macOS
brew install ffmpeg

# Linux (Ubuntu/Debian)
apt install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html
```

### "429 Too Many Requests"

**Cause**: Groq rate limit (free tier: ~6,000 tokens/min for LLM, ~2,000 requests/day for Whisper).

**Fix**:
- Wait a few minutes, then retry
- The tool retries automatically with exponential backoff
- For large meetings (>1 hour), Whisper will auto-segment

### "No recent recordings found"

**Cause**: No recordings in the last 60 days, or account not cloud-recording enabled.

**Fix**:
- Check your Zoom account plan (requires Pro+)
- Verify cloud recording is enabled for your account

### "VTT transcript not available"

**Cause**: Meeting doesn't have cloud transcription enabled.

**Fix**:
- Enable cloud transcription on your Zoom account
- The tool falls back to Whisper automatically
- This is expected behavior for `--use-zoom-transcript`

### Local File Troubleshooting

#### "File not found" with local files

**Fix**:
- Use absolute path: `zoom-insights /Users/name/Downloads/file.mp4 --local`
- Or relative from current directory: `zoom-insights ./Downloads/file.mp4 --local`
- Check file name has no spaces (or use quotes): `zoom-insights "/path/to/My Recording.mp4" --local`

#### "Unknown file type" or "Invalid audio file"

**Cause**: ffmpeg can't recognize the format.

**Fix**:
- Ensure file is a valid Zoom recording
- Try converting with ffmpeg: `ffmpeg -i input.mp4 -c:a aac output.m4a`
- Check file isn't corrupted: `ffprobe file.mp4`

#### "Already processed" but want to re-run

**Cause**: Idempotency tracking skips files already processed.

**Fix**:
```bash
# Remove from completed log
rm -f work/completed.log
# Then re-run the command
zoom-insights /path/to/file.mp4 --local
```

#### Recording takes a long time for 1+ hour meeting

**Cause**: Long audio requires chunking (segments of 15 min each), and Groq has rate limits.

**Fix**:
- This is normal; wait for completion
- Exponential backoff retry kicks in automatically
- Tips:
  - Process during off-peak hours
  - Split very long recordings manually with ffmpeg
  - Use `--debug` to see retry attempts

## Free-Tier Limits

- **Groq Whisper**: ~2,000 audio transcriptions/day, 25 MB per file
  - Mitigation: Auto-compress to 16kHz mono Opus (~90% reduction), auto-segment if >24 MB
  
- **Groq LLM**: ~6,000 tokens/minute (shared across all models)
  - Mitigation: Map-reduce chunking with backoff; never one giant prompt

- **Zoom**: Recording URLs expire in ~24 hours; re-fetch at process time

## Architecture

```
Zoom Cloud Recording API
        ↓
    download (mp4/m4a)
        ↓
    ffmpeg compress (16k mono opus)
        ↓
    segment if >24 MB
        ↓
    Groq Whisper transcribe
        ↓
    (OR) Zoom VTT download + parse
        ↓
    Groq LLM map-reduce summarize
        ↓
    write report + insights.json + transcript.txt
```

### Modules

| Module | Responsibility |
|--------|---|
| `config.py` | Environment loading + validation |
| `zoom_client.py` | OAuth, list/download recordings |
| `audio.py` | ffmpeg compression, segmentation |
| `transcribe.py` | Groq Whisper calls, VTT parsing |
| `insights.py` | Chunking, map-reduce, JSON schema validation |
| `report.py` | Write markdown + JSON + text files |
| `retry.py` | Exponential backoff for 429/timeout |
| `idempotency.py` | Track processed UUIDs |
| `cli.py` | Full orchestration + argument parsing |

## Testing

Run the full test suite (125+ tests, all mocked):

```bash
pytest -q
# or with coverage:
pytest --cov=src/zoom_insights tests/
```

Run integration test:
```bash
pytest tests/test_integration.py -v
```

## Development

### Code style

- Type hints on all public functions
- One-line docstrings
- No `print` in library code (use `logging`)
- Mocked tests only (no real API calls)

### Next steps (post-MVP)

- **FastAPI wrapper**: `POST /process {uuid}` → 202 + async job
- **Webhook automation**: Subscribe to `recording.completed`
- **Local/private mode**: `faster-whisper` + Ollama backend
- **Speaker diarization**: `pyannote` → "who said what"
- **Eval dashboard**: Cost, latency, quality metrics

## Privacy Note

**Audio leaves your machine when using Groq.** This tool:

- Downloads recordings from Zoom to your local machine
- Compresses locally (no network transmission)
- Sends compressed audio to Groq Whisper API
- Sends transcript text to Groq LLM API

Neither Zoom nor Groq stores your audio long-term (see their privacy policies).

For fully local/private processing, see the "Local/private mode" future cycle.

## License

MIT
