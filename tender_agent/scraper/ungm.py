# scraper/ungm.py
# UNGM scraper with full document access strategy:
# 1. Click "Links" tab (JS-rendered) to get all document links
# 2. Try DownloadAllDocuments ZIP (UNGM's own bundle)
# 3. Try Docs-Public SharePoint — enumerate + download all files
# 4. Try Direct Quantum Negotiation link
# 5. Fall back to page text only if all above fail
# 6. Mark login-gated content as "More info after login"

import asyncio
import zipfile
import io
import httpx
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from ai.extractor import extract_tender_fields

UNGM_BASE = "https://www.ungm.org"
UNGM_LIST = "https://www.ungm.org/Public/Notice"
MAX_TENDERS = 15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Login-gate detection ───────────────────────────────────────────────────────
LOGIN_SIGNALS = [
    "please log in", "login required", "sign in to view",
    "you must be logged", "register to access", "sharepoint/login",
    "authentication required", "access denied",
]

def _is_login_gate(text: str) -> bool:
    t = text.lower()
    return any(s in t for s in LOGIN_SIGNALS)


async def scrape_ungm() -> list[dict]:
    """Scrape UNGM tender listings with full document access."""
    tenders = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-gpu", "--disable-extensions",
                "--disable-background-networking", "--no-first-run",
            ]
        )
        context = await browser.new_context(user_agent=HEADERS["User-Agent"])
        page = await context.new_page()

        try:
            print(f"🌐 Opening UNGM listing page...")
            await page.goto(UNGM_LIST, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(5)

            html = await page.content()
            soup = BeautifulSoup(html, "lxml")

            tender_links = []
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if "/Public/Notice/" in href and href not in tender_links:
                    full_url = href if href.startswith("http") else f"{UNGM_BASE}{href}"
                    if full_url != UNGM_LIST and "/Notice/" in full_url:
                        # Filter out non-numeric notice IDs (listing pages)
                        notice_id = full_url.split("/Notice/")[-1].split("?")[0]
                        if notice_id.isdigit():
                            tender_links.append(full_url)

            print(f"📋 UNGM: found {len(tender_links)} tenders")

            for url in tender_links[:MAX_TENDERS]:
                try:
                    tender_data = await _scrape_ungm_detail(page, url)
                    if tender_data:
                        tenders.append(tender_data)
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"⚠️  Error scraping {url}: {e}")
                    continue

        except PlaywrightTimeout:
            print("⚠️  UNGM page timed out")
        except Exception as e:
            print(f"⚠️  UNGM scraping failed: {e}")
        finally:
            await browser.close()

    print(f"✅ UNGM: {len(tenders)} tenders scraped")
    return tenders


