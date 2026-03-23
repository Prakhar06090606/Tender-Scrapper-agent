# scraper/eprocure.py — eProcure NIC Government Portal
#
# ARCHITECTURE (Option B+C — no CAPTCHA):
#
#   The eProcure portal has TWO CAPTCHA walls:
#     Wall 1 — Advanced Search results page (CAPTCHA to see any results)
#     Wall 2 — ZIP document download (CAPTCHA to get files)
#
#   BOTH walls are bypassed by this strategy:
#     ✅ Use the HOMEPAGE — shows 5-10 latest tenders with direct links, NO CAPTCHA
#     ✅ Click each tender's DirectLink → detail page, NO CAPTCHA
#     ✅ Extract all NIT text from detail page HTML
#     ⏭️  Skip ZIP download for now — store download URL in important_links
#
#   PHASE 2 (when 2captcha is added):
#     → Add _download_zip_with_captcha() function
#     → Call it after keyword filter passes
#     → Pass ZIP content to doc_extractor → Gemini
#     → Nothing else changes
#
# WHAT THE DETAIL PAGE CONTAINS (no login needed):
#   - Tender title, reference number, organisation
#   - Tender type, form of contract
#   - Closing date + time, opening date
#   - Brief description / NIT summary
#   - Contact officer details (sometimes)
#   - Download link (needs CAPTCHA to actually download)

import asyncio
import re
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from bs4 import BeautifulSoup
from ai.extractor import extract_tender_fields
from scraper.base import create_stealth_context, human_delay, safe_goto

EPROCURE_HOME = "https://eprocure.gov.in/eprocure/app"
BASE_URL       = "https://eprocure.gov.in"
MAX_TENDERS    = 10   # Max from homepage listing

# Keywords to pre-filter tenders before sending to Gemini
# eProcure has thousands of civil/construction/supply tenders
# We only want consulting, IT, training, research, advisory
RELEVANT_KEYWORDS = [
    # Consulting / advisory
    "consult", "advisory", "study", "survey", "assessment", "evaluation",
    "research", "analysis", "report",
    # IT / digital — NOTE: "IT" alone is intentionally removed
    # "IT HARDWARE" is supply, not our work. Use full phrases only.
    "software", "platform", "portal", "digital", "information technology",
    "IT service", "IT solution", "system development", "application development",
    "mobile app", "web app", "analytics", "dashboard",
    "artificial intelligence", "machine learning", "automation",
    # Training / education
    "training", "capacity building", "workshop", "skill", "education",
    "curriculum", "e-learning", "LMS", "learning management",
    "faculty development", "ToT", "trainer",
    # HR / workforce
    "human resource", "recruitment", "workforce", "employability", "placement",
    # Project management / development
    "project management", "programme management", "PMU", "PMC",
    "monitoring", "M&E", "baseline",
]

# Hard skip — these words in title = definitely not EduBild/Kamtech work
SKIP_KEYWORDS = [
    # Civil / construction
    "construction", "civil work", "renovation", "repair", "maintenance",
    "retaining wall", "drain", "road", "bridge", "fencing",
    "signage", "signages", "playground", "playing field",
    # Supply of physical goods
    "supply of", "procurement of", "purchase of", "rate contract for",
    "furniture", "stationery", "printing",
    "hardware item", "hardware supply", "it hardware",
    # Vehicles / transport
    "vehicle", "car rental", "taxi", "hiring of vehicle",
    "empanelment of car", "empanelment of vehicle",
    "ambulance", "bus", "truck",
    # Facilities
    "housekeeping", "security", "fire fighting", "horticulture",
    "plumbing", "flooring", "painting", "carpentry", "electrical work",
    "canteen", "catering",
    # Medical / pharma
    "medical", "drug", "medicine", "hospital", "reagent", "consumable",
    "surgical", "clinical", "pharmaceutical",
]


