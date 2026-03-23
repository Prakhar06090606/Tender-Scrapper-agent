# scraper/google_search.py
# ─────────────────────────────────────────────────────────────────────────────
# PURPOSE: Find tenders via Google that aren't on the main portals.
# Some tenders are posted on individual agency websites, PDF documents,
# or smaller procurement portals — Google indexes all of them.
#
# HOW THIS WORKS:
# We use the free Google Custom Search JSON API.
# - Google gives 100 free searches per day
# - We run targeted queries like "UNDP India tender AI consulting 2024"
# - For each search result, we visit the page and try to extract tender info
#
# ALTERNATIVE — DuckDuckGo scraping:
# If you don't want to set up Google API, we also support scraping
# DuckDuckGo's HTML results page (no API key needed, but less reliable).
#
# SETUP (one-time, 5 minutes):
# 1. Go to: https://developers.google.com/custom-search/v1/introduction
# 2. Create a Custom Search Engine at: https://cse.google.com
# 3. Set it to search the entire web
# 4. Get your API key and Search Engine ID
# 5. Add to .env:
#    GOOGLE_API_KEY=your_key
#    GOOGLE_CSE_ID=your_cse_id
#
# KEY CONCEPT — Why not just scrape Google directly?
# Google actively blocks scrapers with CAPTCHAs. The official API
# is free (100/day), reliable, and gives clean JSON results.
# ─────────────────────────────────────────────────────────────────────────────

import os
import asyncio
import httpx
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from ai.extractor import extract_tender_fields
from config import GOOGLE_SEARCH_QUERIES

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "")
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

MAX_RESULTS_PER_QUERY = 5   # Google allows max 10 per request
MAX_TENDERS = 10


async def scrape_google() -> list[dict]:
    """
    Runs all configured search queries and extracts tenders from results.
    Returns list of tender dicts.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        print("⚠️  Google API key or CSE ID not set — using DuckDuckGo fallback")
        return await _scrape_duckduckgo_fallback()

    all_urls = []

    # ── Run each search query via Google Custom Search API ─────────────────
    # httpx is an async HTTP client — like requests but works with async/await
    async with httpx.AsyncClient() as client:
        for query in GOOGLE_SEARCH_QUERIES:
            try:
                print(f"🔍 Google search: '{query}'")

                # Make API request
                # The Google API returns a JSON object with "items" array
                # Each item has "link" (URL), "title", and "snippet"
                response = await client.get(
                    GOOGLE_SEARCH_URL,
                    params={
                        "key": GOOGLE_API_KEY,
                        "cx": GOOGLE_CSE_ID,
                        "q": query,
                        "num": MAX_RESULTS_PER_QUERY,
                        "dateRestrict": "m3",   # Only last 3 months
                        "lr": "lang_en",         # English results
                    },
                    timeout=10,
                )

                data = response.json()

                # Extract URLs from search results
                items = data.get("items", [])
                for item in items:
                    url = item.get("link", "")
                    # Skip PDFs, images, and known non-tender sites
                    if url and not _should_skip(url):
                        all_urls.append(url)

                # Respect Google's rate limit — don't hammer the API
                await asyncio.sleep(1)

            except Exception as e:
                print(f"⚠️  Google search failed for '{query}': {e}")
                continue

    # Deduplicate URLs
    unique_urls = list(dict.fromkeys(all_urls))
    print(f"🔗 Google: {len(unique_urls)} unique URLs to check")

    # ── Visit each URL and extract tender information ──────────────────────
    tenders = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--disable-background-networking',
                '--disable-default-apps',
                '--no-first-run',
            ]
        )
        page = await browser.new_page()

        for url in unique_urls[:MAX_TENDERS]:
            try:
                tender_data = await _extract_from_url(page, url)
                if tender_data:
                    tenders.append(tender_data)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"⚠️  Failed to extract from {url}: {e}")
                continue

        await browser.close()

    print(f"✅ Google search: found {len(tenders)} tenders")
    return tenders


def _should_skip(url: str) -> bool:
    """
    Skip URLs that are unlikely to contain extractable tender information.

    WHY: Visiting PDFs, LinkedIn pages, or news sites wastes time and
    can crash the scraper. We filter them out before visiting.
    """
    skip_domains = ["linkedin.com", "facebook.com", "twitter.com", "youtube.com", "instagram.com"]
    skip_extensions = [".pdf", ".doc", ".docx", ".xls", ".zip", ".jpg", ".png"]

    url_lower = url.lower()
    return (
        any(domain in url_lower for domain in skip_domains) or
        any(url_lower.endswith(ext) for ext in skip_extensions)
    )


async def _extract_from_url(page, url: str) -> dict | None:
    """
    Visit a Google search result URL and try to extract tender information.
    Many results will NOT be actual tenders — the AI will recognize this
    and we filter out non-tenders based on what the AI returns.
    """
    print(f"  → Checking: {url}")

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(1)

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        raw_text = soup.get_text(separator="\n", strip=True)

        # Quick relevance check before sending to AI (saves API calls)
        # If the page has no tender-related words, skip it
        text_lower = raw_text.lower()
        tender_words = ["tender", "rfp", "request for proposal", "bid", "procurement", "deadline", "submission"]
        if not any(word in text_lower for word in tender_words):
            print(f"    ⏭️  Not a tender page, skipping")
            return None

        return await extract_tender_fields(raw_text, url, "Google")

    except Exception as e:
        print(f"    ⚠️  Error visiting {url}: {e}")
        return None


async def _scrape_duckduckgo_fallback() -> list[dict]:
    """
    Fallback: scrape DuckDuckGo HTML search results (no API key needed).

    HOW IT WORKS:
    DuckDuckGo has a plain HTML version at https://html.duckduckgo.com
    We scrape the search results page (it's not JSON, just HTML links).

    RELIABILITY: Less reliable than Google API. DuckDuckGo may occasionally
    return CAPTCHA or block repeated requests. We add delays to reduce this.
    """
    all_urls = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--disable-background-networking',
                '--disable-default-apps',
                '--no-first-run',
            ]
        )
        page = await browser.new_page()

        for query in GOOGLE_SEARCH_QUERIES[:3]:  # Only run 3 queries to be safe
            try:
                search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
                print(f"🦆 DuckDuckGo: '{query}'")

                await page.goto(search_url, wait_until="networkidle", timeout=15000)
                await asyncio.sleep(2)

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                # DuckDuckGo results have links with class "result__a"
                for a in soup.find_all("a", class_="result__a"):
                    href = a.get("href", "")
                    if href and not _should_skip(href):
                        all_urls.append(href)

                await asyncio.sleep(3)  # Longer delay for DuckDuckGo

            except Exception as e:
                print(f"⚠️  DuckDuckGo search failed: {e}")
                continue

        await browser.close()

    # Now visit the found URLs
    tenders = []
    if all_urls:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--disable-background-networking',
                '--disable-default-apps',
                '--no-first-run',
            ]
        )
            page = await browser.new_page()

            for url in list(dict.fromkeys(all_urls))[:MAX_TENDERS]:
                tender_data = await _extract_from_url(page, url)
                if tender_data:
                    tenders.append(tender_data)
                await asyncio.sleep(2)

            await browser.close()

    return tenders
