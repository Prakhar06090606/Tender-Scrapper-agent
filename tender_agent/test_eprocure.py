# test_eprocure_full.py — Full pipeline test for eProcure
# Tests: Homepage → Gemini extraction → DB save → Google Sheet write
# Keyword filter is BYPASSED so we always have data to test with.
# Usage: py test_eprocure_full.py

import asyncio, sys
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from scraper.eprocure import EPROCURE_HOME, _extract_homepage_tenders, _scrape_detail_page
from scraper.base import create_stealth_context, safe_goto
from database import init_db, is_duplicate, save_tender, AsyncSessionLocal
from excel.writer import write_tenders_to_sheet

MAX_TEST_TENDERS = 3   # Only 3 — saves Gemini quota


async def run_full_test():
    print("=" * 60)
    print("eProcure FULL PIPELINE TEST")
    print(f"Sending up to {MAX_TEST_TENDERS} tenders → Gemini → DB → Sheet")
    print("Keyword filter BYPASSED for this test")
    print("=" * 60)

    await init_db()
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await create_stealth_context(browser)
        page = await context.new_page()

        try:
            print(f"\n📍 STEP 1 — Loading homepage...")
            ok = await safe_goto(page, EPROCURE_HOME, timeout=60000)
            if not ok:
                print("❌ Could not load homepage")
                return
            await asyncio.sleep(4)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")
            rows = _extract_homepage_tenders(soup)
            print(f"📋 Found {len(rows)} rows — using first {MAX_TEST_TENDERS}")

            print(f"\n📍 STEP 2 — Gemini extraction (filter bypassed)...")
            async with AsyncSessionLocal() as session:
                for i, row in enumerate(rows[:MAX_TEST_TENDERS], 1):
                    print(f"\n  [{i}/{MAX_TEST_TENDERS}] {row['title'][:60]}")

                    # Duplicate check
                    if await is_duplicate(session, row["link"]):
                        print(f"  ⏭️  Already in DB — skipping")
                        continue

                    result = await _scrape_detail_page(page, row)
                    if result:
                        results.append(result)
                        print(f"  ✅ [{result.get('relevance','?')}] {result.get('tender_title','?')[:50]}")
                        print(f"     bid_strategy: {result.get('bid_strategy','?')}")
                    else:
                        print(f"  ⚠️  Extraction failed")

                    await asyncio.sleep(3)

        except Exception as e:
            import traceback
            print(f"⚠️  Error: {e}")
            traceback.print_exc()
        finally:
            await browser.close()

    if not results:
        print("\n❌ No results — all extractions failed or were duplicates")
        return

    # ── Save to DB ─────────────────────────────────────────────────────────────
    print(f"\n📍 STEP 3 — Saving {len(results)} to database...")
    saved_tenders = []
    async with AsyncSessionLocal() as session:
        for r in results:
            try:
                tender = await save_tender(session, r)
                saved_tenders.append(tender)
                print(f"  ✅ DB saved (id={tender.id}): {tender.tender_title[:50]}")
            except Exception as e:
                print(f"  ⚠️  DB save failed: {e}")

    # ── Write to Sheet ─────────────────────────────────────────────────────────
    print(f"\n📍 STEP 4 — Writing {len(saved_tenders)} to Google Sheet...")
    stats = write_tenders_to_sheet(saved_tenders)

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Extracted  : {len(results)}")
    print(f"  DB saved   : {len(saved_tenders)}")
    print(f"  Sheet rows : {stats['written']}")
    print(f"  Errors     : {stats['errors']}")
    print(f"  Tabs used  : {stats['by_sheet']}")
    if stats['written'] > 0:
        print(f"\n✅ Check your Google Sheet — new rows should be visible now")
        print(f"   They'll be 'Not relevant' — correct, filter was bypassed for test")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(run_full_test())