async def _scrape_ungm_detail(page, url: str) -> dict | None:
    """
    Scrape one UNGM tender detail page.

    DOCUMENT ACCESS STRATEGY (in priority order):
    1. Click the "Links" tab to get JS-rendered document links
    2. Try DownloadAllDocuments ZIP endpoint
    3. Try Docs-Public SharePoint folder (enumerate all files)
    4. Try Direct Quantum Negotiation link
    5. Fall back to page text only
    """
    print(f"  → Scraping: {url}")

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=40000)
        await asyncio.sleep(2)

        # ── Step 1: Click "Links" tab to load JS-rendered document links ─────
        links_from_tab = []
        try:
            # UNGM renders tabs as <ul class="nav-tabs"><li><a href="#tab-links">Links</a>
            # Try multiple selectors in order of specificity
            clicked = False
            selectors = [
                "a[href*='links']:not([href^='http'])",  # anchor with #links href
                "a[href='#tab-links']",
                "a[href='#links']",
                "li a[data-toggle='tab']",  # any tab with data-toggle
            ]
            for sel in selectors:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        text = await el.inner_text()
                        if "link" in text.lower():
                            await el.click()
                            clicked = True
                            break
                except Exception:
                    continue

            # Fallback: use JS to find and click any tab containing "Links"
            if not clicked:
                clicked = await page.evaluate("""
                    () => {
                        const anchors = Array.from(document.querySelectorAll('a'));
                        const linksTab = anchors.find(a =>
                            a.textContent.trim() === 'Links' &&
                            (a.getAttribute('data-toggle') === 'tab' ||
                             a.getAttribute('href') || '').startsWith('#')
                        );
                        if (linksTab) { linksTab.click(); return true; }
                        return false;
                    }
                """)

            if clicked:
                await asyncio.sleep(1.5)
                links_from_tab = await _extract_links_tab(page)
                if links_from_tab:
                    print(f"    🔗 Links tab: {len(links_from_tab)} links found")
                else:
                    print(f"    ℹ️  Links tab clicked but no links found")
            else:
                print(f"    ℹ️  No Links tab found on this page")
        except Exception as e:
            print(f"    ⚠️  Links tab error: {e}")

        # Get full page HTML + text
        html = await page.content()
        soup = BeautifulSoup(html, "lxml")
        page_text = soup.get_text(separator="\n", strip=True)

        # Extract notice ID for DownloadAll endpoint
        notice_id = url.split("/Notice/")[-1].split("?")[0]

        # ── Step 2–4: Try all document sources ───────────────────────────────
        doc_text = await _get_all_documents(
            notice_id=notice_id,
            links_from_tab=links_from_tab,
            html=html,
            base_url=url
        )

        # ── Combine and send to Gemini ────────────────────────────────────────
        if doc_text:
            combined = (
                f"=== TENDER PAGE CONTENT ===\n{page_text}\n\n"
                f"=== TENDER DOCUMENTS ===\n{doc_text}"
            )
            print(f"    📚 Combined: {len(combined)} chars (page + documents)")
        else:
            combined = page_text

        return await extract_tender_fields(combined, url, "UNGM")

    except Exception as e:
        print(f"    ⚠️  Failed to scrape {url}: {e}")
        return None


async def _extract_links_tab(page) -> list[dict]:
    """
    Extract all links from the UNGM Links tab after it's been clicked.
    Returns list of {url, description} dicts.
    """
    try:
        # Wait for the tab content to load
        await page.wait_for_selector("table", timeout=3000)
    except Exception:
        pass

    html = await page.content()
    soup = BeautifulSoup(html, "lxml")
    links = []

    # UNGM Links tab renders a table with URL | Description | Button columns
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows[1:]:  # Skip header
            cells = row.find_all("td")
            if len(cells) >= 2:
                # First cell is URL text or contains an <a>
                url_cell = cells[0].get_text(strip=True)
                desc = cells[1].get_text(strip=True) if len(cells) > 1 else ""

                # Also check for actual <a> tags
                a_tag = cells[0].find("a", href=True)
                if a_tag:
                    url_cell = a_tag["href"]

                if url_cell.startswith("http"):
                    links.append({"url": url_cell, "description": desc})

    return links


