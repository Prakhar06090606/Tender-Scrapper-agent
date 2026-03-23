# ai/relevance.py
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS:
# After a tender is extracted, we need to assess whether it's relevant to
# EduBild. This is a SEPARATE AI call from extraction — it needs the full
# company profile context and outputs exactly two things:
#   1. "Relevant" or "Not Relevant" (goes in col T)
#   2. A 2-3 sentence explanation of WHY (goes in col U)
#
# WHY SEPARATE FROM EXTRACTION:
# Mixing relevance into the extraction prompt makes both worse.
# Extraction needs precision. Relevance needs reasoning.
# Two focused calls > one overloaded call.
#
# DEADLINE FILTER (also lives here):
# Before even calling Gemini for relevance, we parse the deadline date
# and skip any tender whose deadline has already passed.
# This is the threshold: only tenders with deadline >= today are kept.
# ─────────────────────────────────────────────────────────────────────────────

import re
import json
import google.generativeai as genai
from datetime import date, datetime
from config import GEMINI_API_KEY, COMPANY_PROFILE, RELEVANCE_KEYWORDS

genai.configure(api_key=GEMINI_API_KEY)

# Separate model instance for relevance — same model, different config
relevance_model = genai.GenerativeModel(
    "gemini-2.5-flash",
    generation_config={
        "temperature": 0.2,
        "response_mime_type": "application/json",
    }
)

# Month name → number mapping for flexible date parsing
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}


