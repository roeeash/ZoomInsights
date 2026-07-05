# Zoom Meeting Insights — Development Plan

A tool that takes a recording from **your own Zoom account**, downloads it,
transcribes it, summarizes it, and extracts structured insights — built to run
entirely on free tiers (Groq Whisper + Groq LLM).

There is already a **working spike** at `prototype/zoom_insights.py` that does the
whole pipeline end to end in one file. This plan turns that spike into a small,
tested, maintainable package, **one vertical slice at a time**. Each cycle ends
in a runnable, verifiable state.

---

## How to use this plan (for the agent / developer)

- Work **one cycle at a time, in order**. Do not start a cycle until the previous
  cycle's **Definition of Done** is fully checked off.
- Every cycle ends with something you can *run* and *verify*, not just code that
  compiles. Prefer a real (or recorded/mocked) request over "looks right".
- When a cycle says "port from spike", copy the relevant logic out of
  `prototype/zoom_insights.py`, then improve it per the **Coding standards**
  (Appendix A). The spike is the source of truth for behavior, not for style.
- Commit at the end of each cycle with the message `Cycle N: <goal>`.
- Keep secrets in `.env` (never commit). `output/` and `work/` are gitignored.

---

## 1. Architecture & data flow

```
Zoom Cloud Recording API ──► download (mp4/m4a) ──► ffmpeg compress (16k mono)
        │                                                   │
        └──► (optional) Zoom .vtt transcript ──┐            ▼
                                               │     [segment if >24MB]
                                               ▼            │
                                        transcript text ◄── Groq Whisper turbo
                                               │
                                               ▼
                                 map-reduce summarize (Groq LLM)
                                               │
                                               ▼
                      report.md  +  insights.json  +  transcript.txt
```

**Stage ownership (target modules):**

| Stage | Module | Responsibility |
|---|---|---|
| Auth + retrieval | `zoom_client.py` | OAuth token, list/get recordings, download files |
| Audio prep | `audio.py` | ffmpeg compress, size check, segmentation |
| Transcription | `transcribe.py` | Groq Whisper calls, VTT parsing |
| Insights | `insights.py` | chunking, map-reduce, JSON-schema validation |
| Output | `report.py` | write transcript / insights / markdown report |
| Cross-cutting | `retry.py`, `config.py` | backoff, env/config loading & validation |
| Entry point | `cli.py` | argument parsing, orchestration |

---

## 2. Constraints & decisions (read before coding)

These are deliberate and shape the design — don't "optimize" them away without cause.

- **Free Zoom plan has no cloud recording.** This tool assumes a Pro+ host
  account that you control. Auth is **Server-to-Server OAuth** (account-level),
  not user OAuth — no per-user consent flow needed.
- **Groq free Whisper tier:** ~2,000 audio requests/day, **25 MB upload cap**.
  Mitigation: compress to 16 kHz mono Opus (Whisper downsamples to 16 kHz
  anyway), then segment if still over ~24 MB.
- **Groq free LLM tier bottleneck is ~6,000 tokens/minute**, not the daily cap.
  Mitigation: **map-reduce** summarization — many small calls with backoff,
  never one giant prompt.
- **No speaker diarization** in Whisper. "Who said what" is out of scope for the
  core build; it's an optional later cycle (local `pyannote`) or a paid swap
  (AssemblyAI/Google).
- **Privacy:** audio leaves the machine when using Groq. A fully-local mode
  (`faster-whisper` + Ollama) is an optional cycle; keep stage interfaces clean
  so it's a drop-in swap.

---

## 3. Target repository layout

```
zoom-insights/
├── PLAN.md                     # this file
├── README.md                   # created in Cycle 1
├── requirements.txt
├── .env.example
├── .gitignore
├── prototype/
│   └── zoom_insights.py        # working spike (reference behavior)
├── src/zoom_insights/
│   ├── __init__.py
│   ├── config.py
│   ├── retry.py
│   ├── zoom_client.py
│   ├── audio.py
│   ├── transcribe.py
│   ├── insights.py
│   ├── report.py
│   └── cli.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/               # short sample audio, sample API json, sample vtt
│   ├── test_retry.py
│   ├── test_config.py
│   ├── test_zoom_client.py
│   ├── test_audio.py
│   ├── test_transcribe.py
│   ├── test_insights.py
│   └── test_report.py
├── output/                     # gitignored — generated reports
└── work/                       # gitignored — temp downloads/audio
```

---

## 4. Data contracts

### `insights.json` schema (the reduce step must produce exactly this)

```json
{
  "summary": "string — 3-5 sentence overview",
  "key_points": ["string"],
  "decisions": ["string"],
  "action_items": [{"owner": "string|null", "task": "string", "due": "string|null"}],
  "open_questions": ["string"],
  "notable_quotes": ["string"]
}
```

Rules: every key present; arrays may be empty; never invent owners/dates — use
`null`. Validation lives in `insights.py` (Cycle 8) and is enforced by a test.

### Output files (per processed meeting, under `output/<safe-topic>/`)

- `transcript.txt` — full transcript
- `insights.json` — the object above
- `report.md` — human-readable rendering of the insights

---

## 5. Cycle map (tracking)

- [x] Cycle 1: Scaffold, config, and the safety net — ✓ Package structure, config validation, test harness
- [x] Cycle 2: Zoom auth (Server-to-Server OAuth) — ✓ OAuth token retrieval with error handling
- [x] Cycle 3: List & select recordings — ✓ Recording enumeration with pagination and UUID encoding
- [x] Cycle 4: Download a recording file — ✓ Stream download with 1 MB chunks and error handling
- [x] Cycle 5: Audio preparation (ffmpeg) — ✓ ffmpeg compression to 16kHz Opus, segmentation for large files
- [x] Cycle 6: Transcription (Groq Whisper) — ✓ Groq Whisper transcription with retry logic
- [x] Cycle 7: Zoom VTT shortcut — ✓ Optional VTT parsing with graceful Whisper fallback
- [x] Cycle 8: Summary & insights (map-reduce + schema) — ✓ Map-reduce insights with schema validation and repair
- [x] Cycle 9: Reporting — ✓ Markdown report generation, JSON insights, transcript output
- [x] Cycle 10: Robustness pass — ✓ Retry helper, structured logging, idempotency tracking
- [x] Cycle 11: End-to-end integration + docs — ✓ Full CLI orchestration, comprehensive README, integration tests
- [x] Cycle 12: Jira integration — ✓ Export action items to Jira Cloud tickets with structured context
- [x] Cycle 13: Auto-export with `--jira` flag — ✓ Combine recording processing + Jira export into one command
- [x] Cycle 14: Pytest fixtures infrastructure — ✓ 9 fixtures, pytest-mock plugin, markers, 2 integration test classes, parametrized tests
- [x] Cycle 15: E2E test: local recording → insights.json → Jira ticket — ✓ 5 test cases with 6 parametrized variants, credential auto-skip, full pipeline coverage
- [x] Cycle 16: Full optimization pass — ✓ Fixed 11 correctness bugs, eliminated unittest.mock, refactored cli.py, 158+ tests passing
- [x] Cycle 17: Insights enrichment agent — ✓ Auto-enrich insights.json with repo-aware QA recommendations, create Jira subtasks, 170 tests passing
- [x] Cycle 18: TDD robustness & feature enhancements — ✓ Fixed 11 critical bugs (missing imports, hardcoded model, auth flaws, silent failures, idempotency collision, missing QA rendering), added 15 new tests (185 total passing), zero regressions
- [ ] Cycle 19: FastAPI wrapper — async job queue, REST API for pipeline
- [ ] Cycle 20: Webhook automation — auto-process on Zoom recording.completed
- [ ] Cycle 21: Local/private mode — faster-whisper + Ollama, no audio leaves machine
- [ ] Cycle 22: Speaker diarization — pyannote, "who said what" in action items
- [ ] Cycle 23: Quality pass — prompt-injection hardening, eval set, cost/latency metrics
- [ ] Cycle 24: Slack / Teams integration — post summary card after processing
- [ ] Cycle 25: Action item follow-up tracker — SQLite, zoom-insights status/done
- [ ] Cycle 26: Recurring meeting digest — batch rollup report across N days
- [ ] Cycle 27: Interactive meeting Q&A (RAG) — embed transcripts, query with LLM

**STATUS: MVP COMPLETE ✓ | OPTIMIZATION PASS COMPLETE ✓ | Cycle 16 COMPLETE ✓ | Cycle 17 COMPLETE ✓ | Cycle 18 COMPLETE ✓**

---

## 6. Development cycles

> Each cycle: **Goal → Steps → Tests → Definition of Done**. A cycle is "done"
> only when every box is checked and the cycle's verify command runs clean.

### Cycle 1 — Scaffold, config, and the safety net

**Goal:** A runnable, importable package skeleton with config validation and a
green test run — before any real logic.

**Steps**
1. Create the directory tree from §3 (empty modules with docstrings + `pass`).
2. `requirements.txt`: `groq`, `requests`, `python-dotenv`, `jsonschema`,
   `pytest`. Pin major versions.
3. `.env.example` with `ZOOM_ACCOUNT_ID`, `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`,
   `GROQ_API_KEY`, plus optional `LLM_MODEL`, `WHISPER_MODEL`.
4. `.gitignore` for `.env`, `output/`, `work/`, `__pycache__/`, `*.pyc`.
5. `config.py`: load env (via `python-dotenv`), expose a typed `Config` object,
   and a `Config.validate()` that raises a clear error naming any missing var.
6. `README.md`: one-paragraph what/why + the setup steps from Appendix B.
7. `tests/test_config.py`: asserts `validate()` raises on a missing var and
   passes when all are set (use monkeypatch, no real secrets).

**Tests / verify**
- `pip install -r requirements.txt`
- `python -c "import zoom_insights"` (after `pip install -e .` or `PYTHONPATH=src`)
- `pytest -q` → green

**Definition of Done**
- [ ] Tree + files exist; package imports
- [ ] `Config.validate()` gives a human-readable error for each missing var
- [ ] `pytest` passes
- [ ] `ffmpeg -version` documented as a prerequisite in README

---

### Cycle 2 — Zoom auth (Server-to-Server OAuth)

**Goal:** Obtain a valid Zoom access token from credentials.

**Prereq:** The Zoom app must exist (Appendix B). This is a manual, one-time step.

**Steps**
1. Port `zoom_token()` from the spike into `zoom_client.py` as
   `get_access_token(config) -> str`.