async def scrape_eprocure() -> list[dict]:
    """
    Main entry point called by scheduler.
    Returns list of tender dicts extracted by Gemini.
    """
    tenders = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = await create_stealth_context(browser)
        page = await context.new_page()

        try:
            # ── Step 1: Load homepage — shows latest tenders, no CAPTCHA ──────
            print("🌐 eProcure: Loading homepage...")
            ok = await safe_goto(page, EPROCURE_HOME, timeout=60000)
            if not ok:
                print("❌ eProcure: Could not reach homepage")
                return tenders

            await asyncio.sleep(4)  # Let JS render the tender table

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            # ── Step 2: Extract tender rows from homepage table ───────────────
            tender_rows = _extract_homepage_tenders(soup)
            print(f"📋 eProcure: {len(tender_rows)} tenders on homepage")

            if not tender_rows:
                print("⚠️  eProcure: No tenders found on homepage — site may have changed layout")
                return tenders

            # ── Step 3: Keyword pre-filter ────────────────────────────────────
            relevant_rows = _filter_relevant_rows(tender_rows)
            print(f"🎯 eProcure: {len(relevant_rows)} relevant after keyword filter")

            # ── Step 4: Scrape each relevant tender's detail page ─────────────
            for row in relevant_rows[:MAX_TENDERS]:
                try:
                    result = await _scrape_detail_page(page, row)
                    if result:
                        tenders.append(result)
                    await human_delay(2, 4)
                except Exception as e:
                    print(f"  ⚠️  eProcure detail error: {e}")

        except Exception as e:
            print(f"⚠️  eProcure scraper failed: {e}")
        finally:
            await browser.close()

    print(f"✅ eProcure: {len(tenders)} tenders extracted")
    return tenders


def _extract_homepage_tenders(soup: BeautifulSoup) -> list[dict]:
    """
    The eProcure homepage shows two tables:
      Table 1 — "Active Tenders" (uses $DirectLink in URL)
      Table 2 — "Corrigendums"   (uses $DirectLink_0 in URL)

    We only want Table 1 — active tenders.
    Corrigendums are amendments on existing tenders, not new opportunities.

    Fix 1: Skip rows where title is the table header itself
            ("Tender TitleReference No..." — the <th> row leaks into <td>)
    Fix 2: Only accept $DirectLink URLs, reject $DirectLink_0 (corrigendums)
    Fix 3: Strip leading "N. " row numbers from titles (homepage adds them)
    """
    rows = []
    all_tables = soup.find_all("table")

    for table in all_tables:
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue

            row_text = tr.get_text(separator=" ", strip=True)

            # Must have a date pattern to be a tender row
            if not re.search(r"\d{2}-\w{3}-\d{4}", row_text):
                continue

            # Find the link
            link_tag = tr.find("a", href=True)
            if not link_tag:
                continue

            href = link_tag["href"]

            # Fix 2: Only $DirectLink (active tenders), NOT $DirectLink_0 (corrigendums)
            # $DirectLink_0 links are for corrigendum rows — amendments, not new tenders
            if "%24DirectLink_0" in href or "DirectLink_0" in href:
                continue
            if not ("%24DirectLink" in href or "DirectLink" in href or
                    "tenderDetail" in href.lower()):
                continue

            full_link = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Extract title — longest cell text
            title = ""
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                if len(cell_text) > len(title) and len(cell_text) > 10:
                    title = cell_text

            # Fix 1: Skip if title is actually the table header row leaking through
            title_lower = title.lower()
            if any(title_lower.startswith(h) for h in [
                "tender title", "corrigendum title", "s.no", "reference no"
            ]):
                continue

            # Fix 3: Strip leading row number "1. ", "2. ", "10. " from title
            title = re.sub(r"^\d+\.\s+", "", title).strip()

            # Extract dates
            dates = re.findall(
                r"\d{2}-\w{3}-\d{4}(?:\s+\d{2}:\d{2}\s*(?:AM|PM))?", row_text
            )
            closing_date = dates[0] if dates else ""
            opening_date = dates[1] if len(dates) > 1 else ""

            # Extract reference number
            ref_match = re.search(
                r"[A-Z][A-Z0-9/_\-\.]{5,40}(?:/\d{4}-\d{2,4})?(?:/\d+)?",
                row_text
            )
            ref_no = ref_match.group(0) if ref_match else ""

            if title and full_link:
                rows.append({
                    "title": title[:200],
                    "ref_no": ref_no,
                    "closing_date": closing_date,
                    "opening_date": opening_date,
                    "link": full_link,
                })

    # Deduplicate by link
    seen = set()
    unique_rows = []
    for row in rows:
        if row["link"] not in seen:
            seen.add(row["link"])
            unique_rows.append(row)

    return unique_rows


