# utils/pdf_extractor.py
# Downloads and extracts text from tender solicitation documents (PDF/DOCX).
# Site-aware link detection — each portal has its own document URL patterns.

import io
import re
import httpx
import pdfplumber
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

MAX_PDF_SIZE_BYTES = 5 * 1024 * 1024   # 5MB max
MAX_PDF_CHARS      = 35000              # chars sent to Gemini from PDF (smart extractor will filter)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/msword,*/*",
}

# ── Site-specific document link patterns ──────────────────────────────────────
# Each portal uses different URL structures for its tender documents.
# We match based on the source site name passed in.

SITE_DOC_PATTERNS = {
    "UNGM": [
        r"estm\.fa\.em2\.oraclecloud\.com",
        r"supplier\.quantum\.partneragencies\.org",
        # UNDP Procurement Notices (direct tender docs)
        r"procurement-notices\.undp\.org/view_negotiation",
        r"procurement-notices\.undp\.org/sharepoint",
        # UNDP SharePoint (actual solicitation documents)
        r"undp\.sharepoint\.com.*AllItems",
        # Direct PDF links on UNGM pages
        r"ungm\.org.*\.pdf",
        r"ungm\.org.*download",
        r"ungm\.org.*document",
    ],
    "GeM": [
        r"gem\.gov\.in.*bid.*document",
        r"gem\.gov\.in.*download",
        r"bidplus\.gem\.gov\.in.*pdf",
        r"\.pdf($|\?)",
    ],
    "eProcure": [
        r"eprocure\.gov\.in.*document",
        r"eprocure\.gov\.in.*download",
        r"eprocure\.gov\.in.*nit",
        r"\.pdf($|\?)",
    ],
    "DefProc": [
        # Only actual document downloads — NOT navigation pages
        r"defproc\.gov\.in.*\.pdf",
        r"defproc\.gov\.in.*downloadDocument",
        r"defproc\.gov\.in.*tenderDocument",
        r"defproc\.gov\.in.*NIT",
    ],
    "Google": [
        r"\.pdf($|\?)",
        r"/download",
        r"attachment",
    ],
    "Test": [
        # For test_scrape.py — try all known patterns
        r"estm\.fa\.em2\.oraclecloud\.com",
        r"procurement-notices\.undp\.org/view_negotiation",
        r"undp\.sharepoint\.com",
        r"\.pdf($|\?)",
        r"gem\.gov\.in.*document",
        r"eprocure\.gov\.in.*document",
        r"defproc\.gov\.in.*document",
    ]
}

# Link text keywords that indicate a document download link
DOC_LINK_TEXTS = [
    "solicitation", "negotiation document", "tender document", "bid document",
    "rfp document", "rfq document", "nit document", "terms of reference",
    "download", "attachment", "annexure", "tor ", "specification",
    "corrigendum", "addendum", "amendment",
]

# Always skip these — they are navigation/registration pages not documents
SKIP_PATTERNS = [
    r"register", r"login", r"password", r"resources-for-bidders",
    r"KnowledgeCenter/Pages/[A-Z]",   # UNGM knowledge center navigation
    r"Public/Notice$",                 # UNGM listing page itself
    r"sitemap", r"terms", r"glossary",
    r"sustainability(?!.*doc)",        # Sustainability pages (not docs)
    r"seminar", r"conference",
    r"user.?guide",
    # DefProc navigation pages — these are portal menus not tender documents
    r"FrontEndLatestActiveCorrigendums",
    r"StandardBiddingDocuments",
    r"FrontEndListTendersbyDate",
    r"FrontEndTendersByLocation",
    r"FrontEndTendersByOrganisation",
    r"FrontEndTendersByClassification",
    r"FrontEndTendersInArchive",
    r"WebTenderStatusLists",
    r"WebCancelledTenderLists",
    r"WebAwards",
    r"ResultOfTenders",
]


def find_doc_links(html: str, base_url: str, site: str = "Test") -> list[str]:
    """
    Find tender document links on a page, using site-specific patterns.
    
    Args:
        html:     Full page HTML
        base_url: Page URL (for resolving relative links)
        site:     Source site name (UNGM, GeM, eProcure, DefProc, Google, Test)
    
    Returns:
        List of URLs pointing to actual tender documents (max 5)
    """
    soup = BeautifulSoup(html, "lxml")
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Get site-specific URL patterns, fall back to Test (all patterns)
    patterns = SITE_DOC_PATTERNS.get(site, SITE_DOC_PATTERNS["Test"])
    found = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        # Build full URL
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = f"{base}{href}"
        else:
            full_url = urljoin(base_url, href)

        # Skip navigation/registration links
        if any(re.search(p, full_url, re.IGNORECASE) for p in SKIP_PATTERNS):
            continue

        link_text = a_tag.get_text(strip=True).lower()

        # Match by URL pattern OR by link text
        url_matches = any(re.search(p, full_url, re.IGNORECASE) for p in patterns)
        text_matches = any(kw in link_text for kw in DOC_LINK_TEXTS)

        if (url_matches or text_matches) and full_url not in found:
            found.append(full_url)

    if found:
        print(f"    🔗 Found {len(found)} document link(s) for {site}")
        for l in found[:5]:
            print(f"       {l[:80]}")

    return found[:5]


