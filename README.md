# Zoom Insights

Extract structured insights from Zoom Cloud Recordings using free-tier APIs (Groq Whisper + Groq LLM).

## What it does

This tool automates the process of analyzing Zoom meeting recordings:

1. **Downloads** your recording from Zoom Cloud
2. **Compresses** the audio to ~5-10% of original size (16 kHz mono Opus)
3. **Transcribes** using Groq's Whisper (or uses Zoom's optional built-in transcript)
4. **Extracts** structured insights: summary, key points, decisions, action items, questions
5. **Generates** a markdown report + JSON insights file + full transcript
6. **Exports** action items directly to Jira Cloud as tickets (optional)

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

## Docker Containerization

Process recordings in an isolated, reproducible environment using Docker.

### Quick Start with Docker

#### 1. Build the Docker image

```bash
cd zoom-insights
make build
```

This creates a `zoom-insights:latest` image with all dependencies including ffmpeg.

#### 2. Process a local recording

```bash
# Copy your MP4 to the recordings folder
cp ~/Downloads/meeting.mp4 ./recordings/meeting.mp4

# Run processing with a custom title
make local TITLE="Q4 Planning Meeting"

# Output appears in ./output/Q4_Planning_Meeting/
# - report.md
# - insights.json
# - transcript.txt
```

#### 3. Process Zoom Cloud recordings

```bash
# Set up your .env (same as Installation section)
cp .env.example .env
# Edit .env with your Zoom and Groq credentials

# Interactive selection — lists recent recordings and prompts you to choose
make process

# You'll see:
#   Fetching recent recordings...
#   1. 2024-01-15 - Q4 Planning
#   2. 2024-01-14 - Team Standup
#   Select recording number (1-2): 

# Just enter the number and it processes automatically
# Output in ./output/<meeting_title>/

# Or bypass interactive mode by providing UUID directly
make process UUID=a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6
```

#### 4. View action item tracker

```bash
# See pending items across all processed meetings
make status

# Mark an item complete
make done TASK=a1b2c3d4
```

### Docker Volumes & Persistence

The Docker setup uses three volume mounts:

| Local Path | Container Path | Purpose |
|-----------|-----------------|---------|
| `./recordings/` | `/recordings` | **Input** — Copy MP4/M4A files here |
| `./output/` | `/output` | **Output** — Reports, insights, transcripts saved here |
| Named volume `data` | `/data` | **Persistence** — SQLite tracker DB, work state |

**Example workflow:**

```bash
# 1. Place your file
cp ~/Downloads/my_recording.mp4 ./recordings/meeting.mp4

# 2. Process (Docker mounts volumes automatically)
make local TITLE="My Meeting"

# 3. Check output on your machine
cat ./output/My_Meeting/report.md
ls -la ./output/My_Meeting/
```

The `data` volume persists across container runs, so your action item tracker state is maintained.

### All Make Targets

```bash
make build                              # Build Docker image
make local TITLE="Meeting Title"        # Process local MP4: ./recordings/meeting.mp4 → ./output/
make process                            # Interactive: list recent recordings, select one to process
make process UUID=<uuid>                # Process Zoom Cloud recording by UUID (bypass interactive)
make status                             # View pending action items (tracker)
make done TASK=<task-id>                # Mark action item complete
make process-jira                       # Interactive: select recording + export to Jira
make process-jira UUID=<uuid>           # Process + export to Jira (bypass interactive)
make process-notify WEBHOOK=<url>       # Interactive: select recording + Slack/Teams notification
make process-notify UUID=<uuid> WEBHOOK=<url>  # Process + notify (bypass interactive)
```

### Environment File (docker-compose auto-loads)

When running with `make`, `docker-compose` automatically reads your `.env` file. You don't need to pass `--env-file` manually.

**Example .env:**
```bash
ZOOM_ACCOUNT_ID=your_id
ZOOM_CLIENT_ID=your_client_id
ZOOM_CLIENT_SECRET=your_secret
GROQ_API_KEY=gsk_your_key_here
TRACKER_DB=/data/zoom-insights.db
```

