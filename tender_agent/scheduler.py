# scheduler.py — optimized parallel pipeline

import asyncio
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import SCRAPE_INTERVAL_HOURS
from database import AsyncSessionLocal, save_tender, is_duplicate, get_pending_tenders, mark_written
from excel.writer import write_tenders_to_excel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_pipeline_running = False


async def run_scraping_pipeline():
    """
    Optimized pipeline — all sites scraped IN PARALLEL using asyncio.gather().

    BEFORE: UNGM → GeM → eProcure → DefProc → Google (sequential, 15-30 min)
    AFTER:  All 5 sites at the same time (total = slowest single site, 3-8 min)

    KEY CONCEPT — asyncio.gather():
    gather() runs multiple async functions simultaneously on the same event loop.
    Since all scrapers spend most of their time WAITING (for pages to load,
    for Gemini to respond), they can wait in parallel — one doesn't block another.
    """
    log.info("=" * 60)
    log.info(f"🚀 Pipeline starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    # ── Run ALL scrapers simultaneously ───────────────────────────────────────
    log.info("🔍 Launching all scrapers in parallel...")
    t0 = datetime.now()

    results = await asyncio.gather(
        _run_ungm(),
        _run_gem(),
        _run_eprocure(),
        _run_defproc(),
        _run_google(),
        return_exceptions=True,   # Don't let one failure kill the others
    )

    elapsed = (datetime.now() - t0).seconds
    log.info(f"⏱️  All scrapers finished in {elapsed}s")

    # Flatten results, skip exceptions and None values
    all_scraped = []
    site_names = ["UNGM", "GeM", "eProcure", "DefProc", "Google"]
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log.error(f"   ❌ {site_names[i]} failed: {result}")
        elif isinstance(result, list):
            valid = [r for r in result if r is not None]
            log.info(f"   ✅ {site_names[i]}: {len(valid)} tenders")
            all_scraped.extend(valid)

    log.info(f"\n📦 Total valid: {len(all_scraped)}")

    if not all_scraped:
        log.info("Nothing new this run.")
        return

    # ── Deduplicate + save to DB ───────────────────────────────────────────────
    new_count = 0
    async with AsyncSessionLocal() as session:
        for tender_data in all_scraped:
            try:
                link = tender_data.get("link", "")
                if await is_duplicate(session, link):
                    continue
                saved = await save_tender(session, tender_data)
                new_count += 1
                rel = tender_data.get("relevance", "?")
                log.info(f"   💾 [{saved.category}][{rel}] {saved.tender_title[:50]}")
            except Exception as e:
                log.error(f"   ❌ DB error: {e}")

    log.info(f"\n✅ Saved {new_count} new tenders")

    # ── Write to Google Sheet ─────────────────────────────────────────────────
    if new_count > 0:
        async with AsyncSessionLocal() as session:
            pending = await get_pending_tenders(session)
            if pending:
                stats = write_tenders_to_excel(pending)
                for tender in pending:
                    try:
                        await mark_written(session, tender.id)
                    except Exception as e:
                        log.error(f"   ❌ mark_written error: {e}")
                log.info(f"   Sheet: {stats}")

    log.info(f"🏁 Done at {datetime.now().strftime('%H:%M:%S')}")
    log.info("=" * 60)


async def _run_ungm():
    from scraper.ungm import scrape_ungm
    return await scrape_ungm()

async def _run_gem():
    from scraper.gem import scrape_gem
    return await scrape_gem()

async def _run_eprocure():
    from scraper.eprocure import scrape_eprocure
    return await scrape_eprocure()

async def _run_defproc():
    from scraper.eprocure import scrape_defproc
    return await scrape_defproc()

async def _run_google():
    from scraper.google_search import scrape_google
    return await scrape_google()


def _run_pipeline_in_thread():
    """Wrapper that runs the async pipeline in a fresh event loop in a thread."""
    global _pipeline_running
    if _pipeline_running:
        return
    _pipeline_running = True
    try:
        import asyncio
        asyncio.run(run_scraping_pipeline())
    finally:
        _pipeline_running = False


def start_scheduler():
    scheduler.add_job(
        func=_run_pipeline_in_thread,
        trigger=IntervalTrigger(hours=SCRAPE_INTERVAL_HOURS),
        id="scraping_pipeline",
        name="Tender Scraping Pipeline",
        replace_existing=True,
        next_run_time=datetime.now() + timedelta(minutes=2),
        max_instances=1,          # CRITICAL: never run two pipelines at the same time
        coalesce=True,            # If missed runs pile up, only run once not multiple times
    )
    scheduler.start()
    log.info(f"⏰ Scheduler started — first run in 2 min, then every {SCRAPE_INTERVAL_HOURS}h")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        log.info("⏰ Scheduler stopped")


_pipeline_running = False

async def run_once():
    """
    Run pipeline in a ThreadPoolExecutor so it doesn't block FastAPI.
    
    WHY THIS MATTERS:
    FastAPI and the scraper share the same asyncio event loop.
    When Playwright opens browsers and waits for pages, it occupies the loop.
    FastAPI can't respond to /health checks during that time → dashboard shows offline.
    
    Running in an executor moves the blocking work to a separate thread,
    freeing the event loop to handle HTTP requests normally.
    """
    global _pipeline_running
    if _pipeline_running:
        log.info("⚠️  Pipeline already running — skipping manual trigger")
        return
    log.info("🔄 Manual run triggered")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: asyncio.run(run_scraping_pipeline()))