async def _get_all_documents(
    notice_id: str,
    links_from_tab: list[dict],
    html: str,
    base_url: str
) -> str:
    """
    Try all document sources in priority order.
    Returns combined extracted text from all accessible documents.
    """
    all_text = []

    # ── Priority 1: DownloadAllDocuments ZIP ──────────────────────────────────
    if notice_id.isdigit():
        zip_url = f"{UNGM_BASE}/Public/Notice/DownloadAllDocuments?noticeId={notice_id}"
        print(f"    📦 Trying DownloadAll ZIP: {zip_url}")
        zip_text = await _download_and_extract_zip(zip_url)
        if zip_text:
            all_text.append(f"=== UNGM Document Bundle ===\n{zip_text}")
            print(f"    ✅ ZIP extracted: {len(zip_text)} chars")
            return "\n\n".join(all_text)  # ZIP has everything, no need to try others

    # ── Priority 2: Docs-Public SharePoint from Links tab ────────────────────
    sharepoint_links = [
        l for l in links_from_tab
        if "sharepoint.com/sites/Docs-Public" in l["url"]
        or "sharepoint.com/sites/docs-public" in l["url"].lower()
    ]

    for sp_link in sharepoint_links:
        print(f"    📁 Trying SharePoint: {sp_link['url'][:70]}")
        sp_text = await _access_sharepoint_folder(sp_link["url"])
        if sp_text:
            all_text.append(f"=== SharePoint Documents ({sp_link['description']}) ===\n{sp_text}")

    # ── Priority 3: Direct Quantum Negotiation link ───────────────────────────
    quantum_links = [
        l for l in links_from_tab
        if "view_negotiation" in l["url"] or "quantum" in l["url"].lower()
        or "nego_id" in l["url"]
    ]

    for q_link in quantum_links:
        print(f"    🔗 Trying Quantum: {q_link['url'][:70]}")
        q_text = await _fetch_quantum_page(q_link["url"])
        if q_text:
            all_text.append(f"=== Quantum Negotiation ({q_link['description']}) ===\n{q_text}")

    # ── Priority 4: Any direct PDF/DOCX links from the tab ───────────────────
    from utils.pdf_extractor import extract_text_from_pdf_url
    doc_links = [
        l for l in links_from_tab
        if any(ext in l["url"].lower() for ext in [".pdf", ".docx", ".doc", ".xlsx"])
    ]

    for doc_link in doc_links:
        print(f"    📄 Trying direct doc: {doc_link['url'][-60:]}")
        text = await extract_text_from_pdf_url(doc_link["url"])
        if text:
            all_text.append(f"=== Document: {doc_link['description']} ===\n{text}")

    # ── Priority 5: Check HTML for any login-gated links (mark them) ─────────
    if links_from_tab:
        login_gated = [
            l for l in links_from_tab
            if any(s in l["url"].lower() for s in [
                "sharepoint/login", "oraclecloud.com", "register-supplier"
            ])
        ]
        if login_gated and not all_text:
            gated_desc = ", ".join(l["description"] for l in login_gated)
            all_text.append(
                f"NOTE: The following documents require UNGM login to access: {gated_desc}. "
                f"Fields like company_eligibility, financial_eligibility may be found in these documents."
            )

    return "\n\n".join(all_text) if all_text else ""


async def _download_and_extract_zip(url: str) -> str:
    """
    Download UNGM's DownloadAllDocuments ZIP and extract text from all files inside.
    ZIP typically contains: TOR.pdf, Financial_Template.xlsx, Annexes.pdf, etc.
    """
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, follow_redirects=True, timeout=30
        ) as client:
            response = await client.get(url)

            if response.status_code != 200:
                print(f"    ⚠️  ZIP download failed: HTTP {response.status_code}")
                return ""

            content_type = response.headers.get("content-type", "")
            data = response.content

            # Handle different file types returned by DownloadAllDocuments
            if data[:2] == b"PK":
                pass  # It's a ZIP — fall through to ZIP extraction below
            elif data[:4] == b"%PDF":
                from utils.pdf_extractor import _extract_pdf_text
                text = _extract_pdf_text(data)
                if text:
                    print(f"    📄 DownloadAll returned PDF: {len(text)} chars")
                    return text
                return ""
            elif b"word/document.xml" in data[:100] or "wordprocessingml" in content_type:
                from utils.pdf_extractor import _extract_docx_text
                text = _extract_docx_text(data)
                if text:
                    print(f"    📄 DownloadAll returned DOCX: {len(text)} chars")
                    return text
                return ""
            else:
                # Could be login redirect HTML
                if b"login" in data[:500].lower() or b"sign in" in data[:500].lower():
                    print(f"    🔒 DownloadAll requires login")
                else:
                    print(f"    ⚠️  Unknown format: {content_type}")
                return ""

        # Extract text from all files in the ZIP
        all_text = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            file_list = zf.namelist()
            print(f"    📦 ZIP contains {len(file_list)} files: {', '.join(file_list[:5])}")

            for filename in file_list:
                if filename.endswith("/"):  # Skip directories
                    continue

                file_data = zf.read(filename)
                ext = filename.lower().split(".")[-1]

                text = ""
                if ext == "pdf":
                    from utils.pdf_extractor import _extract_pdf_text
                    text = _extract_pdf_text(file_data)
                elif ext in ("docx", "doc"):
                    from utils.pdf_extractor import _extract_docx_text
                    text = _extract_docx_text(file_data)
                elif ext in ("xlsx", "xls"):
                    text = _extract_xlsx_text(file_data)
                elif ext == "txt":
                    text = file_data.decode("utf-8", errors="ignore")

                if text.strip():
                    all_text.append(f"--- File: {filename} ---\n{text[:4000]}")

        return "\n\n".join(all_text)

    except Exception as e:
        print(f"    ⚠️  ZIP extraction error: {e}")
        return ""


