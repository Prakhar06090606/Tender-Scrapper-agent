# test_scrape.py — Test single URL end to end with full document access
import asyncio, sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from ai.extractor import extract_tender_fields
from scraper.ungm import (
    _extract_links_tab, _get_all_documents, HEADERS
)

async def test_url(url: str):
    print(f"\n{'='*60}")
    print(f"Testing: {url}")
    print(f"{'='*60}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--no-first-run"]
        )
        page = await browser.new_page(user_agent=HEADERS["User-Agent"])

        print("🌐 Loading page...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await asyncio.sleep(3)
        except Exception as e:
            print(f"❌ Page load failed: {e}")
            await browser.close()
            return

        # Get page text
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(separator="\n", strip=True)
        print(f"📄 Page text: {len(page_text)} chars")

        # Click Links tab
        print("\n🔗 Clicking Links tab...")
        links_from_tab = []
        try:
            await page.click("a:has-text('Links')")
            await asyncio.sleep(1.5)
            links_from_tab = await _extract_links_tab(page)
            html = await page.content()  # Refresh after tab click
            if links_from_tab:
                print(f"   Found {len(links_from_tab)} links:")
                for l in links_from_tab:
                    print(f"   • [{l['description']}] {l['url'][:70]}")
            else:
                print("   No links found in Links tab")
        except Exception as e:
            print(f"   ⚠️  Links tab: {e}")

        await browser.close()

    # Try all document sources
    notice_id = url.split("/Notice/")[-1].split("?")[0]
    print(f"\n📦 Fetching documents (notice {notice_id})...")
    doc_text = await _get_all_documents(
        notice_id=notice_id,
        links_from_tab=links_from_tab,
        html=html,
        base_url=url
    )

    if doc_text:
        print(f"\n📑 Document text: {len(doc_text)} chars")
        combined = f"=== PAGE ===\n{page_text}\n\n=== DOCUMENTS ===\n{doc_text}"
    else:
        print("\nℹ️  No documents — page text only")
        combined = page_text

    print(f"\n🤖 Sending {len(combined)} chars to Gemini...")
    result = await extract_tender_fields(combined, url, "Test")

    if result is None:
        print("\n⏭️  SKIPPED — deadline has passed")
        return

    print(f"\n{'='*60}")
    print("EXTRACTED FIELDS:")
    print(f"{'='*60}")
    skip = ("raw_content", "source_site", "category")
    for key, value in result.items():
        if key not in skip:
            val = str(value)
            display = val[:120] + "..." if len(val) > 120 else val
            icon = "⬜" if val == "Info not fetched" else ("🔴" if key == "relevance" and "Not" in val else ("🟢" if key == "relevance" else "✅"))
            print(f"  {icon} {key:<35} {display}")

    filled = sum(1 for k, v in result.items() if k not in skip and v != "Info not fetched")
    total  = len([k for k in result if k not in skip])
    print(f"\n  Category:      {result['category']}")
    print(f"  Fields filled: {filled}/{total}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.ungm.org/Public/Notice/292926"
    asyncio.run(test_url(url))