### Supported Input Formats

Works with any ffmpeg-compatible format:
- **Video**: MP4, MOV, MKV, AVI, WebM
- **Audio**: M4A, MP3, WAV, OGG, FLAC

### Example Output Structure

After processing a meeting titled "Q4 Planning", your local `./output/` contains:

```
output/Q4_Planning/
├── report.md              # Markdown (human-readable)
├── insights.json          # JSON (machine-readable)
├── transcript.txt         # Full transcript
└── metrics.txt            # Token usage & cost estimates (if --debug)
```

**Sample report.md:**
```markdown
# Q4 Planning

## Summary
Discussed Q4 strategy, budget allocation, timeline. Approved $2M spend.

## Key Points
- Budget approved at $2M
- Timeline: Oct-Dec 2024
- Team expanded to 12 FTE

## Decisions
- Approved Q4 budget
- Postponed feature X to Q1 2025

## Action Items
- **Alice** — Finalize budget docs (due: 2024-12-20)
- **Bob** — Schedule kickoff (due: 2024-12-10)
```

### Combining Docker with Other Features

```bash
# Fully private: local backend + no external APIs
make local TITLE="Private Meeting"     # Uses faster-whisper + Ollama locally

# With speaker diarization (requires HUGGINGFACE_TOKEN in .env)
docker compose run --rm zoom-insights /recordings/meeting.mp4 --local --diarize

# Process + auto-enrich QA recommendations (requires CLAUDE_API_KEY)
docker compose run --rm zoom-insights /recordings/meeting.mp4 --local

# Process + export to Jira
make process-jira UUID=meeting-uuid
```

All features (diarization, local backend, Jira export, Slack/Teams notifications) work identically inside Docker as they do locally.

### Troubleshooting Docker

**"docker: command not found"**
- Install Docker Desktop: https://www.docker.com/products/docker-desktop
- Then: `docker --version` to verify

**"make: command not found"**
- macOS: `brew install make`
- Linux: `apt install make`
- Or use `docker compose` commands directly (see Makefile for commands)

**Build fails: "ffmpeg not found"**
- This should not happen; Dockerfile installs ffmpeg via apt
- Try: `docker compose build --no-cache`

**Container exits immediately**
- Check your recording file path: `ls -la ./recordings/`
- Verify .env is readable: `cat .env`
- Add `--debug` flag: `docker compose run --rm zoom-insights /recordings/meeting.mp4 --local --debug`

#### Optional Features

**Local Backend (fully private, no API calls):**
```bash
# Install Ollama from https://ollama.ai
ollama pull mistral

# In .env:
OLLAMA_URL=http://localhost:11434
```

**Speaker Diarization (identify speakers):**
```bash
# Get HuggingFace token from https://huggingface.co/settings/tokens
# In .env:
HUGGINGFACE_TOKEN=hf_xxxxx
```

**Slack/Teams Notifications:**
```bash
# In .env (optional):
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
TEAMS_WEBHOOK_URL=https://outlook.webhook.office.com/webhookb2/YOUR/URL
```

**Action Item Tracker (SQLite):**
```bash
# In .env (optional):
TRACKER_DB=~/.zoom-insights.db
```

**Zoom Webhook Automation:**
```bash
# In .env (if using webhook):
ZOOM_WEBHOOK_SECRET_TOKEN=your_zoom_webhook_secret
```

**Claude API (for QA enrichment):**
```bash
# In .env (if auto-enriching insights):
CLAUDE_API_KEY=sk-xxxxx
```

## Usage

### API Server Mode (FastAPI)

Run as a REST API server for async processing and webhook automation:

```bash
zoom-insights serve --port 8000
```

This starts a FastAPI server with:
- `POST /process` — Submit a meeting UUID or local file path for async processing
- `GET /jobs/{job_id}` — Check job status and retrieve results
- `GET /health` — Health check endpoint
- `POST /webhook` — Zoom webhook receiver (HMAC-SHA256 signature verification)

