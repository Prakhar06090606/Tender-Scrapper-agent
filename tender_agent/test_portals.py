# test_portals.py — Live portal tester for GeM and eProcure
# Usage:
#   py test_portals.py gem          — test GeM bidplus listing page
#   py test_portals.py eprocure     — test eProcure listing + detail links
#   py test_portals.py both         — test both

import asyncio, sys
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from scraper.base import create_stealth_context, safe_goto

GEM_LIST     = "https://bidplus.gem.gov.in/all-bids"
EPROCURE_URL = "https://eprocure.gov.in/eprocure/app"


async def test_gem():
    print("\n" + "="*60)
    print("TESTING: GeM — bidplus.gem.gov.in/all-bids")
    print("="*60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await create_stealth_context(browser)
        page = await context.new_page()

        print("🌐 Loading GeM listing page...")
        ok = await safe_goto(page, GEM_LIST, timeout=60000)
        if not ok:
            print("❌ Could not load GeM page")
            await browser.close()
            return

        await asyncio.sleep(4)
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(separator="\n", strip=True)

        print(f"📄 Page loaded: {len(page_text)} chars")
        print(f"📄 Page title: {soup.title.string if soup.title else 'No title'}")

        # Look for bid links
        all_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(p in href for p in ["showbidDetail", "bidDetail", "BidDetail", "all-bids/"]):
                full = href if href.startswith("http") else f"https://bidplus.gem.gov.in{href}"
                if full not in all_links and full != GEM_LIST:
                    all_links.append(full)

        print(f"\n📋 Bid detail links found: {len(all_links)}")
        for l in all_links[:5]:
            print(f"   {l}")

        # Print first 1500 chars of page text
        print(f"\n--- First 1500 chars of page text ---")
        print(page_text[:1500])

        # Check for CAPTCHA / block
        lower = page_text.lower()
        if "captcha" in lower:
            print("\n⚠️  CAPTCHA DETECTED — bot protection active")
        if "403" in page_text or "forbidden" in lower:
            print("\n⚠️  403 FORBIDDEN — IP blocked")
        if "javascript" in lower and len(page_text) < 500:
            print("\n⚠️  JS-only page — need to wait longer or use different approach")

        await browser.close()


async def test_eprocure():
    print("\n" + "="*60)
    print("TESTING: eProcure — eprocure.gov.in/eprocure/app")
    print("="*60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await create_stealth_context(browser)
        page = await context.new_page()

        print("🌐 Loading eProcure home...")
        ok = await safe_goto(page, EPROCURE_URL, timeout=60000)
        if not ok:
            print("❌ Could not load eProcure page")
            await browser.close()
            return

        await asyncio.sleep(4)
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(separator="\n", strip=True)

        print(f"📄 Page loaded: {len(page_text)} chars")
        print(f"📄 Page title: {soup.title.string if soup.title else 'No title'}")
        print(f"📄 Current URL: {page.url}")

        # Find all links and categorise
        nav_links = []
        tender_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if "tender" in text.lower() or "bid" in text.lower() or "NIT" in text:
                nav_links.append((text[:50], href[:80]))
            if any(p in href for p in ["tenderDetail", "TenderDetail", "NIT", "noticeDetail"]):
                tender_links.append(href[:80])

        print(f"\n📋 Navigation links mentioning tender/bid: {len(nav_links)}")
        for text, href in nav_links[:10]:
            print(f"   [{text}] → {href}")

        print(f"\n🔗 Direct tender detail links: {len(tender_links)}")
        for l in tender_links[:5]:
            print(f"   {l}")

        # Check the active tenders link specifically
        print(f"\n--- Active Tenders link search ---")
        target_phrases = ["active tender", "latest tender", "all tender", "search tender"]
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if any(ph in text for ph in target_phrases):
                print(f"   FOUND: [{a.get_text(strip=True)}] → {a['href']}")

        print(f"\n--- First 1500 chars of page text ---")
        print(page_text[:1500])

        await browser.close()


async def main():
    target = sys.argv[1].lower() if len(sys.argv) > 1 else "both"
    if target in ("gem", "both"):
        await test_gem()
    if target in ("eprocure", "both"):
        await test_eprocure()


if __name__ == "__main__":
    import os, sys
    # Windows asyncio fix
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