def _filter_relevant_rows(rows: list[dict]) -> list[dict]:
    """
    Two-pass filter:
      Pass 1 — Hard skip: if title contains construction/supply/civil → skip immediately
      Pass 2 — Soft keep: if title contains consulting/IT/training → keep

    If neither pass matches, include the row anyway — let Gemini decide.
    Unknown tenders are cheap (one Gemini call) and we don't want false negatives.
    """
    relevant = []

    for row in rows:
        title_lower = row["title"].lower()

        # Hard skip
        if any(kw in title_lower for kw in SKIP_KEYWORDS):
            print(f"  ⏭️  Skip: {row['title'][:60]}")
            continue

        # Soft keep
        if any(kw in title_lower for kw in RELEVANT_KEYWORDS):
            print(f"  ✅ Keep: {row['title'][:60]}")
            relevant.append(row)
        else:
            # Unknown — include with flag
            print(f"  ❓ Unknown: {row['title'][:60]} — including for Gemini check")
            relevant.append(row)

    return relevant


async def _scrape_detail_page(page, row: dict) -> dict | None:
    """
    Load the tender detail page — no CAPTCHA required.

    The detail page has:
    - Full tender title, organisation, ministry
    - NIT reference number
    - Tender type, form of contract
    - Closing date/time, opening date
    - Brief NIT description
    - Contact details (officer name, email, phone)
    - Download link (CAPTCHA-gated — stored in important_links for manual use)

    We send all this text to Gemini for field extraction.
    """
    print(f"  → eProcure: {row['title'][:55]}...")

    ok = await safe_goto(page, row["link"], timeout=40000)
    if not ok:
        return None

    await asyncio.sleep(2)
    html = await page.content()
    soup = BeautifulSoup(html, "lxml")

    # Check for session expiry — DirectLinks are session-bound
    page_text = soup.get_text(separator="\n", strip=True)
    if any(phrase in page_text.lower() for phrase in [
        "session expired", "session has expired", "please login",
        "login to view", "invalid session"
    ]):
        print(f"    ⚠️  Session expired for this link — skipping")
        return None

    # ── Build context: pre-fill what we already know from the listing row ─────
    # This ensures Gemini always gets at minimum the basic fields even if
    # the detail page is thin
    context_header = f"""
SOURCE: eProcure (Government of India)
TENDER TITLE: {row['title']}
REFERENCE NUMBER: {row['ref_no']}
CLOSING DATE: {row['closing_date']}
OPENING DATE: {row['opening_date']}
DETAIL PAGE URL: {row['link']}

--- FULL PAGE CONTENT ---
"""

    # ── Extract download link (NIT/BOQ ZIP) for important_links ─────────────
    # The actual download link on detail pages uses specific patterns:
    #   /eprocure/app?component=...&page=...&service=download...
    #   or contains "tenderDocuments", "downloadNIT", "downloadTenderDocument"
    #
    # We MUST avoid the nav menu "Downloads" link which goes to:
    #   /eprocure/app?page=StandardBiddingDocuments&service=page
    # That's a generic page, not a tender-specific download.
    zip_link = ""
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True).lower()
        # Skip the generic navigation Downloads link
        if "StandardBiddingDocuments" in href:
            continue
        # Look for tender-specific download indicators
        is_download = any(w in href.lower() for w in [
            "download", "nit", "tender_doc", "tenderdoc",
            "getdocument", "fetchdocument"
        ]) or any(w in text for w in [
            "download tender", "download nit", "download document",
            "tender document", "nit document"
        ])
        if is_download:
            zip_link = href if href.startswith("http") else f"{BASE_URL}{href}"
            break

    # ── Combine everything for Gemini ─────────────────────────────────────────
    combined = context_header + page_text

    if zip_link:
        combined += f"\n\nDOWNLOAD LINK (requires CAPTCHA): {zip_link}"

    # Trim to reasonable size
    combined = combined[:15000]

    result = await extract_tender_fields(combined, row["link"], "eProcure")

    # ── If important_links is empty, populate with download URL ───────────────
    if result and zip_link and not result.get("important_links"):
        result["important_links"] = f"Document ZIP (manual download): {zip_link}"

    return result


# ── PHASE 2 PLACEHOLDER ───────────────────────────────────────────────────────
# When 2captcha integration is added, implement this function:
#
# async def _download_zip_with_captcha(page, download_url: str) -> bytes | None:
#     """
#     1. Load download_url in browser
#     2. Screenshot the CAPTCHA image
#     3. Send to 2captcha API: requests.post("http://2captcha.com/in.php", ...)
#     4. Poll for result: requests.get("http://2captcha.com/res.php?action=get&id=...")
#     5. Type solved CAPTCHA into input field
#     6. Click download button
#     7. Intercept network response → return ZIP bytes
#     8. Pass ZIP bytes to pdf_extractor.extract_from_zip()
#     """
#     pass