**Example: Submit a job**
```bash
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{"action": "0", "local": false}'
```

**Example: Check job status**
```bash
curl http://localhost:8000/jobs/job-uuid-here
```

The API automatically processes recordings in the background and stores results in `output/`.

### Webhook Automation (Zoom Integration)

Configure Zoom to notify your server when recordings complete:

1. Set up your FastAPI server (see API Server Mode above)
2. Go to Zoom Marketplace → Your Apps → Event Subscriptions
3. Add webhook endpoint: `https://your-server.com/webhook`
4. Subscribe to `recording.completed` event
5. Add your `ZOOM_WEBHOOK_SECRET_TOKEN` to `.env`

The server automatically downloads and processes recordings as soon as they're available.

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

### Option 2b: Local Backend Mode (Fully Private - No API Calls)

Process recordings entirely on your machine without sending audio to Groq:

```bash
# Requires: faster-whisper (transcription) + Ollama (LLM)
zoom-insights /path/to/recording.mp4 --local --local-backend

# Or with Zoom Cloud recordings
zoom-insights 0 --local-backend
```

This uses:
- **faster-whisper** — Local speech-to-text (CPU or GPU)
- **Ollama** — Local LLM inference

**Setup:**
```bash
# Install Ollama from https://ollama.ai
ollama pull mistral  # or your preferred model

# Set Ollama URL in .env
OLLAMA_URL=http://localhost:11434
```

No API keys needed; complete privacy.

### Option 2c: Speaker Diarization (Who Said What)

Add speaker identification to action items and transcript:

```bash
zoom-insights /path/to/recording.mp4 --local --diarize
```

Or with Zoom Cloud:
```bash
zoom-insights 0 --diarize
```

**Requirements:**
- HuggingFace account (free tier works)
- HuggingFace token (get from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens))
- Add to `.env`: `HUGGINGFACE_TOKEN=hf_xxxxx`

**Features:**
- Identifies speakers in the recording
- Labels action items with speaker names (e.g., "Alice — Finalize budget docs")
- Includes speaker labels in transcript

### Option 2d: Post Notifications to Slack/Teams

Automatically send a summary card to Slack or Teams after processing:

```bash
# Slack webhook
zoom-insights /path/to/recording.mp4 --local \
  --notify "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Teams webhook
zoom-insights 0 \
  --notify "https://outlook.webhook.office.com/webhookb2/YOUR/URL"
```

The tool auto-detects the platform (Slack vs Teams) and sends:
- Meeting summary
- Top 3 action items
- Link to full report

**Setup Slack webhook:**
1. Go to your Slack workspace → Settings → Apps
2. Search for "Incoming Webhooks"
3. Create new webhook for your channel
4. Copy the webhook URL

**Setup Teams webhook:**
1. In Microsoft Teams, go to your channel
2. Click ⋯ (More options) → Connectors
3. Search "Incoming Webhook"
4. Create new webhook
5. Copy the webhook URL

### Option 3: Action Item Tracker (SQLite)

Track action items across multiple meetings with completion status:

```bash
# View all pending action items
zoom-insights status

# Mark an item complete
zoom-insights done <task-id>
```

**Features:**
- Auto-saves action items after each processing
- Groups by: overdue, upcoming, no due date
- Tracks creation date and completion date
- Configurable database location (default: `~/.zoom-insights.db`)

**Configuration:**
```bash
# In .env (optional)
TRACKER_DB=~/.zoom-insights.db
```

**Output example:**
```
Pending Action Items (5 total)
================================

OVERDUE (1 items):
- [a1b2c3d4] (Alice) Finalize budget docs (due: 2026-07-01)

UPCOMING (3 items):
- [e5f6g7h8] (Bob) Schedule kickoff (due: 2026-07-10)
- [i9j0k1l2] (Carol) Review market analysis (due: 2026-07-15)
- [m3n4o5p6] (Unassigned) Update wiki (due: 2026-07-20)

NO DUE DATE (1 items):
- [q7r8s9t0] (Alice) Follow up on Q4 metrics
```

