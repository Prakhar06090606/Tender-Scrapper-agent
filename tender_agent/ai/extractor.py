# ai/extractor.py — Single Gemini key, wait-and-retry on 429
import json
import re
import os
import time
import asyncio
from datetime import date, datetime
import google.generativeai as genai
from config import CATEGORY_KEYWORDS

# ── Single API Key ─────────────────────────────────────────────────────────────
def _load_api_key() -> str:
    for var in ["GEMINI_API_KEY_1", "GEMINI_API_KEY"]:
        key = os.getenv(var, "").strip()
        if key and key != "your_gemini_api_key_here":
            print(f"🔑 Gemini API key loaded ({var})")
            return key
    raise ValueError("No Gemini API key found. Set GEMINI_API_KEY_1 in your .env file.")

_API_KEY = _load_api_key()

def _get_model():
    genai.configure(api_key=_API_KEY)
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config={"temperature": 0, "response_mime_type": "application/json"},
    )

# ── Global rate limiter ────────────────────────────────────────────────────────
# Serializes all Gemini calls — one at a time, 2s apart = max 30/min
_gemini_lock = asyncio.Semaphore(1)

# ── Company profile ────────────────────────────────────────────────────────────
COMPANY_PROFILE = """
BIDDING ENTITY: EduBild + IT Kamtech (Joint Venture / Consortium)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EDUBILD (Lead Partner)
Website: edubild.com | Location: Jaipur, India
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What EduBild brings:
- Consulting & advisory (policy, strategy, research, assessments)
- AI / ML solutions and advisory
- Capacity building, training, and skill development programs
- Research, studies, surveys, evaluations, M&E, baseline studies
- Data analytics and data science advisory
- Digital transformation strategy
- EdTech solutions and advisory
- Climate change, sustainability, and environmental assessments
- Social sector consulting (health, education, livelihoods, gender)
- Programme/project management (PMU/PMC)

Typical EduBild clients: UN agencies (UNDP, UNICEF, WHO, ILO, UN Women, FAO),
World Bank, Government of India ministries, state governments, NGOs, bilateral donors (GIZ, USAID).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IT KAMTECH (Technical Partner)
Website: itkamtech.com | Location: Jaipur, Odisha, Germany
ISO certified, CMMI certified | 20+ years experience | 1000+ clients
Existing clients: UNDP, UNICEF, LTI, JP Morgan
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What Kamtech brings:
- Mobile application development (Android & iOS)
- Custom software development and deployment
- Custom web application and portal development
- Software development outsourcing
- Multi-vendor e-commerce and marketplace platforms
- E-learning app development and LMS platforms
- Drupal, WordPress web development
- Shopify store development
- UI/UX design services
- Big data analytics and dashboards
- Digital marketing and communications campaigns
- IT consulting and strategic IT roadmaps
- IT training and certification programs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMBINED JV STRENGTHS:
- Full-stack: Strategy + Technology (advisory + build)
- ISO + CMMI certified (Kamtech)
- 20+ years software delivery experience (Kamtech)
- Existing UNDP/UNICEF client relationships (both)
- India-based with international reach
- Can handle both consulting-only AND IT-development tenders
- Can bid solo (EduBild alone for pure consulting) OR as JV for tech delivery

CANNOT DO (neither entity):
- Supply of physical goods (furniture, vehicles, construction materials)
- Civil construction or infrastructure works
- Medical / pharmaceutical supply or procurement
- Plant rental, cleaning, housekeeping, facility management
- Security services, food and beverage supply
- Hardware supply (servers, network equipment, CCTV, biometric devices)
- Data centre setup or physical IT infrastructure installation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTOR PRIORITY (for relevance scoring):
T1 — UN agencies (UNDP, UNICEF, ILO, WHO, UN Women, FAO, WFP, UNOPS), World Bank, ADB
T2 — Central Govt ministries (MeitY, MoE, MoSDE, NITI Aayog, MSDE), national schemes (PMKVY, NEP, Digital India)
T3 — State governments, large NGOs (CARE, Oxfam, SEWA), bilateral donors (GIZ, USAID, FCDO/DFID)
T4 — Small NGOs, district-level government, private companies, unclear scope
"""

