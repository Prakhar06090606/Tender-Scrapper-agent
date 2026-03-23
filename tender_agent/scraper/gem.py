# scraper/gem.py — GeM (Government e-Marketplace India)
# Site behavior: Server-rendered bid cards, each with a detail page.
# Bid details include ministry, dates, items, EMD. Login needed for docs.
# Anti-bot: Moderate. Approach: stealth + filter by relevance keywords.

import asyncio
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
from ai.extractor import extract_tender_fields
from utils.pdf_extractor import get_tender_document_text
from scraper.base import create_stealth_context, human_delay, safe_goto

GEM_BASE = "https://bidplus.gem.gov.in"
GEM_LIST = "https://bidplus.gem.gov.in/all-bids"
MAX_TENDERS = 12

# Keywords to pre-filter GeM bids before sending to Gemini
# GeM has thousands of bids for furniture, stationery etc — we skip those
RELEVANT_KEYWORDS = [
    "artificial intelligence", "machine learning", "AI", "software",
    "consulting", "training", "skill", "education", "platform",
    "digital", "data", "analytics", "technology", "IT service",
    "assessment", "evaluation", "capacity", "e-learning", "LMS",
    "HR", "recruitment", "workforce", "employability", "career",
    "research", "study", "survey", "advisory",
]


async def scrape_gem() -> list[dict]:
    tenders = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await create_stealth_context(browser)
        page = await context.new_page()

        try:
            print("🌐 Opening GeM listing...")
            ok = await safe_goto(page, GEM_LIST, timeout=60000)
            if not ok:
                return tenders

            await asyncio.sleep(4)
            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # GeM uses bid cards — find all detail page links
            bid_links = _extract_gem_links(soup)
            print(f"📋 GeM: found {len(bid_links)} bids, filtering for relevance...")

            # Filter by relevance before visiting each page (saves time)
            page_text_lower = soup.get_text().lower()
            relevant_links = _filter_relevant(bid_links, soup, page_text_lower)
            print(f"🎯 GeM: {len(relevant_links)} potentially relevant bids")

            for url in relevant_links[:MAX_TENDERS]:
                try:
                    result = await _scrape_detail(page, url)
                    if result:
                        tenders.append(result)
                    await human_delay(2, 4)
                except Exception as e:
                    print(f"  ⚠️  GeM detail error: {e}")

        except Exception as e:
            print(f"⚠️  GeM failed: {e}")
        finally:
            await browser.close()

    print(f"✅ GeM: {len(tenders)} tenders scraped")
    return tenders


def _extract_gem_links(soup: BeautifulSoup) -> list[str]:
    """
    GeM bid detail pages follow the pattern /showbidDetail/...
    We also try /bidDetail/ and /BidDetail/ variants.
    """
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(p in href for p in ["showbidDetail", "bidDetail", "BidDetail", "all-bids/"]):
            full = href if href.startswith("http") else f"{GEM_BASE}{href}"
            if full not in links and full != GEM_LIST:
                links.append(full)
    return links


def _filter_relevant(links: list, soup: BeautifulSoup, full_text: str) -> list:
    """
    Check bid card text against relevance keywords before visiting each page.
    If we can't determine relevance from listing, include it anyway.
    """
    if not links:
        return []

    # Check if page contains ANY relevant keywords at all
    has_any = any(kw.lower() in full_text for kw in RELEVANT_KEYWORDS)
    if not has_any:
        # Return a sample anyway — let Gemini decide
        return links[:5]

    relevant = []
    for link in links:
        # Try to find the anchor's card context
        a_tag = soup.find("a", href=lambda h: h and (link.replace(GEM_BASE, "") in h or link in h))
        if a_tag:
            parent = a_tag
            for _ in range(4):  # Walk up 4 levels to get card text
                if parent.parent:
                    parent = parent.parent
            card_text = parent.get_text().lower()
            if any(kw.lower() in card_text for kw in RELEVANT_KEYWORDS):
                relevant.append(link)
        else:
            relevant.append(link)  # Include if we can't determine

    return relevant if relevant else links[:5]


async def _scrape_detail(page, url: str) -> dict | None:
    print(f"  → GeM: {url}")
    ok = await safe_goto(page, url, timeout=40000)
    if not ok:
        return None

    await asyncio.sleep(2)
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")
    page_text = soup.get_text(separator="\n", strip=True)

    pdf_text = ""
    try:
        pdf_text = await get_tender_document_text(html, url)
    except Exception:
        pass

    combined = f"=== PAGE ===\n{page_text}\n\n=== DOCUMENTS ===\n{pdf_text}" if pdf_text else page_text
    return await extract_tender_fields(combined, url, "GeM")
