# main.py
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS:
# This is the entry point of the entire application.
# It creates the FastAPI web server and wires together:
#   - Database initialization
#   - Scheduler startup (background agent)
#   - API endpoints (so you can control the agent and query results)
#
# KEY CONCEPT — FastAPI:
# FastAPI is a Python web framework. When you run this file, it starts
# an HTTP server on your computer (localhost:8000). You can then:
#   - Open a browser to http://localhost:8000/docs to see all API endpoints
#   - Call endpoints from your dashboard frontend
#   - Trigger manual runs
#
# KEY CONCEPT — lifespan:
# FastAPI's "lifespan" is a special function that runs:
#   - ONCE when the app STARTS (setup: init DB, start scheduler)
#   - ONCE when the app STOPS (cleanup: stop scheduler)
# This is the modern replacement for @app.on_event("startup").
#
# API ENDPOINTS in this file:
#   GET  /               → Health check (is the server running?)
#   GET  /tenders        → List all tenders from DB (with filters)
#   GET  /tenders/{id}   → Get one tender's full details
#   POST /run-now        → Manually trigger a scraping run
#   GET  /stats          → How many tenders per sheet, last run time
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import sys

# ── Windows fix ───────────────────────────────────────────────────────────────
# Python 3.13 on Windows defaults to a broken event loop for subprocesses.
# Playwright launches Chromium as a subprocess, so it needs ProactorEventLoop.
# This MUST be set before anything else imports asyncio internals.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from typing import Optional

from database import init_db, get_session
from models import Tender
from scheduler import start_scheduler, stop_scheduler, run_once


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup and shutdown.
    'yield' separates the startup code (above) from shutdown code (below).
    """
    # ── STARTUP ──────────────────────────────────────────────────────────────
    print("🚀 Tender Agent starting up...")

    # Create database tables if they don't exist
    await init_db()

    # Start the background scraping scheduler
    start_scheduler()

    print("✅ Tender Agent is running!")
    print("📖 API docs: http://localhost:8000/docs")

    yield  # App runs here — everything above runs on startup, below on shutdown

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    print("🛑 Tender Agent shutting down...")
    stop_scheduler()


# ── App creation ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Tender Agent API",
    description="Automated tender discovery and Excel reporting system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware — allows your Next.js dashboard (running on port 3000)
# to make API calls to this server (running on port 8000).
# Without this, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API Endpoints ─────────────────────────────────────────────────────────────

@app.get("/")
async def health_check():
    """
    Simple health check. Open http://localhost:8000/ in your browser.
    If you see this response, the server is running.
    """
    return {
        "status": "running",
        "message": "Tender Agent is active",
        "docs": "http://localhost:8000/docs",
    }


@app.get("/tenders")
async def list_tenders(
    session: AsyncSession = Depends(get_session),
    category: Optional[str] = Query(None, description="Filter by sheet: Consulting, IT, etc."),
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected"),
    source: Optional[str] = Query(None, description="Filter by site: UNGM, GeM, etc."),
    limit: int = Query(50, description="Max results to return"),
    offset: int = Query(0, description="Skip this many results (for pagination)"),
):
    """
    Get all tenders from the database with optional filters.

    WHY FILTERS:
    You might want to see only "Consulting" tenders, or only tenders
    from "UNGM", or only "pending" ones not yet reviewed.

    HOW PAGINATION WORKS:
    offset=0, limit=50 → first 50 results
    offset=50, limit=50 → next 50 results (page 2)
    """
    query = select(Tender)

    # Apply filters if provided
    if category:
        query = query.where(Tender.category == category)
    if status:
        query = query.where(Tender.status == status)
    if source:
        query = query.where(Tender.source_site == source)

    # Sort by newest first, then paginate
    query = query.order_by(Tender.created_at.desc()).offset(offset).limit(limit)

    result = await session.exec(query)
    tenders = result.all()

    return {
        "total": len(tenders),
        "offset": offset,
        "limit": limit,
        "tenders": [_tender_to_dict(t) for t in tenders],
    }


@app.get("/tenders/{tender_id}")
async def get_tender(
    tender_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get a single tender's full details by its ID."""
    result = await session.exec(select(Tender).where(Tender.id == tender_id))
    tender = result.first()

    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")

    return _tender_to_dict(tender)