# ── Deadline filter ────────────────────────────────────────────────────────────
def _is_deadline_valid(deadline_str: str) -> tuple[bool, str]:
    if not deadline_str or deadline_str == "Info not fetched":
        return True, "Deadline unknown — included for manual review"
    today = date.today()
    formats = [
        "%d %B %Y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d",
        "%B %d, %Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%y",
    ]
    clean = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", deadline_str.strip())
    clean = re.split(r"\s+at\s+|\s+\d{2}:\d{2}", clean)[0].strip()
    for fmt in formats:
        try:
            d = datetime.strptime(clean, fmt).date()
            if d >= today:
                return True, f"Deadline is {(d - today).days} days away ({d})"
            else:
                return False, f"Deadline was {(today - d).days} days ago ({d}) — EXPIRED"
        except ValueError:
            continue
    return True, f"Could not parse '{deadline_str}' — included for manual review"

# ── Category classifier ────────────────────────────────────────────────────────
def classify_category(title: str, description: str) -> str:
    text = f"{title} {description}".lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                scores[category] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Consulting"

# ── Text cleaner ───────────────────────────────────────────────────────────────
def _clean_page_text(text: str) -> str:
    nav_patterns = [
        r"^(English|Français|Español|Português|中文|Русский|العَرَبِيَّة)$",
        r"^\(?(French|Spanish|Portuguese|Chinese|Russian|Arabic)\)?$",
        r"^(Home|Help Center|Log in|Register|News|Search|Menu)$",
        r"^Jump into", r"^Opens new tab$",
        r"^Procurement Opportunities$", r"^Contract Awards$",
        r"^Knowledge Center$", r"^Doing Business with",
        r"^UNGM Pro", r"^Supplier Code", r"^UN Standard Products",
    ]
    content_signals = [
        r"\b(RFQ|RFP|ITB|EOI|tender|procurement|deadline|submission|proposal)\b",
        r"\b(UNDP|UNICEF|WHO|ILO|FAO|WFP|UNOPS|Ministry|Department)\b",
        r"\b(202[5-9]|203[0-9])\b",
        r"Title:", r"Description",
    ]
    lines = text.split("\n")
    cleaned, started = [], False
    for line in lines:
        s = line.strip()
        if not s:
            if started: cleaned.append("")
            continue
        is_nav = any(re.match(p, s, re.IGNORECASE) for p in nav_patterns)
        if any(re.search(p, s, re.IGNORECASE) for p in content_signals):
            started = True
        if started and not is_nav:
            cleaned.append(s)
    result = "\n".join(cleaned).strip()
    return result if len(result) > 200 else text