# ── Smart section extractor ────────────────────────────────────────────────────
# Extracts only useful sections (Eligibility, Info Sheet, TOR) from RFP documents.
# Skips blank forms, general conditions, boilerplate instructions.
# Reduces 100KB+ documents to ~20KB of signal while preserving all key data.

import re as _re

_SECTION_PATTERNS = [
    # Information Sheet — has deadline, currency, VAT, pre-bid
    (_re.compile(r"^SECTION\s+\d+[\.\:\s].*(INFO.*SHEET|INFORMATION\s+SHEET|TENDER\s+DETAILS|BID\s+DATA)", _re.I), "INFO_SHEET"),
    (_re.compile(r"^INFORMATION\s+SHEET$|^BID\s+DATA\s+SHEET|^TENDER\s+DETAILS$", _re.I), "INFO_SHEET"),
    # Terms of Reference — has scope, deliverables
    (_re.compile(r"^SECTION\s+\d+[\.\:\s].*(TERM.*REFERENCE|SCOPE.*WORK|STATEMENT.*WORK)", _re.I), "TOR"),
    (_re.compile(r"^TERMS\s+OF\s+REFERENCE$|^SCOPE\s+OF\s+WORK$|^STATEMENT\s+OF\s+WORK$", _re.I), "TOR"),
    # Eligibility / Qualification — company + personnel requirements
    (_re.compile(r"^SECTION\s+\d+[\.\:\s].*(EVAL|QUAL|ELIGIB|REQUIRE|CRITERIA)", _re.I), "ELIGIBILITY"),
    (_re.compile(r"^(EVALUATION|QUALIFICATION|ELIGIBILITY)\s+CRITERIA", _re.I), "ELIGIBILITY"),
    (_re.compile(r"^MINIMUM\s+(REQUIREMENTS|ELIGIBILITY|QUALIF)", _re.I), "ELIGIBILITY"),
    (_re.compile(r"^QUALIFICATION\s+CRITERIA$|^KEY\s+PERSONNEL", _re.I), "ELIGIBILITY"),
]

_STOP_PATTERNS = [
    _re.compile(r"^FORM\s+[A-Z][\s:]", _re.I),
    _re.compile(r"^ANNEX\s+\d+[\.\:\s].*(FORM|TEMPLATE|FORMAT|BLANK)", _re.I),
    _re.compile(r"^GENERAL\s+CONDITIONS\s+OF\s+CONTRACT", _re.I),
    _re.compile(r"^STANDARD\s+TERMS\s+AND\s+CONDITIONS", _re.I),
    _re.compile(r"^SECTION\s+[12][\.\:\s].*(INSTRUCTION|GENERAL\s+PROV|LETTER\s+OF\s+INV)", _re.I),
]


def smart_extract_rfp_sections(full_text: str, max_chars: int = 35000) -> str:
    """
    Extract only the 3 useful section types from an RFP document.
    Priority order: Eligibility/Qualification > Information Sheet > TOR
    Skips: blank forms, general conditions, boilerplate.

    Works across UN Women, UNDP, ILO, WHO, and government RFP formats.
    """
    lines = full_text.split("\n")
    sections = []  # (line_index, heading, type)

    for i, line in enumerate(lines):
        l = line.strip()
        if not l or len(l) > 100:
            continue

        matched = False
        for pat, stype in _SECTION_PATTERNS:
            if pat.match(l):
                sections.append((i, l, stype))
                matched = True
                break

        if not matched:
            for pat in _STOP_PATTERNS:
                if pat.match(l):
                    sections.append((i, l, "STOP"))
                    break

    # If no sections found — document doesn't follow standard structure
    # Return as much as fits, prioritizing end of document (eligibility often last)
    if not sections:
        if len(full_text) <= max_chars:
            return full_text
        # Take first 8000 + last 27000 (eligibility tends to be at the end)
        return full_text[:8000] + "\n\n[...middle section omitted...]\n\n" + full_text[-27000:]

    # Extract content for each section (stop at STOP or next section boundary)
    extracted = {"ELIGIBILITY": [], "INFO_SHEET": [], "TOR": []}

    for idx, (start, heading, stype) in enumerate(sections):
        if stype == "STOP":
            continue
        # Find end boundary
        end = len(lines)
        for j in range(idx + 1, len(sections)):
            end = sections[j][0]
            break
        content = "\n".join(lines[start:end]).strip()
        if content and len(content) > 50:  # Skip near-empty sections
            extracted[stype].append(content[:10000])  # Cap each section at 10K

    # Build result in priority order
    parts = []
    for stype in ["ELIGIBILITY", "INFO_SHEET", "TOR"]:
        if extracted[stype]:
            combined = "\n\n".join(extracted[stype])
            parts.append(f"=== {stype} ===\n{combined}")

    if not parts:
        # Fallback: nothing matched cleanly
        return full_text[:max_chars]

    result = "\n\n".join(parts)
    return result[:max_chars]