@app.post("/run-now")
async def trigger_manual_run():
    """
    Manually trigger a scraping run immediately.
    The run happens in the background — this endpoint returns instantly.

    USE CASE: You just added a new site to watch, or you want fresh data
    without waiting for the scheduled run.
    """
    import asyncio
    # Run in background so the API response returns immediately
    asyncio.create_task(run_once())

    return {
        "message": "Scraping pipeline triggered",
        "note": "Check server logs for progress. Results appear in Excel when complete.",
    }


@app.get("/stats")
async def get_stats(session: AsyncSession = Depends(get_session)):
    """
    Summary statistics — useful for the dashboard overview.
    Returns counts by category, source site, and status.
    """
    from sqlmodel import func

    # Total tenders
    total_result = await session.exec(select(func.count(Tender.id)))
    total = total_result.one()

    # By category
    by_category = {}
    for cat in ["Consulting", "IT", "Medical Oxygen", "Training and Skill"]:
        result = await session.exec(
            select(func.count(Tender.id)).where(Tender.category == cat)
        )
        by_category[cat] = result.one()

    # By status
    by_status = {}
    for status in ["pending", "approved", "rejected"]:
        result = await session.exec(
            select(func.count(Tender.id)).where(Tender.status == status)
        )
        by_status[status] = result.one()

    # Written to Excel
    written_result = await session.exec(
        select(func.count(Tender.id)).where(Tender.written_to_excel == True)
    )
    written_count = written_result.one()

    return {
        "total_tenders": total,
        "by_category": by_category,
        "by_status": by_status,
        "written_to_excel": written_count,
        "pending_excel_write": total - written_count,
    }


@app.patch("/tenders/{tender_id}/status")
async def update_tender_status(
    tender_id: int,
    status: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Update a tender's status (approve / reject / reconsider).
    Even though full tender submission is a future phase, tracking
    your decisions in the DB is useful now.

    Valid values: "pending", "approved", "rejected", "reconsidering"
    """
    valid_statuses = ["pending", "approved", "rejected", "reconsidering"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    result = await session.exec(select(Tender).where(Tender.id == tender_id))
    tender = result.first()

    if not tender:
        raise HTTPException(status_code=404, detail=f"Tender {tender_id} not found")

    tender.status = status
    session.add(tender)
    await session.commit()

    return {"message": f"Tender {tender_id} status updated to '{status}'"}


# ── Helper ────────────────────────────────────────────────────────────────────

def _tender_to_dict(t: Tender) -> dict:
    """Convert Tender model to JSON-serializable dict for API responses."""
    return {
        "id": t.id,
        "category": t.category,
        "source_site": t.source_site,
        "agency": t.agency,
        "tender_title": t.tender_title,
        "link": t.link,
        "area": t.area,
        "submission_deadline_date": t.submission_deadline_date,
        "submission_deadline_time": t.submission_deadline_time,
        "date_scouted_on": t.date_scouted_on,
        "company_eligibility": t.company_eligibility,
        "personnel_eligibility": t.personnel_eligibility,
        "language_requirement": t.language_requirement,
        "financial_eligibility": t.financial_eligibility,
        "currency_for_proposal": t.currency_for_proposal,
        "pre_bid_meeting_date": t.pre_bid_meeting_date,
        "location": t.location,
        "travel_required": t.travel_required,
        "tax_inclusive_exclusive": t.tax_inclusive_exclusive,
        "jv_consortium_allowed": t.jv_consortium_allowed,
        "brief_specification": t.brief_specification,
        "status": t.status,
        "written_to_excel": t.written_to_excel,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


# ── Run the server ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    # uvicorn is the ASGI server that runs FastAPI
    # reload=True means: if you edit any Python file, the server restarts automatically
    # This is for DEVELOPMENT only — remove reload=True in production
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