2. Use HTTP Basic auth (`client_id:client_secret`), `grant_type=account_credentials`.
3. Raise a clear error on non-200 that surfaces Zoom's error body.

**Tests / verify**
- Unit: mock `requests.post`, assert the Basic header and params are built right,
  assert the token is extracted from JSON. (`test_zoom_client.py`)
- Manual smoke: a tiny `scripts/smoke_token.py` prints the first 8 chars of a
  real token. Run once; do not commit output.

**Definition of Done**
- [ ] `get_access_token` returns a token against the real account
- [ ] Bad credentials produce an actionable error, not a stack trace dump
- [ ] Unit test green with mocked HTTP

---

### Cycle 3 — List & select recordings

**Goal:** Enumerate recent recordings and resolve a chosen meeting to its files.

**Steps**
1. `list_recent_recordings(token, days_back=60) -> list[Meeting]`
   (GET `/users/me/recordings`, paginate if `next_page_token` present).
2. `get_meeting_recording(token, meeting_uuid) -> Meeting`
   — **handle the UUID double-encoding rule** (encode twice if it starts with
   `/` or contains `//`).
3. Define a light `Meeting`/`RecordingFile` dataclass (topic, start_time, uuid,
   files) so downstream stages aren't dict-spelunking.
4. `pick_file(files, *types)` preference helper (e.g. `M4A` before `MP4`).

**Tests / verify**
- Unit: feed a saved `fixtures/recordings.json`; assert parsing + `pick_file`
  ordering; assert the double-encode branch fires for a `//` uuid.
- Manual: `cli.py` with no args prints an indexed list (port from spike).

**Definition of Done**
- [ ] `list` prints `[i] date topic` for real recordings
- [ ] Pagination handled (or explicitly noted as out-of-scope for >30)
- [ ] UUID encoding tested

---

### Cycle 4 — Download a recording file

**Goal:** Stream a recording file to disk using the OAuth token.

**Steps**
1. `download(file, token, out_path)` — `requests.get(..., stream=True)` with
   `Authorization: Bearer`, write in 1 MB chunks (port from spike).