async def _access_sharepoint_folder(url: str) -> str:
    """
    Access a UNDP Docs-Public SharePoint folder URL.
    SharePoint returns JSON with file listings — extract file download URLs
    and download each file.
    """
    try:
        async with httpx.AsyncClient(
            headers={**HEADERS, "Accept": "application/json"},
            follow_redirects=True,
            timeout=20
        ) as client:
            response = await client.get(url)

            if response.status_code != 200:
                print(f"    ⚠️  SharePoint HTTP {response.status_code}")
                return ""

            text = response.text
            if _is_login_gate(text):
                print(f"    🔒 SharePoint requires login")
                return "More info after login"

            # Try to parse as HTML and find file links
            soup = BeautifulSoup(text, "lxml")
            file_links = []

            # SharePoint file links typically have these patterns
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(ext in href.lower() for ext in [".pdf", ".docx", ".doc", ".xlsx", ".pptx"]):
                    if href.startswith("http"):
                        file_links.append(href)
                    elif href.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        file_links.append(f"{parsed.scheme}://{parsed.netloc}{href}")

            if file_links:
                print(f"    📁 SharePoint: {len(file_links)} file(s) found")
                from utils.pdf_extractor import extract_text_from_pdf_url
                all_text = []
                for furl in file_links[:5]:  # Max 5 files
                    ftext = await extract_text_from_pdf_url(furl)
                    if ftext:
                        fname = furl.split("/")[-1][:40]
                        all_text.append(f"[{fname}]\n{ftext}")
                return "\n\n".join(all_text)
            else:
                # Return raw page text as fallback (may contain useful info)
                page_text = soup.get_text(separator="\n", strip=True)
                if len(page_text) > 200 and not _is_login_gate(page_text):
                    return page_text[:3000]

    except Exception as e:
        print(f"    ⚠️  SharePoint error: {e}")

    return ""


async def _fetch_quantum_page(url: str) -> str:
    """
    Fetch a UNDP Quantum Negotiation page.
    Some are public, some redirect to login.
    """
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, follow_redirects=True, timeout=20
        ) as client:
            response = await client.get(url)

            if response.status_code != 200:
                return ""

            text = response.text
            if _is_login_gate(text):
                print(f"    🔒 Quantum page requires login")
                return "More info after login"

            soup = BeautifulSoup(text, "lxml")
            clean = soup.get_text(separator="\n", strip=True)

            if len(clean) > 300:
                print(f"    ✅ Quantum page: {len(clean)} chars")
                return clean[:4000]

    except Exception as e:
        print(f"    ⚠️  Quantum fetch error: {e}")

    return ""


def _extract_xlsx_text(data: bytes) -> str:
    """Extract text from Excel files inside ZIP."""
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf) as z:
            names = z.namelist()
            # Get shared strings (cell text values)
            shared_strings = []
            if "xl/sharedStrings.xml" in names:
                ss_xml = z.read("xl/sharedStrings.xml")
                root = ET.fromstring(ss_xml)
                ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                for si in root.iter(f"{{{ns}}}si"):
                    t_els = si.iter(f"{{{ns}}}t")
                    text = "".join(t.text or "" for t in t_els)
                    shared_strings.append(text)

            # Get first sheet content
            sheet_files = [n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
            if sheet_files:
                sheet_xml = z.read(sheet_files[0])
                root = ET.fromstring(sheet_xml)
                ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                rows_text = []
                for row in root.iter(f"{{{ns}}}row"):
                    row_vals = []
                    for c in row.iter(f"{{{ns}}}c"):
                        t_attr = c.get("t", "")
                        v_el = c.find(f"{{{ns}}}v")
                        if v_el is not None and v_el.text:
                            if t_attr == "s":  # shared string index
                                idx = int(v_el.text)
                                row_vals.append(shared_strings[idx] if idx < len(shared_strings) else "")
                            else:
                                row_vals.append(v_el.text)
                    if row_vals:
                        rows_text.append(" | ".join(row_vals))
                return "\n".join(rows_text)[:3000]
    except Exception as e:
        print(f"    ⚠️  XLSX parse error: {e}")
    return ""