### Option 4: Processing Metrics and Cost Tracking

View cost estimates and performance metrics for your processing:

```bash
zoom-insights /path/to/recording.mp4 --local --debug
```

The output now includes:
- **Tokens used**: Input and output tokens for transcription and LLM
- **Latency**: Time spent at each stage
- **Estimated cost**: Cost breakdown by API call (Groq pricing)

**Sample metrics output:**
```
Processing Metrics
==================
Stage: Transcription
  Tokens (input): 45,320
  Latency: 42.3 seconds
  Cost: $0.08

Stage: Summarization
  Tokens (input): 8,450 | (output): 1,200
  Latency: 5.2 seconds
  Cost: $0.00

Total estimated cost: $0.08
```

Metrics are also saved to `insights.json` for tracking.

### Option 5: Automatic Enrichment with QA Recommendations (optional)

**Enrichment is automatic!** When you pass an `insights.json` file to the CLI, it automatically enriches it with repository-aware QA recommendations if `CLAUDE_API_KEY` is set:

```bash
# Automatic enrichment: pass insights.json and it gets enhanced
zoom-insights output/<meeting>/insights.json

# Optionally save enriched version to a different file instead of overwriting
zoom-insights output/<meeting>/insights.json --output-file output/<meeting>/insights_enriched.json

# Specify a different repository path (defaults to current directory)
zoom-insights output/<meeting>/insights.json --repo-path /path/to/repo
```

**Per-Action-Item Enrichment:**

Enrichment generates **distinct QA recommendations for each action item** in the meeting. Each action item receives its own:
- **Test scenarios** — specific test cases tailored to that action item
- **Features to add** — code improvements or enhancements relevant to that item
- **Edge cases to cover** — failure modes and boundary conditions specific to that action
- **Technologies** — languages, frameworks, and libraries involved
- **Implementation steps** — concrete, actionable steps to implement or test that action

This means when you export multiple action items to Jira, each ticket gets its own unique QA recommendations and subtasks—not generic, shared recommendations.

**Note:** Enrichment is optional. If `CLAUDE_API_KEY` is not set, the insights file is left as-is. Just use `zoom-insights output/<meeting>/insights.json` and the system will enrich it automatically if possible.

### Option 6: Export to Jira (optional)

After processing a meeting (and optionally enriching it), export action items as Jira tickets:

```bash
# Export insights to Jira Cloud
zoom-insights jira --insights output/<meeting>/insights.json
```

This creates one Task ticket per action item with:
- Action item description as title
- Meeting summary and key points in description
- Owner and due date (if available)
- QA recommendations (if insights have been enriched)