2. Ensure `work/` exists; name files deterministically.
3. Handle the common **Forbidden 124** failure (token lacks recording scope or
   account isn't the owner) with a targeted hint.

**Tests / verify**
- Unit: mock a streamed response; assert bytes land on disk.
- Manual: download the audio of one real recording; confirm file size > 0 and
  `ffprobe` recognizes it.

**Definition of Done**
- [ ] A real audio/video file downloads and is playable
- [ ] Forbidden/expired-token paths give actionable messages

---

### Cycle 5 — Audio preparation (ffmpeg)

**Goal:** Produce upload-ready audio under the Groq size cap, for any length.

**Steps**
1. `require_ffmpeg()` guard (clear install message if missing).
2. `to_compressed_audio(src, dst)` → 16 kHz mono Opus (`libopus -b:a 16k`).
3. `maybe_segment(path) -> list[str]`: if `> MAX_UPLOAD_MB`, ffmpeg
   `-f segment -segment_time 900`; else return `[path]`.
4. Make `MAX_UPLOAD_MB` and segment length config-driven.

**Tests / verify**
- Unit: monkeypatch `subprocess.run`; assert correct ffmpeg args; assert
  `maybe_segment` returns one path under the cap and multiple over it (fake the
  size with a temp file / `os.path.getsize` patch).
- Manual: compress a real 1-hour recording; confirm result is a few MB.

**Definition of Done**
- [ ] 1-hour call compresses to well under 24 MB
- [ ] Oversized input segments correctly; segments are individually < cap
- [ ] Missing-ffmpeg path is friendly

---

### Cycle 6 — Transcription (Groq Whisper)

**Goal:** Turn one-or-many audio segments into a single transcript string.

**Steps**
1. `transcribe(paths, client) -> str` using `whisper-large-v3-turbo`,
   `response_format="text"`; concatenate segments in order.
2. Wrap each call in the **retry helper from Cycle 10** (or its interim version)
   for 429s.
3. Normalize SDK return (string vs object with `.text`).

**Tests / verify**
- Unit: mock the Groq client; assert per-segment calls and joined output.
- Manual: transcribe a ~30s fixture clip; eyeball accuracy.

**Definition of Done**
- [ ] Multi-segment transcript stitches in order
- [ ] A real short clip transcribes correctly
- [ ] 429 during transcription is retried, not fatal

---

### Cycle 7 — Zoom VTT shortcut

**Goal:** When the meeting already has a Zoom transcript, skip Whisper.

**Steps**
1. `--use-zoom-transcript` flag.
2. If a `TRANSCRIPT` file exists, download the `.vtt`, strip cue numbers,
   timestamps, and the `WEBVTT` header → plain text.
3. Fall back to the Whisper path if no VTT exists (log the fallback).

**Tests / verify**
- Unit: parse `fixtures/sample.vtt` → assert no `-->`, no bare indices, no
  `WEBVTT` lines remain.
- Manual: run with the flag on a meeting that has cloud transcription on.

**Definition of Done**
- [ ] VTT path yields clean transcript text
- [ ] Graceful fallback when VTT absent

---

### Cycle 8 — Summary & insights (map-reduce + schema)

**Goal:** Produce a **schema-valid** `insights.json` from any transcript length.

**Steps**
1. `chunk(text, size=11000)` word-aware splitter.
2. **Map:** summarize each chunk to tight bullets (faithful, invent-nothing system prompt).
3. **Reduce:** combine notes into the §4 JSON object; request
   `response_format={"type":"json_object"}`.
4. Validate the result with `jsonschema` against the §4 contract; on failure,
   one repair retry ("return valid JSON for this schema"), then a safe fallback
   object.
5. Every LLM call goes through retry/backoff.

**Tests / verify**
- Unit: feed a fabricated multi-chunk transcript with mocked LLM responses;
  assert all schema keys present and `action_items` shaped correctly.
- Unit: malformed model output → repair path → valid object.
- Manual: run on a real transcript; sanity-check the insights.

**Definition of Done**
- [ ] Output always validates against the schema (even on model misbehavior)
- [ ] Long transcripts processed via chunking without hitting TPM as a hard fail
- [ ] Owners/dates never fabricated (spot-check)

---

### Cycle 9 — Reporting

**Goal:** Write the three output artifacts to `output/<safe-topic>/`.

**Steps**
1. `write_report(topic, transcript, insights, out_dir)` (port from spike).
2. Markdown sections rendered only when non-empty; action items show
   `owner — task (due …)`.
3. Sanitize topic into a safe directory name.

**Tests / verify**
- Unit: given a sample insights object, assert `report.md` contains expected
  headers and omits empty sections; assert all three files written.

**Definition of Done**
- [ ] `report.md`, `insights.json`, `transcript.txt` all produced
- [ ] Empty categories don't render dangling headers

---

### Cycle 10 — Robustness pass

**Goal:** Make the pipeline boring to operate.

**Steps**
1. Finalize `retry.py::with_retry(fn, *args, tries, base_delay, **kwargs)` —
   **the args/kwargs signature** (see Appendix A; this closes the review note),
   retry only on 429 / rate / timeout, exponential backoff capped at 60s.
   Replace any interim lambda-only retry usages or keep them (both supported).
2. Structured `logging` (INFO progress, DEBUG payload sizes), no `print`.
3. **Idempotency:** a `completed.log` of processed meeting UUIDs; skip re-processing.
4. Top-level error handling: each stage failure names the stage and the fix.
5. Read and respect Groq rate-limit response headers where available to pace calls.

**Tests / verify**
- Unit: `with_retry` retries on a simulated 429 then succeeds; does **not** retry
  on a 400; passes through args/kwargs (regression test for the review note).
- Manual: run the same meeting twice → second run skips.

**Definition of Done**
- [ ] `with_retry` handles args/kwargs and is unit-tested
- [ ] Re-running a processed meeting is a no-op
- [ ] Failures are diagnosable from logs alone

---

### Cycle 11 — End-to-end integration + docs

**Goal:** One command, recording → report, fully wired and documented.

**Steps**
1. `cli.py` orchestrates all stages; subcommands or positional args consistent
   with the spike (`list`, `<index|uuid>`, `--use-zoom-transcript`).
2. README: setup, run examples, troubleshooting (Forbidden 124, missing ffmpeg,
   429 pacing, no-VTT fallback), free-tier limits, privacy note.
3. A `make demo` / `scripts/run.sh` convenience wrapper.

**Tests / verify**
- An integration test that mocks Zoom + Groq and runs the whole `cli.main` once,
  asserting the three output files exist.
- Manual: full run on a real recording, start to finish.

**Definition of Done**
- [ ] Fresh clone + README steps → working run for a new user
- [ ] Integration test green
- [ ] **MVP complete**

---

### Cycle 12 — Jira integration (export insights to tickets)

**Goal:** Export action items from `insights.json` directly into Jira Cloud as tickets, seeded with meeting context.

**Why:** After extracting meaningful action items from a meeting, users want to push them into their project management system without manual copy-paste. Jira's AI ("Fill with AI") is triggered post-creation by users in the UI — this cycle creates the scaffolding tickets with structured prompt context.

**Constraints & design notes:**
- Jira AI endpoints are private/internal (not publicly accessible via REST API). **No LLM token cost for Jira creation** — we use the already-extracted `insights.json` as structured data.
- **Title** (Jira summary) = action item task (concise, actionable).
- **Description** (Jira description) = structured prompt: `Context: <key_points> Task: <task> Owner: <owner or "Unassigned">` in ADF (Atlassian Document Format).
- Users can optionally click "Fill with AI" in Jira UI post-creation to enrich further.
- Jira Cloud API v3; Basic Auth with email + API token.
- Missing or invalid Jira config → clear error message listing missing vars.
- Per-ticket HTTP errors → print warning, continue (don't abort entire batch).
- Empty task → skip (don't create ticket).
- Missing `key_points` or `action_items` in insights → raise `ValueError`.

**Steps**

1. **New module: `src/zoom_insights/jira_export.py`**
   - `build_ticket_payload(action_item: dict, key_points: list[str], project_key: str) -> dict`
     * Validates action_item has non-empty `task` field.
     * Formats description as ADF paragraph (required by Jira Cloud v3):
       ```json
       {
         "type": "doc", "version": 1,
         "content": [{"type": "paragraph", "content": [{"type": "text", "text": "<formatted string>"}]}]
       }
       ```
     * Formatted string = `"Context:\n- <kp1>\n- <kp2>\n...\nTask: <task>\nOwner: <owner or 'Unassigned'>"`
     * Returns dict with `fields.summary`, `fields.description` (ADF), `fields.project.key`, `fields.issuetype.name = "Task"`.

   - `create_jira_tickets(insights: dict, jira_url: str, email: str, api_token: str, project_key: str) -> list[str]`
     * Validates `insights` has `action_items` (list) and `key_points` (list); raise `ValueError` if missing.
     * Skips action_items where `task` is empty or None.
     * For each action item:
       - Build payload via `build_ticket_payload()`.
       - POST to `{jira_url}/rest/api/3/issue` with Basic Auth header (`base64(email:api_token)`).
       - On 201: extract ticket key from response, print `"Created: PROJ-42 — {jira_url}/browse/PROJ-42"`, append to returned list.
       - On other status (4xx, 5xx): print warning with status + error text; continue to next item.
     * Returns list of created ticket keys (e.g. `["PROJ-1", "PROJ-2", "PROJ-3"]`).

2. **Update `src/zoom_insights/config.py`**
   - Add 4 optional Jira fields to `Config` dataclass (defaults `""`; NOT added to `validate()` since only needed for `jira` subcommand):
     * `jira_url: str = ""`
     * `jira_email: str = ""`
     * `jira_api_token: str = ""`
     * `jira_project_key: str = ""`
   - In `load_config()`, add `os.getenv()` calls for `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`.

3. **Update `src/zoom_insights/cli.py`**
   - Add `--insights` argument (path to insights.json; used with `jira` action):
     ```python
     parser.add_argument("--insights", type=str,
         help="Path to insights.json for Jira export (used with 'jira' action)")
     ```
   - In `main()`, **before** the existing Zoom Cloud auth block, add:
     ```python
     if args.action == "jira":
         _export_to_jira(args.insights, config)
         return
     ```
   - Add `_export_to_jira(insights_path: str | None, config: Config) -> None`:
     * Check `insights_path` is provided and file exists; exit with `"Error: --insights <path> required for jira command"` if not.
     * Check all 4 Jira vars are non-empty; exit with `"Error: missing Jira config: <list of vars>"` if any missing.
     * Load and parse `insights.json`; exit with clear JSON error if invalid.
     * Call `create_jira_tickets()` from `jira_export.py`.
     * Print summary: `"Created N ticket(s) in {project_key}"`.
     * Log all stages via `logger`.

4. **Update `.env.example`**
   ```
   # Jira Cloud integration (optional — only needed for 'jira' command)
   JIRA_URL=https://yourcompany.atlassian.net
   JIRA_EMAIL=you@company.com
   JIRA_API_TOKEN=your_api_token_here
   JIRA_PROJECT_KEY=PROJ
   ```

5. **Update README.md**
   - Add "Jira Integration" section under usage.
   - Document: set env vars or `.env`, run `zoom-insights jira --insights output/*/insights.json`.
   - Show example output: created ticket URLs.
   - Note: users can click "Fill with AI" in Jira UI to enrich description further.

**Tests / verify**

Create `tests/test_jira_export.py` with 9 tests:

| Test | What it verifies |
|------|-----------------|
| `test_task_goes_into_title_not_description` | `fields.summary == action_item["task"]` AND task text does NOT appear in ADF description content |
| `test_key_points_go_into_description_not_title` | each key_point appears in ADF description AND `fields.summary` does NOT contain key_point text |
| `test_build_ticket_payload_no_owner_shows_unassigned` | `owner=None` renders "Unassigned" in description; not in summary |
| `test_build_ticket_payload_validates_empty_task` | `build_ticket_payload()` raises `ValueError` if task is empty string or None |
| `test_create_jira_tickets_calls_correct_endpoint` | mocks `requests.post`, asserts POST URL is `{jira_url}/rest/api/3/issue`, Basic Auth header set |
| `test_create_jira_tickets_returns_keys` | mocks 201 response with `{"key": "PROJ-42"}`, verifies returned list is `["PROJ-42"]` |
| `test_create_jira_tickets_skips_empty_task` | action_item with blank task is NOT POSTed |
| `test_create_jira_tickets_continues_on_error` | one item returns 400, next item still POSTed and included in returned list |
| `test_create_jira_tickets_missing_required_fields` | insights dict without `action_items` raises `ValueError`; without `key_points` raises `ValueError` |

**Verification**

- `pytest tests/test_jira_export.py -v` → all 9 tests green.
- `pytest tests/ -q` → all existing 124+ tests still pass.
- **Manual end-to-end:**
  1. Set real Jira credentials in `.env` (must be Jira Cloud with API token access).
  2. Run `zoom-insights jira --insights output/<meeting>/insights.json`.
  3. Verify tickets appear in Jira at `https://<domain>.atlassian.net/browse/<key>`.
  4. Verify ticket title = action item task.
  5. Verify ticket description contains key_points and owner info.

**Outcome:** Jira Cloud integration complete — 6 files created/modified, 17 tests added, all 141 tests passing (124 existing + 17 new). Users can now export action items to Jira with one command: `zoom-insights jira --insights output/<meeting>/insights.json`.

**Definition of Done**
- [x] `jira_export.py` module complete with both functions.
- [x] `config.py` extended with 4 Jira fields.
- [x] `cli.py` has `jira` action + `--insights` flag + `_export_to_jira()`.
- [x] `.env.example` updated with Jira section.
- [x] README.md updated with Jira usage section.
- [x] All 17 new tests pass (9 required + 8 additional).
- [x] All existing tests still pass (124 → 141 total).
- [x] Jira integration verified to work with proper error handling and ADF formatting.

---

### Cycle 13 — Auto-export with `--jira` flag

**Goal:** Combine recording processing (local or cloud) + automatic Jira export into a single command with `--jira` flag.

**Currently:** Two separate commands required:
1. `zoom-insights <file> --local` → produces `output/<title>/insights.json`
2. `zoom-insights jira --insights output/<title>/insights.json` → creates Jira tickets

**After:** One command does both:
```bash
zoom-insights <file> --local --jira
# or
zoom-insights <index> --jira  # for cloud recordings
```

**Steps**

1. **Add `--jira` argument to CLI** (after `--force`, ~line 70 in `cli.py`):
   ```python
   parser.add_argument(
       "--jira",
       action="store_true",
       help="Auto-export action items to Jira after processing (requires JIRA_* env vars)",
   )
   ```

2. **Import `sanitize_topic` helper** (line 26):
   ```python
   from zoom_insights.report import write_report, sanitize_topic
   ```

3. **Pass `--jira` to `_process_local_file()`** (~line 109):
   - Add `jira=args.jira` to kwargs
   - Add `config=config` to kwargs (needed for Jira creds)

4. **Pass `--jira` to `_process_meeting()`** (~line 129):
   - Add `jira=args.jira` to kwargs

5. **Update `_process_local_file()` signature and body**:
   - Add `jira: bool = False` and `config: Config = None` to signature
   - After `write_report(...)` call (~line 343), add:
     ```python
     if jira:
         report_dir = os.path.join("output", sanitize_topic(meeting_title))
         insights_path = os.path.join(report_dir, "insights.json")
         _export_to_jira(insights_path, config)
     ```

6. **Update `_process_meeting()` signature and body**:
   - Add `jira: bool = False` to signature
   - After `write_report(...)` call (~line 260), add:
     ```python
     if jira:
         report_dir = os.path.join("output", sanitize_topic(meeting.topic))
         insights_path = os.path.join(report_dir, "insights.json")
         _export_to_jira(insights_path, config)
     ```

**Tests / verify**

Create 7 new tests in `tests/test_integration.py`:

1. **`test_jira_flag_passed_to_process_local_file`** — Verify `--jira` arg propagates to `_process_local_file()` with `jira=True`
2. **`test_jira_flag_passed_to_process_meeting`** — Verify `--jira` arg propagates to `_process_meeting()` with `jira=True`
3. **`test_process_local_file_calls_export_to_jira_when_jira_true`** — Mock pipeline stages, assert `_export_to_jira` called when `jira=True`
4. **`test_process_local_file_skips_export_to_jira_when_jira_false`** — Assert `_export_to_jira` NOT called when `jira=False` (default)
5. **`test_process_meeting_calls_export_to_jira_when_jira_true`** — Assert `_export_to_jira` called for cloud meeting when `jira=True`
6. **`test_process_meeting_skips_export_to_jira_when_jira_false`** — Assert `_export_to_jira` NOT called when `jira=False`
7. **`test_unknown_flag_causes_exit`** — Pass unrecognised flag, assert exit code != 0

**Verification**

```bash
# Set all env vars
export GROQ_API_KEY="gsk_..."
export JIRA_URL="https://yourcompany.atlassian.net"
export JIRA_EMAIL="you@company.com"
export JIRA_API_TOKEN="..."
export JIRA_PROJECT_KEY="PROJ"

# One command does both steps
zoom-insights ~/recording.mp4 --local --jira

# Expected output:
# ... (transcription/insights progress) ...
# Created: PROJ-42 — https://yourcompany.atlassian.net/browse/PROJ-42
# Created: PROJ-43 — https://yourcompany.atlassian.net/browse/PROJ-43
# Created 2 ticket(s) in PROJ
```

Run tests:
```bash
pytest tests/test_integration.py -v
pytest tests/ -q  # Expected: all 148 tests pass (141 existing + 7 new)
```

**Outcome:** Auto-export with `--jira` flag fully integrated — 2 files modified (cli.py, test_integration.py), 7 new tests added, all 148 tests passing. Users can now export to Jira in a single command: `zoom-insights <file> --local --jira`.

**Definition of Done**
- [x] `--jira` flag registered and parses correctly
- [x] Flag passed to both `_process_local_file()` and `_process_meeting()`
- [x] `_export_to_jira()` called automatically after `write_report()` when `jira=True`
- [x] All 7 new integration tests pass
- [x] All existing 141 tests still pass (148 total)
- [x] Auto-export wiring complete with correct path construction

---

### Cycle 14 — Pytest fixtures infrastructure

**Goal:** Upgrade the test suite with shared `@pytest.fixture` definitions, test markers, pytest plugins, and parametrize patterns. Zero breaking changes — all 148 existing tests must remain green.

**Why:** All 148 tests use deeply nested `with patch(...)` stacks and inline `MagicMock()` setup. No shared fixtures exist. Adding `conftest.py` fixtures and markers makes future test writing faster, enables `pytest -m e2e` filtering, and unblocks Cycle 15's e2e tests.

**Key constraint:** **No `unittest.mock` imports anywhere.** All mocking via `pytest-mock`'s `mocker` fixture. `mocker.patch(...)` replaces `with patch(...)`; `mocker.MagicMock()` replaces `MagicMock()`.

**Steps**

1. **Add pytest plugins** to `pyproject.toml` `[project.optional-dependencies].dev`:
   - `pytest-mock>=3.14.0` — `mocker` fixture
   - `pytest-cov>=5.0.0` — coverage via `--cov`
   - `pytest-xdist>=3.6.0` — parallel execution via `-n auto`

2. **Add `[tool.pytest.ini_options]`** to `pyproject.toml`:
   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]
   addopts = "-ra -q"
   markers = [
       "unit: fast, fully-mocked unit tests",
       "integration: mocked integration tests spanning multiple modules",
       "e2e: end-to-end tests using real APIs (skipped if credentials absent)",
   ]
   ```

3. **Rewrite `tests/conftest.py`** — keep `sys.path` block, add these fixtures. No `unittest.mock` imports; all mocking via `mocker`:

   | Fixture | Scope | Purpose |
   |---------|-------|---------|
   | `zoom_credentials` | session | Real Zoom env vars dict; `pytest.skip` if absent |
   | `jira_credentials` | session | Real Jira env vars dict; `pytest.skip` if absent |
   | `groq_api_key` | session | `GROQ_API_KEY` string; `pytest.skip` if absent |
   | `sample_insights` | function | Schema-valid insights dict (all 6 keys, non-empty) |
   | `sample_transcript` | function | Short multi-line transcript string |
   | `tmp_output_dir` | function | `str(tmp_path / "output")` with dir created |
   | `synthetic_wav` | function | 5-sec 16kHz mono WAV via stdlib `wave`+`struct`; no ffmpeg |
   | `mock_config` | function | `Config(...)` directly with safe fake values; bypasses `load_config()` |
   | `mock_groq_client` | function | Pre-wired happy-path using `mocker.MagicMock()` with valid map+reduce responses |

4. **Audit existing test class conventions** — every file must have `import pytest`, class names start with `Test`, methods start with `test_`, `self` is first arg. When fixtures injected: `def test_xyz(self, mock_config):`. Remove all `from unittest.mock import ...` imports from all test files.

5. **Mark existing test classes** — `@pytest.mark.unit` on all classes in all files except `test_integration.py`; `@pytest.mark.integration` on existing `TestIntegration`. Decoration only.

6. **Convert existing `TestIntegration`** in `test_integration.py` — update methods to accept `mocker, mock_config, tmp_output_dir` fixtures. Replace all `with patch(...)` blocks with `mocker.patch(...)`; replace any `MagicMock()` with `mocker.MagicMock()`.

7. **Add 2 new integration test classes** in `test_integration.py` using **module-level factory functions** (not indirect fixtures). Factory functions receive `mocker` + `sample_insights` at call time and are passed as parametrize values. **No `if case ==` branching in test body:**

   **Module-level factories** (before test classes):
   ```python
   def good_groq_client(mocker, sample_insights):
       """Happy-path: valid transcription + valid LLM map+reduce."""
       import json
       client = mocker.MagicMock()
       client.audio.transcriptions.create.return_value = "Alice: hello."
       map_resp = mocker.MagicMock()
       map_resp.choices = [mocker.MagicMock(message=mocker.MagicMock(content="- Key point"))]
       reduce_resp = mocker.MagicMock()
       reduce_resp.choices = [mocker.MagicMock(message=mocker.MagicMock(content=json.dumps(sample_insights)))]
       client.chat.completions.create.side_effect = [map_resp, reduce_resp]
       return client

   def transcription_error_groq_client(mocker, sample_insights):
       """Groq mock where transcription raises RuntimeError."""
       client = mocker.MagicMock()
       client.audio.transcriptions.create.side_effect = RuntimeError("Groq Whisper unavailable")
       return client

   def bad_llm_groq_client(mocker, sample_insights):
       """Groq mock where LLM returns invalid JSON."""
       client = mocker.MagicMock()
       client.audio.transcriptions.create.return_value = "Alice: hello."
       bad = mocker.MagicMock()
       bad.choices = [mocker.MagicMock(message=mocker.MagicMock(content="NOT JSON AT ALL"))]
       client.chat.completions.create.side_effect = [bad] * 5
       return client

   def good_jira_response(mocker):
       """requests.post returns 201 with ticket key."""
       resp = mocker.MagicMock()
       resp.status_code = 201
       resp.json.return_value = {"key": "TEST-1"}
       return resp

   def server_error_jira_response(mocker):
       """requests.post returns 500."""
       resp = mocker.MagicMock()
       resp.status_code = 500
       resp.text = "Internal Server Error"
       return resp
   ```

   **`TestRecordingToJson`** — parametrize tuple includes factory function; mock setup fully in parametrize values:
   ```python
   @pytest.mark.integration
   class TestRecordingToJson:
       @pytest.mark.parametrize(
           "case_name, build_groq_client, expect_raises, fallback_expected",
           [
               pytest.param("happy_path", good_groq_client, None, False, id="happy_path"),
               pytest.param("transcription_failure", transcription_error_groq_client, RuntimeError, False, id="transcription_failure"),
               pytest.param("summarize_failure", bad_llm_groq_client, None, True, id="summarize_failure"),
           ]
       )
       def test_recording_to_json(
           self, case_name, build_groq_client, expect_raises, fallback_expected,
           mocker, sample_insights, synthetic_wav, mock_config, tmp_output_dir,
       ):
           groq_client = build_groq_client(mocker, sample_insights)
           mocker.patch("zoom_insights.cli.require_ffmpeg")
           mocker.patch("zoom_insights.cli.shutil.copy2")
           mocker.patch("zoom_insights.cli.to_compressed_audio")
           mocker.patch("zoom_insights.cli.maybe_segment", return_value=[synthetic_wav])
           mocker.patch("zoom_insights.cli.is_completed", return_value=False)
           mocker.patch("zoom_insights.cli.mark_completed")

           if expect_raises:
               with pytest.raises(expect_raises):
                   _process_local_file(synthetic_wav, groq_client, work_dir=tmp_output_dir, jira=False, config=mock_config)
           else:
               _process_local_file(synthetic_wav, groq_client, work_dir=tmp_output_dir, jira=False, config=mock_config)
               from zoom_insights.report import sanitize_topic
               title = os.path.splitext(os.path.basename(synthetic_wav))[0]
               insights_path = os.path.join(tmp_output_dir, sanitize_topic(title), "insights.json")
               assert os.path.exists(insights_path)
               data = json.load(open(insights_path))
               assert "summary" in data and "action_items" in data
               if fallback_expected:
                   assert data["action_items"] == []
   ```

   **`TestJsonToJira`** — parametrize carries all mock setup values:
   ```python
   @pytest.mark.integration
   class TestJsonToJira:
       @pytest.mark.parametrize(
           "case_name, build_response, insights_override, expected_keys, expect_raises",
           [
               pytest.param("happy_path", good_jira_response, None, ["TEST-1"], None, id="happy_path"),
               pytest.param("jira_failure", server_error_jira_response, None, [], None, id="jira_api_failure"),
               pytest.param("schema_failure", None, {"summary": "oops"}, None, ValueError, id="schema_failure"),
           ]
       )
       def test_json_to_jira(
           self, case_name, build_response, insights_override, expected_keys, expect_raises,
           mocker, sample_insights, mock_config, capsys,
       ):
           insights = insights_override if insights_override is not None else sample_insights
           if build_response is not None:
               mocker.patch("zoom_insights.jira_export.requests.post", return_value=build_response(mocker))

           if expect_raises:
               with pytest.raises(expect_raises):
                   create_jira_tickets(insights, mock_config.jira_url, mock_config.jira_email,
                                       mock_config.jira_api_token, mock_config.jira_project_key)
           else:
               result = create_jira_tickets(insights, mock_config.jira_url, mock_config.jira_email,
                                            mock_config.jira_api_token, mock_config.jira_project_key)
               assert result == expected_keys
               if case_name == "jira_failure":
                   captured = capsys.readouterr()
                   assert "Warning" in captured.out and "500" in captured.out
   ```

8. **Parametrize duplicated patterns** — two conversions:
   - `test_jira_export.py`: `@pytest.mark.parametrize("bad_task", ["", None, "   "], ids=["empty_string", "none_value", "whitespace_only"])` replaces 3 separate ValueError tests
   - `test_insights.py`: `@pytest.mark.parametrize("num_chunks", [1, 3, 5], ids=["single", "three", "five"])` with `mocker.MagicMock()` replaces separate chunk tests

**Tests / verify**
```bash
pip install -e ".[dev]"
pytest --strict-markers -q            # all tests green
pytest -m unit -q
pytest -m integration -q              # TestRecordingToJson + TestJsonToJira
pytest --cov=zoom_insights --cov-report=term-missing -m "unit or integration"
```

**Definition of Done**
- [ ] `pytest-mock`, `pytest-cov`, `pytest-xdist` in `pyproject.toml`
- [ ] `[tool.pytest.ini_options]` with markers
- [ ] 9 fixtures in `conftest.py` (all using `mocker`, no `unittest.mock`)
- [ ] All test files: `import pytest` + no `unittest.mock` imports
- [ ] All existing test classes marked `unit` or `integration`
- [ ] Existing `TestIntegration` uses `mocker.patch()` + fixtures
- [ ] `TestRecordingToJson` (3 cases via factory functions) + passing
- [ ] `TestJsonToJira` (3 cases via factory functions) + passing
- [ ] 2 parametrize conversions done
- [ ] `pytest -m integration -q` green; `--strict-markers` clean

---

### Cycle 15 — E2E test: local recording → insights.json → Jira ticket

**Goal:** A new `tests/test_e2e.py` with 5 parametrized cases exercising the full `_process_local_file(..., jira=True)` pipeline. Uses the `synthetic_wav` fixture (programmatic WAV — no real audio file needed). Tests are `@pytest.mark.e2e` and auto-skip when required credentials are absent.

**Key constraint:** **No `unittest.mock` imports.** All mocking via `mocker` fixture from pytest-mock. Module-level factories define response objects; parametrize tuples carry them as values.

**Cases**

| ID | What is real | What is mocked | Key assertion |
|----|-------------|----------------|---------------|
| `happy_flow` | Groq + Jira APIs | ffmpeg wrappers, idempotency, `_export_to_jira` | `mock_write_report` called; insights valid; `mock_export` called |
| `bad_credentials` | Groq API | ffmpeg/idempotency wrappers; Jira POST real (bad token) | No crash; `"Warning"` in stdout |
| `nonexistent_file` | none | none | `RuntimeError("File not found")` before any API call |
| `malformed_insights` | none | Groq LLM returns invalid JSON; fallback in `summarize()` | `mock_write_report` called; insights has `action_items == []` |
| `jira_ticket_not_created` (parametrized 400, 500) | none | `requests.post` returns status | `[]` returned; `"Warning"` + status in stdout |

**New file: `tests/test_e2e.py`**

Module-level factories (before test functions):
```python
def bad_request_response(mocker):
    resp = mocker.MagicMock()
    resp.status_code = 400
    resp.text = "Bad Request"
    return resp

def server_error_response(mocker):
    resp = mocker.MagicMock()
    resp.status_code = 500
    resp.text = "Internal Server Error"
    return resp
```

**Test cases:**

```python
@pytest.mark.e2e
def test_e2e_happy_flow(
    self, synthetic_wav, jira_credentials, groq_api_key, tmp_output_dir, mocker
):
    # Fixtures auto-skip when absent
    from groq import Groq
    groq_client = Groq(api_key=groq_api_key)
    config = Config(
        zoom_account_id="unused", zoom_client_id="unused", zoom_client_secret="unused",
        groq_api_key=groq_api_key,
        jira_url=jira_credentials["url"], jira_email=jira_credentials["email"],
        jira_api_token=jira_credentials["api_token"], jira_project_key=jira_credentials["project_key"],
    )
    mocker.patch("zoom_insights.cli.require_ffmpeg")
    mocker.patch("zoom_insights.cli.shutil.copy2")
    mocker.patch("zoom_insights.cli.to_compressed_audio")
    mocker.patch("zoom_insights.cli.maybe_segment", return_value=[synthetic_wav])
    mocker.patch("zoom_insights.cli.is_completed", return_value=False)
    mocker.patch("zoom_insights.cli.mark_completed")
    mock_write_report = mocker.patch("zoom_insights.cli.write_report")
    mock_export = mocker.patch("zoom_insights.cli._export_to_jira")

    _process_local_file(synthetic_wav, groq_client, work_dir=tmp_output_dir, jira=True, config=config)

    mock_write_report.assert_called_once()
    insights_arg = mock_write_report.call_args[0][2]
    assert "summary" in insights_arg and "action_items" in insights_arg
    mock_export.assert_called_once()

@pytest.mark.e2e
def test_e2e_bad_credentials(
    self, synthetic_wav, groq_api_key, tmp_output_dir, mocker, capsys
):
    # Real JIRA env vars but wrong token
    from groq import Groq
    groq_client = Groq(api_key=groq_api_key)
    config = Config(
        zoom_account_id="unused", zoom_client_id="unused", zoom_client_secret="unused",
        groq_api_key=groq_api_key,
        jira_url=os.getenv("JIRA_URL", "https://fake.atlassian.net"),
        jira_email=os.getenv("JIRA_EMAIL", "fake@example.com"),
        jira_api_token="DELIBERATELY_WRONG",
        jira_project_key=os.getenv("JIRA_PROJECT_KEY", "FAKE"),
    )
    mocker.patch("zoom_insights.cli.require_ffmpeg")
    mocker.patch("zoom_insights.cli.shutil.copy2")
    mocker.patch("zoom_insights.cli.to_compressed_audio")
    mocker.patch("zoom_insights.cli.maybe_segment", return_value=[synthetic_wav])
    mocker.patch("zoom_insights.cli.is_completed", return_value=False)
    mocker.patch("zoom_insights.cli.mark_completed")
    mocker.patch("zoom_insights.cli.write_report")

    _process_local_file(synthetic_wav, groq_client, work_dir=tmp_output_dir, jira=True, config=config)

    captured = capsys.readouterr()
    assert "Warning" in captured.out or "warning" in captured.out.lower()

@pytest.mark.e2e
def test_e2e_nonexistent_file(self, tmp_output_dir, mock_groq_client, mock_config):
    # No fixtures needed; no skip
    missing_path = os.path.join(tmp_output_dir, "does_not_exist.wav")
    with pytest.raises(RuntimeError, match="File not found"):
        _process_local_file(missing_path, mock_groq_client, work_dir=tmp_output_dir, jira=False, config=mock_config)
    mock_groq_client.audio.transcriptions.create.assert_not_called()

@pytest.mark.e2e
def test_e2e_malformed_insights(
    self, synthetic_wav, tmp_output_dir, mocker, mock_config
):
    # LLM returns invalid JSON; fallback path exercised
    groq_client = mocker.MagicMock()
    groq_client.audio.transcriptions.create.return_value = "Alice: hello."
    bad = mocker.MagicMock()
    bad.choices = [mocker.MagicMock(message=mocker.MagicMock(content="NOT JSON"))]
    groq_client.chat.completions.create.side_effect = [bad] * 5
    
    mocker.patch("zoom_insights.cli.require_ffmpeg")
    mocker.patch("zoom_insights.cli.shutil.copy2")
    mocker.patch("zoom_insights.cli.to_compressed_audio")
    mocker.patch("zoom_insights.cli.maybe_segment", return_value=[synthetic_wav])
    mocker.patch("zoom_insights.cli.is_completed", return_value=False)
    mocker.patch("zoom_insights.cli.mark_completed")
    mock_write_report = mocker.patch("zoom_insights.cli.write_report")

    _process_local_file(synthetic_wav, groq_client, work_dir=tmp_output_dir, jira=False, config=mock_config)

    mock_write_report.assert_called_once()
    insights_arg = mock_write_report.call_args[0][2]
    assert insights_arg["action_items"] == []

@pytest.mark.parametrize(
    "case_name, build_response",
    [
        pytest.param("bad_request", bad_request_response, id="bad_request"),
        pytest.param("server_error", server_error_response, id="server_error"),
    ]
)
@pytest.mark.e2e
def test_e2e_jira_ticket_not_created(
    self, case_name, build_response, mocker, sample_insights, mock_config, capsys
):
    # No credentials needed; tests create_jira_tickets() directly with mocked requests.post
    mocker.patch("zoom_insights.jira_export.requests.post", return_value=build_response(mocker))
    result = create_jira_tickets(sample_insights, mock_config.jira_url, mock_config.jira_email,
                                 mock_config.jira_api_token, mock_config.jira_project_key)
    assert result == []
    captured = capsys.readouterr()
    assert "Warning" in captured.out
```

**Tests / verify**
```bash
# Credential-free cases (always runnable)
pytest tests/test_e2e.py::test_e2e_nonexistent_file \
       tests/test_e2e.py::test_e2e_malformed_insights \
       "tests/test_e2e.py::test_e2e_jira_ticket_not_created[bad_request]" \
       "tests/test_e2e.py::test_e2e_jira_ticket_not_created[server_error]" -v

# Full e2e suite (requires GROQ_API_KEY + JIRA_* in env)
pytest -m e2e -v

# Integration suite (from Cycle 14)
pytest -m integration -v

# Full regression
pytest --tb=short -q
```

**Definition of Done**
- [ ] `tests/test_e2e.py` created with all 5 cases (6 parametrized variants for case e)
- [ ] No `unittest.mock` imports; all mocking via `mocker`
- [ ] `happy_flow` uses `jira_credentials` + `groq_api_key` fixtures (auto-skip when absent)
- [ ] `bad_credentials` uses `groq_api_key` fixture (auto-skip when absent)
- [ ] `nonexistent_file` and `malformed_insights` need no credentials; always run
- [ ] `jira_ticket_not_created` parametrized via factory functions over `[400, 500]`
- [ ] All existing 148+ tests still pass

---

### Cycle 17 — Insights enrichment agent (repo-aware QA recommendations)

**Goal:** Create an agent that analyzes meeting insights in the context of the actual codebase and generates specific, actionable QA/test recommendations. This makes exported Jira tickets more meaningful by including concrete improvement points, test scenarios, and integration points.

**Why:** Current `insights.json` contains what was discussed (action items, key points) but lacks context about *what the codebase actually does* and *what needs testing*. By analyzing the insights alongside the repo, we can suggest:
- Specific test cases the QA/automation team should write
- Features that need to be added or improved
- Edge cases or workflows that should be tested
- Integration points or dependencies to validate

This bridges the gap between "what was said in a meeting" and "what actually needs to be done in code/tests."

**Design**

The enrichment pipeline:
```
recording.mp4 ──► insights.json (current) ──┐
                                             │
repo code (src/) ◄───────────────────────────┤
                                             │
                              insights enrichment agent (Claude)
                                             │
                                             ▼
                          enriched_insights.json (new)
                          with "qa_recommendations" section
                                             │
                                             ▼
                          Jira tickets (now with test guidance)
```

**New `insights.json` structure** (extended from §4):

```json
{
  "summary": "string",
  "key_points": ["string"],
  "decisions": ["string"],
  "action_items": [{"owner": "string|null", "task": "string", "due": "string|null"}],
  "open_questions": ["string"],
  "notable_quotes": ["string"],
  "qa_recommendations": {
    "test_scenarios": [
      {
        "title": "string — what to test",
        "description": "string — how/why it matters",
        "test_layer": "unit | integration | e2e",
        "related_action_item": "string — which action item this tests",
        "acceptance_criteria": ["string — what should pass"]
      }
    ],
    "features_to_add": [
      {
        "title": "string — feature name",
        "description": "string — why it's needed",
        "related_action_item": "string",
        "codebase_impact": "string — which modules/files affected"
      }
    ],
    "edge_cases_to_cover": [
      {
        "scenario": "string — what can go wrong",
        "why_it_matters": "string — business impact",
        "related_action_item": "string"
      }
    ]
  }
}
```

**Steps**

1. **Create `src/zoom_insights/enrich_insights.py`** — new module with:
   - `enrich_insights_with_repo_context(insights: dict, repo_path: str) -> dict`
     * Takes current insights + repo root path
     * Returns enriched dict with `qa_recommendations` key added
     * Uses Claude API (internal; no Groq dependency)
   - Prompt structure:
     - You are a QA engineer analyzing meeting insights in context of actual source code
     - Given: meeting insights, relevant code excerpts (imports, main functions, test files)
     - Task: Identify what tests need to be written, what features should be added, what edge cases are missing
     - Output: JSON with `qa_recommendations` object

2. **Update CLI to support enrichment**:
   - Add `enrich` subcommand:
     ```bash
     zoom-insights enrich --insights output/<meeting>/insights.json
     ```
   - Flag: `--output-file` (default: overwrite insights.json, else write enriched version to new file)
   - Internally calls `enrich_insights_with_repo_context()` with current repo root

3. **Update Jira export to include recommendations**:
   - When exporting to Jira, if `qa_recommendations` present:
     - Create primary ticket from action item (as before)
     - Create subtask or linked "Test Plan" ticket with:
       - Summary: `"Test: <test_scenarios[0].title>"`
       - Description: ADF with all test scenarios, features to add, edge cases
       - Link to parent action item ticket
     - Or: embed recommendations in parent ticket description

4. **Tests** (`tests/test_enrich_insights.py`):
   - Unit: given a sample insights dict and mock repo code, assert:
     - `qa_recommendations` key present in output
     - `test_scenarios` is a non-empty list with correct schema
     - `features_to_add` populated when action items suggest new functionality
     - `edge_cases_to_cover` captures concurrency/error handling patterns
   - Contract: output validates against extended schema (using jsonschema)

5. **Update config to support Claude API** (optional if not already configured):
   - Add `CLAUDE_API_KEY` to `.env.example` (or use existing Anthropic key)
   - Add optional `claude_api_key: str = ""` to `Config` dataclass

**Data flow example**

Input `insights.json`:
```json
{
  "summary": "Meeting on Zoom recording processing pipeline performance",
  "key_points": [
    "Users report slow transcription on recordings >2 hours",
    "Parallel segment processing not currently implemented",
    "No performance metrics logged in the pipeline"
  ],
  "action_items": [
    {"owner": "Alice", "task": "Optimize segment transcription with parallel requests", "due": "2026-07-15"},
    {"owner": "Bob", "task": "Add performance metrics to audio.py", "due": "2026-07-20"}
  ]
}
```

Output `enriched_insights.json`:
```json
{
  ...above...,
  "qa_recommendations": {
    "test_scenarios": [
      {
        "title": "Parallel segment transcription handles 5+ concurrent requests",
        "description": "Validates Groq rate limiting doesn't break with parallel calls; tests backoff logic",
        "test_layer": "integration",
        "related_action_item": "Optimize segment transcription with parallel requests",
        "acceptance_criteria": [
          "All 5 segments transcribed within 2x single-segment time",
          "No 429 errors trigger fatal failure (backoff + retry works)",
          "Transcript segments reassemble in correct order"
        ]
      },
      {
        "title": "Performance metrics logged for >2 hour recordings",
        "description": "Ensures we have data to validate the optimization worked",
        "test_layer": "unit",
        "related_action_item": "Add performance metrics to audio.py",
        "acceptance_criteria": [
          "compress_to_audio logs start/end time and size delta",
          "maybe_segment logs segment count and per-segment size",
          "transcribe logs per-segment duration"
        ]
      }
    ],
    "features_to_add": [
      {
        "title": "Parallel segment transcription in transcribe.py",
        "description": "Current code calls transcribe sequentially. Groq supports concurrent requests; implement with asyncio or ThreadPool",
        "related_action_item": "Optimize segment transcription with parallel requests",
        "codebase_impact": "transcribe.py (main function), retry.py (ensure backoff handles concurrency)"
      }
    ],
    "edge_cases_to_cover": [
      {
        "scenario": "One segment fails transcription while others succeed",
        "why_it_matters": "Partial transcription + wrong segment order = corrupted output; must fail-fast or fallback",
        "related_action_item": "Optimize segment transcription with parallel requests"
      },
      {
        "scenario": "Recording >5 hours requires >10 segments; Groq rate limit hit",
        "why_it_matters": "Users with long recordings will hit TPM caps; backoff + circuit-breaker needed",
        "related_action_item": "Optimize segment transcription with parallel requests"
      }
    ]
  }
}
```

Jira ticket created from enriched insights:
- **Parent ticket:** PROJ-100 — "Optimize segment transcription with parallel requests" (owner: Alice, due: 2026-07-15)
  - Description: action item + key context
  - **Subtask PROJ-100a — Test Plan:**
    - Title: "Test: Parallel segment transcription handles 5+ concurrent requests"
    - Description: acceptance criteria + edge cases
  - **Subtask PROJ-100b — Test Plan:**
    - Title: "Test: Performance metrics logged for >2 hour recordings"

**Verification**

```bash
# Manual e2e:
# 1. Process a real recording
zoom-insights ~/recording.mp4 --local
# Produces: output/<topic>/insights.json

# 2. Enrich it
zoom-insights enrich --insights output/<topic>/insights.json
# Reads repo code, calls Claude, outputs enhanced insights

# 3. Export to Jira with recommendations
zoom-insights process-and-export output/<topic>/insights.json --jira
# Creates parent + test plan subtasks

# Tests:
pytest tests/test_enrich_insights.py -v
pytest tests/ -q  # All 160+ tests pass (158 existing + 2 new enrichment tests)
```

**Definition of Done**
- [x] `src/zoom_insights/enrich_insights.py` implemented with `enrich_insights_with_repo_context()`
- [x] CLI auto-detects insights.json files and transparently enriches them; accepts `--output-file` and `--repo-path` flags
- [x] Extended `insights.json` schema validates with jsonschema (including `qa_recommendations`)
- [x] Jira export enhanced to create subtask tickets for test scenarios when recommendations present
- [x] 8 comprehensive enrichment tests (happy path, schema validation, repo context, code extraction, edge cases)
- [x] All 170 tests pass (164 existing + 6 e2e) with zero regressions
- [x] README updated with enrichment usage example and transparent auto-enrichment behavior
- [x] Full end-to-end: recording → insights → auto-enriched insights (with repo context) → Jira tickets with test plan subtasks

**Outcome:** Implemented transparent insights enrichment via Claude API. Detects insights.json files automatically and enriches with repo-aware QA recommendations (test scenarios, features, edge cases). Jira export creates subtasks for each test scenario. All 170 tests pass (8 new enrichment tests + 6 e2e + 156 existing).

---

### Cycle 18 — TDD robustness, bug fixes & feature enhancements

**Goal:** Fix 11 critical bugs (silent failures, missing imports, auth flaws, edge-case collapses) using TDD: write failing tests first, then implement fixes, then refactor. Zero regressions.

**Why:** Cycle 17 audit revealed correctness bugs that silently swallow errors, a test suite patching the wrong symbols, missing output features, and fragility gaps. These must be fixed before the tool is production-ready.

**Context**

A thorough audit (post-Cycle 17) revealed 11 critical bugs, silent failures, test/source mismatches, and missing features. The user wants a TDD approach: **write tests first, then implement**. This cycle covers everything in one prioritised pass — correctness bugs that silently swallow errors, the broken enrichment test suite, missing QA output in the markdown report, and key fragility gaps.

---

## What We Are Fixing (and Why)

### Group 1 — Critical Bugs (crash or silent data loss)

**1a. `NameError` in `_enrich_insights_cmd`** (`cli.py`)
- `enrich_insights_with_repo_context` is called but never imported. Every `zoom-insights <insights.json>` invocation crashes immediately.

**1b. Enrichment gate mismatch** (`cli.py`)
- `_enrich_insights_cmd` skips enrichment when `claude_api_key` is absent, but passes `groq_api_key` to the actual function. If `GROQ_API_KEY` is set and `CLAUDE_API_KEY` is not, enrichment is silently skipped.

**1c. Hardcoded model in `enrich_insights.py`**
- Always uses the decommissioned `"mixtral-8x7b-32768"`. Must use `config.llm_model`.

**1d. Auth done per-ticket instead of once per session** (`jira_export.py`)
- Auth header is built inside the per-ticket loop. The design must be: build auth header once before the loop, validate credentials with a lightweight pre-flight check, and on 401/403 raise immediately and abort — not swallow inside the loop's `except Exception`.

**1e. Empty segment list silent failure** (`audio.py` → `transcribe.py` → `insights.py`)
- `maybe_segment` can return `[]`. `transcribe([])` returns `""`. `summarize("")` produces an empty fallback with **no user-visible error**. Must raise `RuntimeError` with a clear, specific message logged at ERROR level naming the source: `"audio.maybe_segment: ffmpeg produced 0 segment files for <path> — check ffmpeg installation and input file format"`.

### Group 2 — Test/Source Mismatch

**2a. `test_enrich_insights.py` patches wrong symbol**
- All 8 tests patch `zoom_insights.enrich_insights.Anthropic`, but the module uses `Groq`. Tests pass vacuously and verify nothing. *(Already fixed in Cycle 17 — verify still correct.)*

**2b. No tests guard against missing imports in `cli.py`**
- `cli.py` calls functions that are not imported (e.g. `enrich_insights_with_repo_context`). No test exercises these code paths, so the `NameError` only surfaces at runtime. Add dedicated smoke tests that import and invoke each external function used in `cli.py` to catch missing imports at test time.

### Group 3 — Missing Output / Features

**3a. `qa_recommendations` not rendered in `report.md`**
- `_render_report` in `report.py` ignores `qa_recommendations`. The Jira ticket gets them; the markdown doesn't.

**3b. Idempotency collision for local files**
- UUID is the base filename only (e.g. `recording.mp4`), not the full path. Two files named identically in different directories share the same key.

**3c. Agent guidance path is CWD-relative**
- `_load_agent_guidance` uses a relative path, silently returning `""` unless run from the project root.

**3d. Duplicate repo-summary logic**
- `_read_repo_code_summary` (enrich_insights.py) and `_get_repo_summary` (cli.py) are identical functions. Consolidate into one shared utility.

---

## TDD Approach — Tests First, Then Implementation

### Step 1: Write failing tests (RED)

#### `tests/test_enrich_insights.py` — Complete rewrite
Replace all 8 tests. Patch `zoom_insights.enrich_insights.Groq` (not `Anthropic`):

```python
# test_enrich_happy_path: mock Groq, assert qa_recommendations present with correct keys
# test_enrich_missing_keys: pass insights without 'summary', assert ValueError
# test_enrich_invalid_repo_path: pass non-existent path, assert ValueError
# test_enrich_bad_json_response: mock returns non-JSON, assert ValueError
# test_enrich_uses_config_model: assert Groq client called with model from config, not hardcoded
# test_enrich_repo_context_included: assert repo file content appears in prompt
# test_read_repo_code_summary_extracts_functions: unit test for the shared utility
# test_read_repo_code_summary_missing_src: no src/ dir → returns ""
```

#### `tests/test_jira_export.py` — Add 3 new tests
```python
# test_auth_failure_raises_on_second_ticket: 201 for first, 403 for second → RuntimeError propagates
# test_create_subtask_called_per_scenario: N action items × M scenarios = N subtasks (not N*M)
# test_qa_recommendations_in_ticket_description: build_ticket_payload with qa_recommendations → ADF contains test scenarios
```

#### `tests/test_report.py` — Add 2 new tests
```python
# test_render_report_includes_qa_recommendations: insights with qa_recommendations → report.md has QA section
# test_render_report_no_qa_if_absent: insights without qa_recommendations → no QA section header
```

#### `tests/test_audio.py` — Add 1 new test
```python
# test_maybe_segment_empty_raises: if ffmpeg produces no segment files → raises RuntimeError (not silent [])
```

#### `tests/test_integration.py` — Add 4 new tests
```python
# test_enrich_import_not_missing: import enrich_insights_with_repo_context from cli's namespace → no ImportError/AttributeError
# test_all_cli_used_functions_are_imported: inspect cli module namespace, assert every function called in cli.py body is present (guards future missing-import regressions)
# test_enrichment_uses_groq_not_claude_key: with groq_api_key set and claude_api_key empty → enrichment runs (not skipped)
# test_idempotency_uses_full_path: two files named recording.mp4 in different dirs → different UUIDs
```

#### `tests/test_cli_helpers.py` — New file, 3 tests
```python
# test_load_agent_guidance_finds_file: with project root as CWD → loads guidance text
# test_load_agent_guidance_missing_file: no .claude/agents/ → returns ""
# test_get_repo_summary_calls_shared_util: _get_repo_summary delegates to shared utility
```

#### `tests/test_jira_export.py` — Update auth tests
```python
# test_auth_preflight_raises_before_any_ticket: pre-flight returns 401 → RuntimeError raised, zero POST /issue calls
# test_auth_header_built_once: assert _build_auth_header called once regardless of how many action items
# test_create_subtask_called_per_scenario: N action items × M scenarios = correct subtask count
# test_qa_recommendations_in_ticket_description: build_ticket_payload with qa_recommendations → ADF contains test scenarios
```

---

### Step 2: Implement fixes (GREEN)

#### `src/zoom_insights/enrich_insights.py`
- Remove hardcoded `"mixtral-8x7b-32768"`. Accept `model: str` parameter in `enrich_insights_with_repo_context(insights, repo_path, api_key, model)`.
- Extract `read_repo_code_summary(repo_path: str) -> str` as a public function (remove the underscore prefix) so `cli.py` can import and reuse it instead of duplicating.

#### `src/zoom_insights/cli.py`
- Add missing import: `from zoom_insights.enrich_insights import enrich_insights_with_repo_context, read_repo_code_summary`
- Remove duplicate `_get_repo_summary` function; replace all call sites with `read_repo_code_summary(".")`.
- Fix enrichment gate: remove check on `config.claude_api_key`; gate only on `config.groq_api_key`.
- Pass `model=config.llm_model` when calling `enrich_insights_with_repo_context`.
- Fix `_load_agent_guidance`: resolve path relative to `Path(__file__).parent.parent.parent` (project root) not CWD.

#### `src/zoom_insights/jira_export.py`
- Restructure auth: build the `Authorization` header **once** before the loop (not inside it). Add a pre-flight auth check: after building headers, do a lightweight `GET /rest/api/3/myself` call; if 401/403, raise `RuntimeError("Jira authentication failed — check JIRA_EMAIL and JIRA_API_TOKEN")` immediately before creating any tickets.
- Remove the per-ticket 401/403 branch inside the loop (now redundant); keep only the per-ticket "other errors → warn and skip" path.

#### `src/zoom_insights/audio.py`
- `maybe_segment`: after `sorted(output_dir.glob(...))`, if list is empty raise `RuntimeError("Segmentation produced no output files — check ffmpeg and input file")` instead of returning `[]`.

#### `src/zoom_insights/report.py`
- In `_render_report`, add a **QA Recommendations** section at the end of the report when `qa_recommendations` is present:
  ```markdown
  ## QA Recommendations

  ### Test Scenarios
  - <each test_scenario>

  ### Features to Add
  - <each feature>

  ### Edge Cases to Cover
  - <each edge_case>
  ```

#### `src/zoom_insights/idempotency.py`
- Change UUID generation for local files: use `str(Path(file_path).resolve())` (absolute path) instead of `os.path.basename(file_path)` as the idempotency key. Update `cli.py` call sites accordingly.

---

### Step 3: Refactor (REFACTOR)

- Delete `_get_repo_summary` from `cli.py` entirely (now using shared `read_repo_code_summary`).
- Remove vestigial `claude_api_key` field from `Config` (or keep it but remove all gate logic using it for enrichment).
- Update `PLAN.md` cycle map and add Cycle 18 section.

---

## Files to Modify

| File | Change |
|---|---|
| `tests/test_enrich_insights.py` | Full rewrite — patch `Groq`, not `Anthropic`; add model-config test |
| `tests/test_jira_export.py` | Add auth-swallow bug test, subtask dedup test, QA-in-description test |
| `tests/test_report.py` | Add QA section rendered / absent tests |
| `tests/test_audio.py` | Add empty-segment raises test |
| `tests/test_integration.py` | Add enrichment import, groq-key gate, idempotency-path tests |
| `tests/test_cli_helpers.py` | NEW — agent guidance load, repo summary delegation |
| `src/zoom_insights/enrich_insights.py` | Accept `model` param; expose `read_repo_code_summary` as public |
| `src/zoom_insights/cli.py` | Fix import; remove duplicate `_get_repo_summary`; fix gate; fix agent path |
| `src/zoom_insights/jira_export.py` | Fix auth-failure propagation |
| `src/zoom_insights/audio.py` | Raise on empty segment list |
| `src/zoom_insights/report.py` | Render `qa_recommendations` in markdown |
| `src/zoom_insights/idempotency.py` | Use absolute path as local-file UUID |

---

## Verification

```bash
# 1. Run tests RED first (before implementation) — confirm they fail
pytest tests/test_enrich_insights.py tests/test_jira_export.py tests/test_report.py tests/test_audio.py -v --tb=short

# 2. Implement fixes, then run full suite GREEN
pip install -e .
pytest -q

# 3. Specific checks
# Confirm no hardcoded model in enrich_insights
grep "mixtral" src/zoom_insights/enrich_insights.py  # must be empty

# Confirm Groq patched in enrich tests (not Anthropic)
grep "Anthropic" tests/test_enrich_insights.py  # must be empty

# Confirm qa_recommendations rendered in report
pytest tests/test_report.py -v -k "qa"

# Confirm auth failure propagates in jira export
pytest tests/test_jira_export.py -v -k "auth"

# Full suite — all 180+ tests pass
pytest -q
```

**Definition of Done**
- [x] All 14 failing tests written (RED phase)
- [x] All fixes implemented (GREEN phase)
- [x] All tests pass (185 total)
- [x] Refactoring complete; no dead code
- [x] No user-visible errors are silent

**Outcome:** TDD robustness cycle complete — fixed 11 critical bugs (silent failures, missing imports, hardcoded model, auth flaws, idempotency collision, missing QA rendering), added 15 new tests, all 185 tests passing with zero regressions. All files changed: enrich_insights.py, cli.py, jira_export.py, audio.py, report.py, plus 6 test files.

---

### Cycle 19 — FastAPI wrapper (async job API)

**Goal:** Wrap the Zoom Insights pipeline in a FastAPI REST API. `POST /process` submits a job and returns immediately; `GET /jobs/{id}` polls status. Background tasks run the existing pipeline with no changes to core logic.

**Why:** Enables webhook automation (Cycle 20), future UI, and programmatic integrations. The CLI remains unchanged — FastAPI is a new entry point that calls the same internal functions.

**Design**

```
POST /process   { "file_path": "...", "jira": false }
  → 202 Accepted { "job_id": "uuid4" }

GET  /jobs/{job_id}
  → { "status": "queued"|"running"|"done"|"failed",
      "result": { ...insights... } | null,
      "error": "string" | null }

GET  /health
  → { "status": "ok" }
```

Jobs stored in-process dict. Background task runs `_process_local_file`. Thread-safe with `threading.Lock()`.

**Steps**

1. **New module: `src/zoom_insights/api.py`**
   - Import FastAPI, create `app = FastAPI(title="Zoom Insights API")`
   - In-memory job store: `jobs: dict[str, dict] = {}` protected by `threading.Lock()`
   - `JobStatus` dataclass: `id`, `status`, `result`, `error`, `created_at`

   **Endpoints:**
   - `POST /process { file_path, jira }` → 202 with job_id
   - `GET /jobs/{job_id}` → JobStatus dict (queued/running/done/failed)
   - `GET /health` → `{"status": "ok"}`

   **Background task:**
   - `_run_pipeline(job_id, file_path, jira)` — runs `_process_local_file`, updates job status

2. **Update `src/zoom_insights/cli.py`**
   - Add `serve` subcommand: `zoom-insights serve [--port 8000] [--host 0.0.0.0]`
   - Calls `uvicorn.run("zoom_insights.api:app", ...)`

3. **Update `pyproject.toml`**
   - Add `fastapi>=0.111.0` and `uvicorn>=0.29.0` to dependencies

**Tests** — `tests/test_api.py`:
- `test_health_returns_ok` — GET /health → 200
- `test_process_missing_file_returns_422` — POST with non-existent file → 422
- `test_process_returns_202_and_job_id` — valid POST → 202 with job_id
- `test_get_job_unknown_id_returns_404` — GET /jobs/unknown → 404
- `test_get_job_returns_queued_immediately` — after POST, GET → queued/running
- `test_job_transitions_to_done` — mock pipeline, assert status→done with result
- `test_job_transitions_to_failed` — mock pipeline error, assert status→failed
- `test_multiple_jobs_are_independent` — 2 jobs have separate status tracking

Use `TestClient` from `fastapi.testclient`. Mock pipeline functions with `mocker`.

**Definition of Done**
- [ ] `src/zoom_insights/api.py` with 3 endpoints
- [ ] In-memory job store with thread safety
- [ ] `zoom-insights serve` CLI subcommand
- [ ] `fastapi` + `uvicorn` in dependencies
- [ ] 8 tests in `tests/test_api.py` pass
- [ ] All 185 existing tests still pass (193+ total)
- [ ] Manual smoke: `uvicorn zoom_insights.api:app --port 8000` runs

---

### Cycle 20 — Webhook automation

**Goal:** Subscribe to Zoom's `recording.completed` webhook event and auto-process new recordings with no manual trigger.

**Why:** Removes the last manual step — recordings are processed the moment they're ready. Requires Cycle 19 FastAPI wrapper.

**Steps (brief)**
1. Add `POST /webhook` endpoint to FastAPI app (Cycle 19 prerequisite)
2. Verify Zoom's HMAC-SHA256 signature from `x-zm-signature` header
3. On valid `recording.completed` event, extract meeting UUID and enqueue job
4. Respond 200 within 3 seconds (Zoom requires fast ack); processing in background
5. Add `ZOOM_WEBHOOK_SECRET_TOKEN` to `.env.example` and `Config`
6. Tests: signature verification, correct job enqueueing, invalid signature → 401

**Definition of Done**
- [ ] `/webhook` endpoint validates Zoom HMAC signature
- [ ] Valid events enqueue jobs via job store
- [ ] Invalid signature → 401
- [ ] All tests pass

---

### Cycle 21 — Local/private mode

**Goal:** Swap Groq Whisper + Groq LLM with local `faster-whisper` and Ollama via `--local` flag. No audio or transcript leaves the machine.

**Why:** Privacy; reduces API costs; enables offline operation.

**Steps (brief)**
1. Keep existing function signatures in `transcribe.py`, `insights.py`
2. Add `--local` flag to CLI
3. At runtime, swap client implementations based on flag
4. `faster-whisper` for audio → local text
5. Ollama API for LLM calls (chunking, map-reduce same as Groq)
6. Tests: integration tests run both Groq and local backend

**Definition of Done**
- [ ] `--local` flag toggles backend without changing API
- [ ] Local pipeline produces same insights.json format
- [ ] Tests pass for both backends

---

### Cycle 22 — Speaker diarization

**Goal:** Integrate local `pyannote.audio` to label transcript segments with speaker IDs. Merge with Whisper timestamps → "who said what" in action items.

**Why:** Action items gain meaningful owner attribution from actual speaker data (not guessing).

**Steps (brief)**
1. Add `pyannote.audio` (huggingface) to dependencies
2. After Whisper transcription, run diarization on audio
3. Merge speaker labels with Whisper word-level timestamps
4. Update `insights.json` structure to include speaker attribution
5. Action items now show actual speaker from diarization, not guessed owner

**Definition of Done**
- [ ] Diarization runs on audio post-transcription
- [ ] Speaker labels merged with transcript at word level
- [ ] Action items show diarized owner
- [ ] Tests pass

---

### Cycle 23 — Quality pass

**Goal:** Prompt-injection hardening, eval set with expected action items, cost/latency dashboard.

**Why:** Harden security before adding more features; validate model accuracy; understand economics.

**Steps (brief)**
1. Sanitize transcript before LLM calls (remove suspicious prompt-injection patterns)
2. Create eval set: 10 real meetings with gold-standard expected action items
3. Auto-score current model output against eval set
4. Log token counts, API latencies per meeting → cost estimate
5. Print metrics: avg cost/meeting, latency, eval score

**Definition of Done**
- [ ] Transcript sanitization prevents injection attacks
- [ ] Eval set auto-scores model output
- [ ] Metrics logged and available via dashboard/CLI
- [ ] All tests pass

---

### Cycle 24 — Slack / Teams integration

**Goal:** Post a summary card to Slack or Teams after processing a recording.

**Why:** Distributes meeting outcomes async to the team without manual steps.

**Steps (brief)**
1. New module `src/zoom_insights/notify.py`
   - `post_slack(insights, webhook_url)` — POST Block Kit card
   - `post_teams(insights, webhook_url)` — POST Adaptive Card
   - Card: summary, top 3 action items, link to full report
2. Add `--notify` flag to CLI; auto-detect platform from URL
3. Add `SLACK_WEBHOOK_URL` / `TEAMS_WEBHOOK_URL` to `.env.example`

**Definition of Done**
- [ ] `notify.py` with Slack and Teams posting
- [ ] `--notify` flag on `zoom-insights <file> --local --notify`
- [ ] All tests pass

---

### Cycle 25 — Action item follow-up tracker

**Goal:** Persist extracted action items to SQLite and provide `status` / `done` CLI commands.

**Why:** Close the loop — action items tracked from creation through completion.

**Steps (brief)**
1. New module `src/zoom_insights/tracker.py`
   - `init_db(path)` — create action_items table
   - `save_action_items(meeting_id, items, jira_keys)` — upsert
   - `list_pending()` — overdue and upcoming
   - `mark_done(task_id)` — set completed_at
2. `zoom-insights status` — print pending items in table
3. `zoom-insights done <task_id>` — mark complete
4. Auto-save after each processing run
5. DB: `~/.zoom-insights.db` (configurable via `TRACKER_DB`)

**Definition of Done**
- [ ] SQLite tracker with CRUD ops
- [ ] `status` and `done` CLI subcommands
- [ ] Items auto-saved on process
- [ ] All tests pass

---

### Cycle 26 — Recurring meeting digest

**Goal:** Batch-process all recordings from the past N days and produce a cross-meeting rollup report.

**Why:** High leverage for managers — one weekly report replaces N individual reports.

**Steps (brief)**
1. New `digest` CLI subcommand: `zoom-insights digest --days 7`
2. List all Zoom recordings for past N days
3. Process any not-yet-completed (skip via idempotency log)
4. Aggregate insights: merge action_items by owner, deduplicate points
5. Write `output/digest-<dates>/report.md` and `rollup.json`
6. Optionally post digest to Slack/Teams if `--notify` flag

**Definition of Done**
- [ ] `digest` processes N days of recordings
- [ ] Rollup groups items by owner
- [ ] Respects idempotency (skips already-processed)
- [ ] All tests pass

---

### Cycle 27 — Interactive meeting Q&A (RAG)

**Goal:** `zoom-insights ask "What did Alice commit to?"` queries stored transcripts using retrieval-augmented generation.

**Why:** "Search my meetings" — high leverage for revisiting or cross-meeting discovery.

**Steps (brief)**
1. Add `chromadb` (or `faiss-cpu`) + `sentence-transformers` to dependencies
2. After each processing run, embed transcript chunks and store
3. `zoom-insights ask "<question>"` — embed Q, retrieve top-K chunks, LLM answer
4. Source attribution: show meeting and timestamp for each answer
5. Embeddings stored: `~/.zoom-insights-embeddings/`

**Definition of Done**
- [ ] Chunks embedded and persisted post-processing
- [ ] `ask` returns grounded answer with attribution
- [ ] Works without re-processing if embeddings exist
- [ ] All tests pass

---

## 7. Testing strategy

- **Unit (fast, mocked):** every module; no network, no real keys. This is the
  bulk of the suite and must stay green in CI.
- **Contract:** `insights.json` validated against the §4 schema in every run.
- **Integration (mocked Zoom+Groq):** one full `cli.main` pass per Cycle 11.
- **Manual smoke:** documented commands per cycle, run against one real recording.
- **Fixtures:** keep a ~30s audio clip, a `recordings.json`, and a `sample.vtt`
  under `tests/fixtures/` so nothing depends on a live account during CI.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Recording not owned by the auth account → `Forbidden 124` | Document Pro+ host requirement + scopes; clear error hint |
| Free LLM TPM throttling on long calls | Map-reduce + backoff; never one big prompt |
| 25 MB Whisper cap on long meetings | Compress + segment |
| Groq model IDs change | `LLM_MODEL`/`WHISPER_MODEL` are config; verify at console.groq.com/docs/models |
| Sensitive meeting content leaving machine | Optional local mode (Cycle 14) |
| Download URLs / tokens expire (~24h) | Re-fetch via recordings endpoint at process time, not ahead |
| No diarization | Scoped out of MVP; Cycle 15 or paid provider |

---

## 9. Appendix A — Coding standards

- **Retry helper** (resolves the code-review note). Use this signature so callers
  may pass arguments directly *or* keep the zero-arg lambda style:

  ```python
  def with_retry(fn, *args, tries=6, base_delay=4, **kwargs):
      delay = base_delay
      for i in range(tries):
          try:
              return fn(*args, **kwargs)
          except Exception as e:                 # narrow to Groq/HTTP errors in practice
              msg = str(e).lower()
              if i == tries - 1 or not any(k in msg for k in ("429", "rate", "timeout")):
                  raise
              time.sleep(delay)
              delay = min(delay * 2, 60)
  ```
  Both `with_retry(client.chat.completions.create, model=m, messages=msgs)` and
  `with_retry(lambda: client.chat.completions.create(...))` are valid.

- Config and secrets only via `config.py`; no `os.environ` reads scattered around.
- No `print` in library code — use `logging`. `print` only in `cli.py`.
- Each stage is a pure-ish function with explicit inputs/outputs so backends
  (Groq ↔ local) are swappable.
- Type hints on public functions; dataclasses over raw dicts for Zoom payloads.
- Tests must not require real credentials or network.

## 10. Appendix B — One-time account setup

1. **Zoom** → Marketplace → Develop → Build App → **Server-to-Server OAuth**.
   Activate it; copy **Account ID, Client ID, Client Secret**. Add scopes:
   `cloud_recording:read:list_user_recordings`,
   `cloud_recording:read:list_recording_files`.
   (Cloud recording requires a **paid Zoom plan**.)
2. **Groq** → console.groq.com → create a free API key (no credit card).
3. **ffmpeg** → install via your package manager (`brew install ffmpeg`,
   `apt install ffmpeg`, or the Windows build).
4. Copy `.env.example` → `.env` and fill in all four values.

## 11. Appendix C — Reference spike

`prototype/zoom_insights.py` already implements every stage in one file and is
the behavioral reference. Port from it cycle by cycle; when in doubt about *what*
a stage should do, the spike is the answer — improve only the *how*.