# ── Main extraction ────────────────────────────────────────────────────────────
async def extract_tender_fields(raw_text: str, source_url: str, source_site: str) -> dict | None:
    if len(raw_text.strip()) < 100:
        print(f"    ⚠️  Page too short — skipping")
        return _fallback_record(source_url, source_site)

    text_to_send = _clean_page_text(raw_text)[:12000]
    print(f"    📄 Sending {len(text_to_send)} chars to Gemini ({source_site})")

    prompt = f"""You are a procurement analyst for EduBild + IT Kamtech JV, an Indian consulting and technology company.
Analyze this tender and extract ALL information. Return ONLY a JSON object.

COMPANY PROFILE:
{COMPANY_PROFILE}

TENDER SOURCE: {source_site}
SOURCE URL: {source_url}

TENDER TEXT:
{text_to_send}

EXTRACTION RULES:
- Read ALL sections including any attached PDF content marked with === Document ===
- For deadline: look in Description for "Deadline:", "Closing date:", "Last date:", "Submit by:"
- For eligibility: copy FULL verbatim text, do not summarize
- For personnel_eligibility: look for Qualifications/Requirements/Competencies — copy REQUIREMENTS not job description
- If not found anywhere: use "Info not fetched"
- If login/registration needed: use "More info after login"

RELEVANCE RULES:
- "Relevant" = work is consulting, IT development, AI/ML, training, EdTech, research, assessment, digital transformation, data analytics, communications/outreach, software platforms
- "Not relevant" = physical goods supply, civil construction, medical/pharma supply, hardware procurement, cleaning, security, food, vehicles
- Individual/National Consultant tenders ARE relevant if subject matches
- Focus on WHAT THE WORK IS, not the procurement mechanism
- With Kamtech as JV, pure IT development tenders (mobile apps, portals, software) ARE now relevant

COMPANY_ELIGIBILITY RULES:
- First: copy the verbatim eligibility criteria from the tender
- Then add TWO assessment lines:
  SOLO (EduBild): [meets / partially meets / does not meet] — [one line reason]
  JV (EduBild+Kamtech): [meets / partially meets / does not meet] — [one line reason citing Kamtech's ISO/CMMI/20yr experience if relevant]

BID_STRATEGY RULES — choose exactly one value:
- "Solo — EduBild": pure consulting/research/advisory, no software delivery needed, EduBild meets eligibility alone
- "Solo — Kamtech": pure IT development tender, no consulting component, Kamtech meets eligibility alone
- "JV Recommended": both partners strengthen the bid but JV is not mandatory to meet eligibility
- "JV Required": eligibility criteria (ISO, years, turnover, software delivery) cannot be met without combining both partners
- "Not Eligible": neither entity nor JV meets minimum criteria (wrong sector, out of scope)

PRIORITY TIER RULES — include in relevance_reason:
- T1: UN agencies, World Bank, ADB — chase immediately
- T2: Central Govt ministries, national schemes (PMKVY, NEP, Digital India) — chase within 24h
- T3: State govts, large NGOs, bilateral donors (GIZ, USAID, FCDO) — chase if bandwidth
- T4: Small NGOs, district govt, private companies, unclear scope — flag for manual review

ISSUES RULES:
- Identify 2-4 PRACTICAL ISSUES the JV might face bidding for this tender
- Consider: geographic constraints, language barriers, experience gaps, competition level,
  tight deadlines, financial requirements, local presence requirements, JV agreement needed

Return this exact JSON:
{{
  "agency": "Organization posting the tender",
  "tender_title": "Full official title exactly as written",
  "link": "{source_url}",
  "area": "Geographic area where work is done",
  "submission_deadline_date": "Exact deadline date from Description section (not metadata)",
  "submission_deadline_time": "Deadline time with timezone",
  "company_eligibility": "Verbatim criteria. Then: SOLO (EduBild): [assessment]. JV (EduBild+Kamtech): [assessment]",
  "bid_strategy": "Solo — EduBild / Solo — Kamtech / JV Recommended / JV Required / Not Eligible",
  "personnel_eligibility": "Full verbatim QUALIFICATION REQUIREMENTS — degrees, years of experience, specific skills. NOT the job description.",
  "language_requirement": "Language for proposal",
  "financial_eligibility": "Financial requirements — turnover, EMD, net worth",
  "currency_for_proposal": "Currency code",
  "pre_bid_meeting_date": "Pre-bid meeting details or Not Applicable",
  "location": "Where work will be performed",
  "travel_required": "Yes / No / If required / Info not fetched",
  "tax_inclusive_exclusive": "Tax inclusive / Tax exclusive / Info not fetched",
  "jv_consortium_allowed": "Yes / No / Info not fetched",
  "brief_specification": "Clear summary of what this tender asks for and expected deliverables",
  "relevance": "Relevant or Not relevant",
  "relevance_reason": "2-3 sentences: what the work is, why it matches, and the priority tier (T1/T2/T3/T4) with reason",
  "issues_faced": "2-4 practical issues the JV might face. Format: 1. Issue one 2. Issue two 3. Issue three",
  "contact_name": "Name/surname of procurement contact from Contacts section",
  "contact_email": "Email address of procurement contact",
  "contact_phone": "Phone number of procurement contact",
  "important_links": "All links from Links/Documents section: Label: URL | Label: URL | Label: URL"
}}"""

    for attempt in range(3):
        try:
            async with _gemini_lock:
                model = _get_model()
                response = model.generate_content(prompt)
                await asyncio.sleep(2)  # stay under 15 req/min
                raw_response = response.text.strip() if response.text else ""

            if not raw_response:
                print(f"    ⚠️  Empty Gemini response")
                break

            print(f"    🤖 Gemini responded ({len(raw_response)} chars)")

            cleaned = re.sub(r"```json\s*", "", raw_response)
            cleaned = re.sub(r"```\s*", "", cleaned).strip()
            extracted = json.loads(cleaned)

            for key in extracted:
                val = extracted[key]
                if val is None or (isinstance(val, str) and val.strip() == ""):
                    extracted[key] = "Info not fetched"

            extracted["link"] = source_url

            is_valid, msg = _is_deadline_valid(extracted.get("submission_deadline_date", ""))
            if not is_valid:
                print(f"    ⏭️  SKIPPING — {msg}")
                return None
            print(f"    ✅ Deadline OK — {msg}")

            category = classify_category(
                extracted.get("tender_title", ""),
                extracted.get("brief_specification", ""),
            )

            rel = extracted.get("relevance", "Info not fetched")
            issues = extracted.get("issues_faced", "Info not fetched")
            print(f"    🎯 {rel}: {extracted.get('relevance_reason', '')[:80]}")
            if issues != "Info not fetched":
                print(f"    ⚠️  Issues: {issues[:80]}")
            print(f"    ✅ [{category}] {extracted.get('tender_title', '')[:60]}")

            return {
                "category":                   category,
                "source_site":                source_site,
                "agency":                     extracted.get("agency"),
                "tender_title":               extracted.get("tender_title"),
                "link":                       source_url,
                "area":                       extracted.get("area"),
                "submission_deadline_date":   extracted.get("submission_deadline_date"),
                "submission_deadline_time":   extracted.get("submission_deadline_time"),
                "date_scouted_on":            _today(),
                "company_eligibility":        extracted.get("company_eligibility"),
                "bid_strategy":               extracted.get("bid_strategy"),
                "personnel_eligibility":      extracted.get("personnel_eligibility"),
                "language_requirement":       extracted.get("language_requirement"),
                "financial_eligibility":      extracted.get("financial_eligibility"),
                "currency_for_proposal":      extracted.get("currency_for_proposal"),
                "pre_bid_meeting_date":       extracted.get("pre_bid_meeting_date"),
                "location":                   extracted.get("location"),
                "travel_required":            extracted.get("travel_required"),
                "tax_inclusive_exclusive":    extracted.get("tax_inclusive_exclusive"),
                "jv_consortium_allowed":      extracted.get("jv_consortium_allowed"),
                "brief_specification":        extracted.get("brief_specification"),
                "relevance":                  rel,
                "relevance_reason":           extracted.get("relevance_reason"),
                "issues_faced":               issues,
                "contact_name":               extracted.get("contact_name"),
                "contact_email":              extracted.get("contact_email"),
                "contact_phone":              extracted.get("contact_phone"),
                "important_links":            extracted.get("important_links"),
                "raw_content":                raw_text[:2000],
            }

        except json.JSONDecodeError as e:
            print(f"    ❌ JSON parse error: {e}")
            break
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["429", "quota", "RESOURCE_EXHAUSTED"]):
                wait = 60 * (attempt + 1)  # 60s → 120s → 180s
                print(f"    ⚠️  429 quota — waiting {wait}s before retry ({attempt+1}/3)...")
                time.sleep(wait)
                continue
            else:
                print(f"    ❌ Gemini error: {err_str[:80]}")
                time.sleep(10)
                continue

    return _fallback_record(source_url, source_site)


def _today() -> str:
    return date.today().strftime("%d %b %Y")


def _fallback_record(url: str, site: str) -> dict:
    empty = "Info not fetched"
    return {
        "category": "Consulting", "source_site": site,
        "agency": empty, "tender_title": f"Manual check — {url.split('/')[-1]}",
        "link": url, "area": empty,
        "submission_deadline_date": empty, "submission_deadline_time": empty,
        "date_scouted_on": _today(),
        "company_eligibility": empty, "bid_strategy": empty,
        "personnel_eligibility": empty,
        "language_requirement": empty, "financial_eligibility": empty,
        "currency_for_proposal": empty, "pre_bid_meeting_date": empty,
        "location": empty, "travel_required": empty,
        "tax_inclusive_exclusive": empty, "jv_consortium_allowed": empty,
        "brief_specification": empty,
        "relevance": empty, "relevance_reason": "Extraction failed — review manually",
        "issues_faced": empty,
        "contact_name": empty, "contact_email": empty,
        "contact_phone": empty, "important_links": empty,
        "raw_content": "",
    }
