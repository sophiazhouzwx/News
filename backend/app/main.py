import logging
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import digests, podcasts, media, push, livestreams, feedback, predictions, speeches
from .services.scheduler import daily_digest_job, is_running, get_last_run_report, cancel_running

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stderr,
    force=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Daily AI News", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(digests.router, prefix="/api/digests", tags=["digests"])
app.include_router(podcasts.router, prefix="/api/podcasts", tags=["podcasts"])
app.include_router(media.router, prefix="/api/media", tags=["media"])
app.include_router(push.router, prefix="/api/push", tags=["push"])
app.include_router(livestreams.router, prefix="/api/livestreams", tags=["livestreams"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["feedback"])
app.include_router(predictions.router, prefix="/api/predictions", tags=["predictions"])
app.include_router(speeches.router, prefix="/api/speeches", tags=["speeches"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/admin/run-digest")
async def run_digest_now(force: bool = False):
    """Trigger the digest job. Pass ?force=true to regenerate even if today's exists."""
    if is_running():
        return {"status": "already_running", "message": "Digest job is already in progress"}

    thread = threading.Thread(target=daily_digest_job, args=(force,), daemon=True)
    thread.start()
    return {"status": "started", "message": "Digest job triggered"}


@app.post("/api/admin/cancel-digest")
async def cancel_digest():
    """Force-reset the running flag if it gets stuck."""
    if not is_running():
        return {"status": "not_running", "message": "No digest job is running"}
    cancel_running()
    return {"status": "cancelled", "message": "Running flag reset. Background threads may still be finishing."}


@app.get("/api/admin/digest-status")
async def digest_status():
    """Check whether the digest job is currently running, and return the last run report."""
    report = get_last_run_report()
    return {
        "running": is_running(),
        "last_run": report,
    }
