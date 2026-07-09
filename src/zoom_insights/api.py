"""FastAPI REST wrapper for the Zoom Insights pipeline."""

import hashlib
import hmac
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from zoom_insights.config import load_config, Config
from zoom_insights.logging_config import setup_logging
from zoom_insights.zoom_client import get_access_token
from groq import Groq

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Zoom Insights API", version="0.1.0")

# Global job store with thread safety
jobs: Dict[str, Dict[str, Any]] = {}
jobs_lock = threading.Lock()

# Global executor for bounded concurrency
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _get_executor(config: Config) -> ThreadPoolExecutor:
    """Get or create a bounded ThreadPoolExecutor.

    Args:
        config: Application configuration

    Returns:
        ThreadPoolExecutor with max_workers set to config.max_concurrent_jobs
    """
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs)
    return _executor


def _verify_zoom_signature(request_body: bytes, signature: str, secret: str) -> bool:
    """Verify Zoom webhook signature using HMAC-SHA256.

    Args:
        request_body: Raw request body bytes
        signature: The x-zm-signature header value (hex string)
        secret: The webhook secret token

    Returns:
        True if signature is valid, False otherwise
    """
    computed = hmac.new(secret.encode(), request_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@dataclass
class JobStatus:
    """Status of a background job."""

    id: str
    status: str  # "queued", "processing", "done", "failed"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict with ISO datetime string."""
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d


class ProcessRequest(BaseModel):
    """Request body for POST /process."""

    file_path: str
    jira: bool = False


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint.

    Returns:
        {"status": "ok"}
    """
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request) -> Dict[str, str]:
    """Zoom webhook endpoint for recording.completed events.

    Validates the Zoom signature and enqueues a background job to process the recording.

    Args:
        request: The FastAPI request object

    Returns:
        {"status": "ok"} on success (HTTP 200)

    Raises:
        HTTPException 401: if signature is invalid or missing
    """
    # Get the raw body
    body = await request.body()

    # Get the signature header (case-insensitive)
    signature_header = request.headers.get("x-zm-signature", "")
    if not signature_header:
        logger.warning("Webhook request missing x-zm-signature header")
        raise HTTPException(status_code=401, detail="Missing x-zm-signature header")

    # Extract the hex part (format is v0=<hex>)
    if not signature_header.startswith("v0="):
        logger.warning("Webhook signature has invalid format")
        raise HTTPException(status_code=401, detail="Invalid signature format")
    signature = signature_header[3:]  # Strip "v0=" prefix

    # Load config to get the webhook secret
    config = load_config()
    if not config.zoom_webhook_secret_token:
        logger.error("ZOOM_WEBHOOK_SECRET_TOKEN not configured")
        raise HTTPException(status_code=401, detail="Webhook not configured")

    # Verify signature
    if not _verify_zoom_signature(body, signature, config.zoom_webhook_secret_token):
        logger.warning("Webhook request failed signature verification")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse the webhook payload
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Extract meeting UUID from the webhook payload
    # Zoom sends: { "event": "recording.completed", "data": { "object": { "id": "...", ... } } }
    try:
        meeting_uuid = payload.get("data", {}).get("object", {}).get("id")
        if not meeting_uuid:
            logger.warning("Webhook payload missing meeting UUID")
            raise HTTPException(status_code=400, detail="Missing meeting UUID in payload")
    except (KeyError, TypeError) as e:
        logger.error(f"Failed to extract meeting UUID from webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload structure")

    # Generate job ID and create job record
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
            "webhook": True,
            "meeting_uuid": meeting_uuid,
        }

    # Submit to bounded executor
    executor = _get_executor(config)
    executor.submit(_run_pipeline, job_id, None, False, meeting_uuid)

    logger.info(f"Webhook job {job_id} queued for meeting: {meeting_uuid}")

    # Return 200 immediately (Zoom expects response within 3 seconds)
    return {"status": "ok"}


@app.post("/process", status_code=202)
async def process(request: ProcessRequest) -> Dict[str, str]:
    """Submit a local file for processing.

    Args:
        request: ProcessRequest with file_path and optional jira flag

    Returns:
        {"job_id": "<uuid>"}

    Raises:
        HTTPException 422: if file_path does not exist
    """
    # Validate file exists
    file_path = Path(request.file_path)
    if not file_path.exists():
        raise HTTPException(
            status_code=422,
            detail=f"File not found: {request.file_path}",
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Create job record
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
        }

    # Load config to get executor
    config = load_config()

    # Submit to bounded executor
    executor = _get_executor(config)
    executor.submit(_run_pipeline, job_id, request.file_path, request.jira)

    logger.info(f"Job {job_id} queued for file: {request.file_path}")
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> Dict[str, Any]:
    """Get job status.

    Args:
        job_id: UUID of the job

    Returns:
        JobStatus dict with id, status, result, error, created_at

    Raises:
        HTTPException 404: if job_id not found
    """
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        job_data = jobs[job_id].copy()

    return job_data


def _run_pipeline(
    job_id: str,
    file_path: str = None,
    jira: bool = False,
    meeting_uuid: str = None,
) -> None:
    """Run the pipeline in background.

    Updates the job status in the jobs dict as it progresses.
    Either processes a local file or fetches and processes a Zoom cloud recording.

    Args:
        job_id: UUID of the job
        file_path: Path to the file to process (for local files)
        jira: Whether to export to Jira after processing
        meeting_uuid: UUID of a Zoom meeting to process (for cloud recordings)
    """
    try:
        # Update status to processing (from queued)
        with jobs_lock:
            jobs[job_id]["status"] = "processing"

        # Load config and create Groq client
        config = load_config()
        groq_client = Groq(api_key=config.groq_api_key)

        # Create backends
        from zoom_insights.backends import GroqTranscriptionBackend, GroqLLMBackend

        transcription_backend = GroqTranscriptionBackend(groq_client)
        llm_backend = GroqLLMBackend(groq_client)

        # Ensure work directory
        from zoom_insights.zoom_client import ensure_work_dir

        work_dir = ensure_work_dir("work")

        # Determine whether to process local file or cloud meeting
        if meeting_uuid:
            # Process cloud meeting from Zoom
            logger.info(f"Job {job_id}: starting pipeline for meeting {meeting_uuid}")

            from zoom_insights.cli import _process_meeting

            # Get OAuth token for Zoom API calls
            token = get_access_token(config)

            _process_meeting(
                meeting_uuid,
                token,
                groq_client,
                config,
                work_dir=work_dir,
                force=False,
                jira=jira,
            )
        else:
            # Process local file
            logger.info(f"Job {job_id}: starting pipeline for {file_path}")

            from zoom_insights.cli import _process_local_file

            _process_local_file(
                file_path,
                groq_client,
                work_dir=work_dir,
                force=False,
                jira=jira,
                config=config,
            )

        # Read the insights.json that was just created
        from zoom_insights.report import sanitize_topic

        if meeting_uuid:
            # For cloud meetings, use the UUID as the fallback title
            # _process_meeting handles determining the actual meeting title
            title = meeting_uuid
        else:
            # For local files, use the filename
            title = Path(file_path).stem

        report_dir = Path("output") / sanitize_topic(title)
        insights_path = report_dir / "insights.json"

        result = {}
        if insights_path.exists():
            with open(insights_path, "r", encoding="utf-8") as f:
                result = json.load(f)

        # Update job with success
        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["result"] = result

        logger.info(f"Job {job_id}: completed successfully")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id}: failed with error: {error_msg}", exc_info=True)

        # Update job with failure
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = error_msg