Requires Jira Cloud credentials in `.env` (see [Jira Integration](#jira-integration) section).

### Combining Features

Here are some powerful combinations:

```bash
# Local file + diarization + speaker-attributed action items
zoom-insights ~/Downloads/meeting.mp4 --local --diarize

# Process + auto-enrich + export to Jira + notify Slack
zoom-insights 0 --jira \
  --notify "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Fully private: local backend + no external APIs
zoom-insights ~/recording.mp4 --local --local-backend --notify "YOUR_SLACK_WEBHOOK"

# Track action items + view status later
zoom-insights 0 --local
# ... later ...
zoom-insights status
zoom-insights done <task-id>

# View processing metrics and costs
zoom-insights /path/to/recording.mp4 --local --debug
```

### Enable debug logging

```bash
zoom-insights 0 --debug
# Shows: retry attempts, token usage, latency, estimated costs

# or with local files:
zoom-insights /path/to/recording.mp4 --local --debug

# or with Jira export:
zoom-insights jira --insights output/<meeting>/insights.json --debug

# or with tracker:
zoom-insights status --debug
```

### Performance Tuning (Optional)

Optimize throughput and resource usage with environment variables in `.env`:

```bash
# Parallel segment transcription (default: 4 workers)
# Speeds up large recordings by transcribing segments concurrently
MAX_TRANSCRIPTION_WORKERS=4

# Concurrent batch digest processing (default: 3 workers)
# When processing multiple meetings, limits parallelism to avoid rate limits
MAX_BATCH_WORKERS=3

# Bounded API server concurrency (default: 4 jobs)
# When using webhook/API mode, limits concurrent pipeline executions
MAX_CONCURRENT_JOBS=4
```

**Impact:**
- Increasing `MAX_TRANSCRIPTION_WORKERS` speeds up large recordings (>25MB) at the cost of higher Groq API rate usage
- Increasing `MAX_BATCH_WORKERS` processes multiple meetings faster when running digest
- Increasing `MAX_CONCURRENT_JOBS` allows more parallel webhook jobs but may exceed Groq rate limits

**Recommendation:** Keep defaults (4, 3, 4) unless you:
- Have many large recordings → increase `MAX_TRANSCRIPTION_WORKERS` to 6-8
- Process many meetings in batch → increase `MAX_BATCH_WORKERS` to 5-10
- Run high-traffic webhook server → monitor Groq rate limits before increasing `MAX_CONCURRENT_JOBS`

## Processing Modes

| Mode | Input | Privacy | Speed | Cost |
|------|-------|---------|-------|------|
| **Zoom Cloud** | Zoom Recording URL | Medium (audio → Groq) | Fast | Low (~$0.01-0.05) |
| **Local File** | MP4/M4A on disk | Medium (audio → Groq) | Fast | Low (~$0.01-0.05) |
| **Local Backend** | MP4/M4A on disk | High (fully local) | Slow (CPU) | Free |
| **API Server** | Remote HTTP | Depends on config | Async | Depends on config |

## Output

For a meeting titled "Q4 Planning", creates:

```
output/Q4_Planning/
├── report.md          # Markdown report (human-readable)
├── insights.json      # Structured JSON (machine-readable)
├── transcript.txt     # Full transcript
└── # Enhanced outputs (optional):
    ├── speaker_labels # (if --diarize: speaker names + timestamps)
    └── metrics        # (in insights.json: tokens, latency, cost)
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
      "owner": "Bob",
      "task": "Review analysis",
      "due": null
    }
  ],
  "open_questions": ["Overseas hiring?"],
  "notable_quotes": ["We need to move fast."],
  
  "metrics": {
    "transcription": {
      "tokens_in": 45320,
      "latency_seconds": 42.3,
      "estimated_cost_usd": 0.08
    },
    "summarization": {
      "tokens_in": 8450,
      "tokens_out": 1200,
      "latency_seconds": 5.2,
      "estimated_cost_usd": 0.00
    },
    "total_estimated_cost_usd": 0.08
  },

  "action_item_qa": [
    {
      "test_scenarios": [
        "Verify budget allocation across departments"
      ],
      "features_to_add": [
        "Budget dashboard for real-time spending"
      ],
      "edge_cases_to_cover": [
        "Emergency spending requests over limit"
      ],
      "technologies": [
        "Python, PostgreSQL, React"
      ],
      "implementation_steps": [
        "Create budget allocation model",
        "Implement department-level approval logic",
        "Add audit trail for compliance"
      ]
    },
    {
      "test_scenarios": [
        "Test approval workflow for Q4 spending"
      ],
      "features_to_add": [
        "Automated approval escalation"
      ],
      "edge_cases_to_cover": [
        "Multi-currency budget handling"
      ],
      "technologies": [
        "Node.js, MongoDB, Vue.js"
      ],
      "implementation_steps": [
        "Design approval state machine",
        "Implement escalation notifications",
        "Add currency conversion logic"
      ]
    }
  ]
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
# Auto-enrich with QA recommendations, then export to Jira
zoom-insights output/<meeting>/insights.json
zoom-insights jira --insights output/<meeting>/insights.json
```

Or combine both in one command with `--jira` flag:
```bash
zoom-insights /path/to/recording.mp4 --local --jira
```

This command:
1. Reads the structured insights from the JSON file
2. Auto-enriches with repository-aware QA recommendations (if `CLAUDE_API_KEY` set)
3. Extracts all action items with owners and due dates
4. Creates one Jira ticket per action item with:
   - **Unique subtasks for each test scenario** — Each action item gets its own set of test scenarios based on its specific context
   - **Per-item QA recommendations** — Technologies, implementation steps, edge cases, and features specific to that action item (not generic)
   - **Meeting context and key points** — Summary and discussion context
   - **Speaker attribution** (if diarization enabled)
5. Links tickets back to the original meeting context

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
| **Core Pipeline** | |
| `config.py` | Environment loading + validation |
| `zoom_client.py` | OAuth, list/download recordings |
| `audio.py` | ffmpeg compression, segmentation |
| `transcribe.py` | Groq Whisper calls, VTT parsing |
| `insights.py` | Chunking, map-reduce, JSON schema validation |
| `report.py` | Write markdown + JSON + text files |
| `retry.py` | Exponential backoff for 429/timeout |
| `idempotency.py` | Track processed UUIDs |
| **Backend Abstraction** | |
| `backends.py` | Abstract backend interfaces + implementations (Groq, faster-whisper, Ollama) |
| `diarization.py` | Speaker identification (PyannoteBackend, LocalDiarizationBackend) |
| `transcript_merge.py` | Merge diarization segments with transcript |
| **Enhancement & Export** | |
| `enrich_insights.py` | Auto-enrich with repo-aware QA recommendations |
| `jira_export.py` | Create Jira tickets from action items |
| `notify.py` | Post to Slack/Teams webhooks |
| `sanitize.py` | Remove injection patterns, sanitize input |
| `metrics.py` | Token/latency/cost tracking |
| **Tracking & APIs** | |
| `tracker.py` | SQLite action item persistence (CRUD, filtering, sorting) |
| `api.py` | FastAPI REST endpoints (POST /process, GET /jobs/{id}, POST /webhook) |
| **CLI & Entry** | |
| `cli.py` | Full orchestration + argument parsing + subcommands |

## Testing

Run the full test suite (240+ tests, all mocked, no external API calls):

```bash
pytest -q
# or with coverage:
pytest --cov=src/zoom_insights tests/
# Expected: 240+ passed
```

Run specific test modules:
```bash
# Core pipeline tests
pytest tests/test_transcribe.py tests/test_insights.py tests/test_report.py -v

# Backend tests
pytest tests/test_backends.py tests/test_diarization.py -v

# API and integration tests
pytest tests/test_api.py tests/test_integration.py -v

# Action item tracker tests
pytest tests/test_tracker.py tests/test_cli.py -v

# Integration tests (end-to-end)
pytest tests/test_integration.py -v
```

Test markers:
```bash
# Run only unit tests (fast)
pytest -m unit -q

# Run slow tests (e2e, integration)
pytest -m integration -v
```

## Development

### Code style

- Type hints on all public functions
- One-line docstrings
- No `print` in library code (use `logging`)
- Mocked tests only (no real API calls)

### Completed Features (Cycles 19-25)

✅ **Cycle 19: FastAPI wrapper** — `POST /process`, `GET /jobs/{id}`, `zoom-insights serve`
✅ **Cycle 20: Webhook automation** — `POST /webhook` with HMAC verification, auto-process on `recording.completed`
✅ **Cycle 21: Local/private mode** — `--local-backend` flag (faster-whisper + Ollama, no API calls)
✅ **Cycle 22: Speaker diarization** — `--diarize` flag (pyannote.audio, speaker attribution to action items)
✅ **Cycle 23: Quality pass** — Metrics tracking (tokens, latency, cost), sanitization, backend abstraction
✅ **Cycle 24: Slack/Teams integration** — `--notify` flag, auto-detects platform, posts summary cards
✅ **Cycle 25: Action item tracker** — SQLite DB, `zoom-insights status` / `done`, auto-save on process

### Next steps (post-Cycle 25)

- **Cycle 26: Recurring meeting digest** — Batch process N days, rollup report across meetings
- **Cycle 27: Interactive meeting Q&A (RAG)** — Embed transcripts, semantic search with LLM

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