async def extract_text_from_pdf_url(url: str) -> str:
    """Download PDF from URL and extract text. Returns empty string on failure."""
    try:
        print(f"    📥 Downloading: {url[-70:]}")

        async with httpx.AsyncClient(
            headers=HEADERS,
            follow_redirects=True,
            timeout=30,
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    print(f"    ⚠️  HTTP {response.status_code}")
                    return ""

                pdf_bytes = b""
                async for chunk in response.aiter_bytes(8192):
                    pdf_bytes += chunk
                    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
                        print(f"    ⚠️  File too large, stopping")
                        break

        if not pdf_bytes:
            return ""

        # Check file signature
        if pdf_bytes.startswith(b"%PDF"):
            return _extract_pdf_text(pdf_bytes)
        elif pdf_bytes[:2] in (b"PK", b"\xd0\xcf"):
            # ZIP-based (DOCX) or OLE (DOC) — extract what we can as text
            return _extract_docx_text(pdf_bytes)
        else:
            print(f"    ⚠️  Unknown file format")
            return ""

    except httpx.TimeoutException:
        print(f"    ⚠️  Download timed out")
        return ""
    except Exception as e:
        print(f"    ⚠️  Download error: {e}")
        return ""


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdfplumber."""
    try:
        buf = io.BytesIO(pdf_bytes)
        pages = []
        with pdfplumber.open(buf) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text and text.strip():
                        pages.append(f"[Page {i+1}]\n{text.strip()}")
                except Exception:
                    continue
        result = "\n\n".join(pages)
        from utils.doc_parser import smart_extract_document
        filtered = smart_extract_document(result, "document.pdf")
        print(f"    📄 PDF extracted: {len(result)} → {len(filtered)} chars (smart filtered)")
        return filtered
    except Exception as e:
        print(f"    ⚠️  PDF parse error: {e}")
        return ""


def _extract_docx_text(doc_bytes: bytes) -> str:
    """
    Extract text from DOCX files (ZIP-based Office format).
    Uses zipfile + basic XML parsing — no extra library needed.
    """
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        buf = io.BytesIO(doc_bytes)
        with zipfile.ZipFile(buf) as z:
            if "word/document.xml" not in z.namelist():
                return ""
            xml_content = z.read("word/document.xml")
        root = ET.fromstring(xml_content)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        texts = []
        for para in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            para_text = "".join(
                t.text or "" for t in para.iter(
                    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
                )
            )
            if para_text.strip():
                texts.append(para_text.strip())
        result = "\n".join(texts)
        from utils.doc_parser import smart_extract_document
        filtered = smart_extract_document(result, "document.docx")
        print(f"    📄 DOCX extracted: {len(result)} → {len(filtered)} chars (smart filtered)")
        return filtered
    except Exception as e:
        print(f"    ⚠️  DOCX parse error: {e}")
        return ""


async def get_tender_document_text(page_html: str, page_url: str, site: str = "Test") -> str:
    """
    Main entry point — find and extract text from all tender documents on a page.
    
    Args:
        page_html: Full HTML of the tender detail page
        page_url:  URL of the page
        site:      Source site name for targeted link detection
    
    Returns:
        Combined extracted text from all documents, or empty string
    """
    doc_links = find_doc_links(page_html, page_url, site)

    if not doc_links:
        print(f"    ℹ️  No document links found")
        return ""

    all_text = []
    for url in doc_links:
        text = await extract_text_from_pdf_url(url)
        if text:
            filename = url.split("/")[-1][:50]
            all_text.append(f"=== Document: {filename} ===\n{text}")

    return "\n\n".join(all_text)