def parse_deadline(deadline_str: str) -> date | None:
    """
    Parse a deadline string into a Python date object.

    WHY THIS IS HARD:
    Tender sites use wildly different date formats:
      - "10 March 2026"        (UNGM description)
      - "18-Mar-2026"          (UNGM metadata)
      - "11TH AUGUST 2025"     (older tenders)
      - "2026-03-10"           (ISO format)
      - "10/03/2026"           (DD/MM/YYYY)
      - "March 10, 2026"       (US format)
      - "10.03.2026"           (European format)

    We try multiple patterns in order from most to least specific.
    Returns None if we can't parse — caller treats as "keep the tender".
    """
    if not deadline_str or deadline_str in ("Info not fetched", "More info after login"):
        return None

    s = deadline_str.strip()

    # Pattern 1: ISO format — 2026-03-10
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Pattern 2: DD-Mon-YYYY — 18-Mar-2026
    m = re.match(r"(\d{1,2})[-/]([A-Za-z]+)[-/](\d{4})", s)
    if m:
        month = MONTH_MAP.get(m.group(2).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass

    # Pattern 3: DD Month YYYY — 10 March 2026 or 10th March 2026
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", s, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(2).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1)))
            except ValueError:
                pass

    # Pattern 4: Month DD, YYYY — March 10, 2026
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", s, re.IGNORECASE)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                pass

    # Pattern 5: DD/MM/YYYY or DD.MM.YYYY
    m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass

    # Pattern 6: YYYY/MM/DD
    m = re.match(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    return None  # Could not parse


def is_deadline_valid(deadline_str: str) -> tuple[bool, str]:
    """
    Check if a tender's deadline is today or in the future.

    Returns:
        (True, reason) if deadline is valid (today or future)
        (False, reason) if deadline has passed
        (True, reason) if deadline cannot be parsed (keep it, check manually)

    WHY WE KEEP UNPARSEABLE DATES:
    Better to include a tender you manually review than miss a valid one.
    "Info not fetched" deadlines are kept — the agent couldn't read it.
    """
    today = date.today()
    parsed = parse_deadline(deadline_str)

    if parsed is None:
        return True, f"Could not parse deadline '{deadline_str}' — keeping for manual review"

    if parsed >= today:
        days_left = (parsed - today).days
        return True, f"Deadline is {days_left} days away ({parsed.strftime('%d %b %Y')})"
    else:
        days_ago = (today - parsed).days
        return False, f"Deadline passed {days_ago} days ago ({parsed.strftime('%d %b %Y')})"


def quick_relevance_check(title: str, description: str) -> bool:
    """
    Fast keyword-based relevance pre-check before calling Gemini.

    WHY:
    Gemini calls cost quota. If a tender is obviously about buying
    furniture or office supplies, we skip the AI relevance call.
    This pre-check uses the keyword list from config.

    Returns True if at least one relevance keyword matches.
    Returns False only if NONE match AND the tender looks clearly off-topic.
    """
    text = f"{title} {description}".lower()
    matches = [kw for kw in RELEVANCE_KEYWORDS if kw.lower() in text]

    # If any keyword matches, worth checking with AI
    if matches:
        return True

    # Clear irrelevance signals — supply/goods tenders
    irrelevant_signals = [
        "supply of furniture", "office chairs", "stationery", "vehicles",
        "construction", "civil works", "road", "building", "cement",
        "food supply", "catering", "cleaning services", "security guard",
        "generator", "electrical works", "plumbing", "plants rental",
        "pest control", "printing", "uniforms", "tyres",
    ]
    clearly_irrelevant = any(sig in text for sig in irrelevant_signals)

    # If clearly irrelevant AND no keyword matches, skip AI call
    return not clearly_irrelevant


async def assess_relevance(
    tender_title: str,
    brief_specification: str,
    company_eligibility: str,
    agency: str,
) -> tuple[str, str]:
    """
    Ask Gemini whether this tender is relevant to EduBild.

    Returns:
        (relevance, reason) where:
        - relevance: "Relevant" or "Not Relevant"
        - reason: 2-3 sentence explanation for the Reason of Relevance column

    HOW THE PROMPT WORKS:
    We give Gemini:
    1. EduBild's full company profile (what we do, our capabilities)
    2. The tender details (title, what's needed, who can apply)
    3. A clear instruction to decide and explain in 2-3 sentences

    The response_mime_type=json forces clean output.
    """

    # Quick pre-check first — avoid Gemini call for obvious mismatches
    is_potentially_relevant = quick_relevance_check(tender_title, brief_specification)

    if not is_potentially_relevant:
        return (
            "Not Relevant",
            f"This tender is for goods/services unrelated to EduBild's core areas "
            f"of AI, EdTech, skill assessment, and employability platforms."
        )

    prompt = f"""You are assessing whether a government tender is relevant to a company.

COMPANY PROFILE:
{COMPANY_PROFILE}

TENDER DETAILS:
Title: {tender_title}
Agency: {agency}
What is needed: {brief_specification}
Company eligibility required: {company_eligibility}

TASK:
1. Decide if this tender is RELEVANT or NOT RELEVANT to this company.
2. Write 2-3 sentences explaining WHY — be specific about which company capability matches (or doesn't match) which tender requirement.

RULES for RELEVANT:
- The company can credibly bid for this (has the capability/experience)
- The tender is in the company's domain: AI, EdTech, skill assessment, training, employability, HR tech, digital platforms

RULES for NOT RELEVANT:
- Tender is for physical goods, construction, medical supplies, or services the company clearly cannot provide
- Eligibility requirements the company cannot meet (e.g., minimum 10 years experience when company is a startup)

Return ONLY this JSON:
{{
  "relevance": "Relevant" or "Not Relevant",
  "reason": "2-3 sentence explanation here. Be specific about the match or mismatch."
}}"""

    try:
        response = relevance_model.generate_content(prompt)
        raw = response.text.strip() if response.text else ""

        cleaned = re.sub(r"```json\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        result = json.loads(cleaned)

        relevance = result.get("relevance", "Not Relevant")
        reason = result.get("reason", "Could not assess relevance.")

        # Normalize relevance value to exactly "Relevant" or "Not Relevant"
        if "not" in relevance.lower():
            relevance = "Not Relevant"
        else:
            relevance = "Relevant"

        return relevance, reason

    except Exception as e:
        print(f"    ⚠️  Relevance assessment failed: {e}")
        # Default to "Relevant" on failure — better to include than miss
        return "Relevant", "Relevance could not be automatically assessed — please review manually."
