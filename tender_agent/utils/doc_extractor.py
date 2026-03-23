# utils/doc_extractor.py
# Smart document section extractor for tender RFP/TOR documents.
#
# WHAT THIS DOES:
# Instead of sending the full 100KB document to Gemini (8x over limit),
# it identifies and extracts only the 3 sections that matter:
#   1. Information Sheet  — deadline, currency, VAT, pre-bid, contract type
#   2. Terms of Reference — scope, deliverables, timeline
#   3. Eligibility/Evaluation Criteria — company requirements, financial threshold
#
# Blank forms (Form D, Form F, Form G etc.) are detected and skipped because
# they have labels but no values — they're templates for the bidder to fill in.
#
# CHAR LIMIT:
# For documents specifically we use 35,000 chars (vs 12,000 for page text).
# Gemini 2.0 Flash handles 1M tokens — the old 12K limit was for web pages
# where most text is navigation noise. Documents are dense and worth reading fully.

import re

# ── Section heading patterns — what signals a "useful" section ─────────────────
# These match the section titles across different UN agencies (UNDP, UN Women,
# ILO, WHO, FAO etc.) which use similar but not identical section names.

USEFUL_SECTION_PATTERNS = [
    # Information Sheet variants
    r"information\s+sheet",
    r"solicitation\s+details",
    r"procurement\s+information",
    r"rfp\s+details",
    r"tender\s+details",
    r"bidding\s+data\s+sheet",

    # Terms of Reference variants
    r"terms\s+of\s+reference",
    r"\btor\b",
    r"scope\s+of\s+(work|services)",
    r"statement\s+of\s+work",
    r"technical\s+specifications",
    r"description\s+of\s+services",
    r"background\s+and\s+objectives",
    r"deliverables",

    # Eligibility/Qualification/Evaluation variants
    r"eligibility\s+(and\s+)?(qualification|criteria)",
    r"qualification\s+criteria",
    r"evaluation\s+criteria",
    r"minimum\s+requirements",
    r"technical\s+evaluation",
    r"vendor\s+qualification",
    r"supplier\s+qualification",
    r"preliminary\s+examination",
    r"experience\s+requirements",
    r"financial\s+(standing|requirements|eligibility)",
]

# ── Form/blank template patterns — what signals USELESS sections ───────────────
# Blank forms have sequential empty label lines — lots of "Name:", "Address:"
# without any actual values filled in. We skip entire form sections.

SKIP_SECTION_PATTERNS = [
    r"^form\s+[a-z]:?\s",           # "Form A:", "Form B:", "FORM D"
    r"general\s+conditions\s+of\s+contract",
    r"^annex\s+[ivxlc]+",           # Roman numeral annexes (often GCC)
    r"statement\s+of\s+exclusivity",
    r"performance\s+security",
    r"advance\s+payment\s+(guarantee|form)",
    r"bid\s+security\s+form",
]

# Lines that are blank-form indicators — label with no value
BLANK_FORM_LABELS = [
    "name:", "address:", "signature:", "date:", "title:", "telephone:",
    "email:", "nationality:", "date of birth:", "job title:",
    "name of client:", "name of employer:", "references:",
]

MAX_DOC_CHARS = 35000   # Higher limit for documents vs 12K for web pages
MAX_SECTION_CHARS = 8000  # Max chars per section to prevent one section eating all budget


def extract_useful_sections(full_text: str) -> str:
    """
    Main entry point. Takes full document text, returns only the useful sections.

    Args:
        full_text: Complete extracted text from PDF/DOCX

    Returns:
        Concatenated text of useful sections only, under MAX_DOC_CHARS
    """
    lines = full_text.split("\n")
    sections = _split_into_sections(lines)
    useful = _filter_useful_sections(sections)

    if not useful:
        # Fallback: if we couldn't identify sections, send first 35K chars
        # but skip obvious blank form blocks
        return _smart_truncate(full_text, MAX_DOC_CHARS)

    # Combine useful sections
    combined_parts = []
    total_chars = 0

    for section_name, section_text in useful:
        if total_chars >= MAX_DOC_CHARS:
            break
        remaining = MAX_DOC_CHARS - total_chars
        chunk = section_text[:min(MAX_SECTION_CHARS, remaining)]
        combined_parts.append(f"[{section_name}]\n{chunk}")
        total_chars += len(chunk)

    result = "\n\n".join(combined_parts)
    skipped = len(sections) - len(useful)
    print(f"    📋 Sections: {len(useful)} useful, {skipped} skipped (forms/boilerplate)")
    print(f"    📊 Extracted: {len(result)} chars from {len(full_text)} char document")
    return result


def _split_into_sections(lines: list[str]) -> list[tuple[str, str]]:
    """
    Split document into (section_heading, section_text) pairs.
    Detects section boundaries by looking for heading-like lines:
    - ALL CAPS lines
    - Lines starting with SECTION N. or Section N.
    - Short lines ending in nothing (standalone heading)
    """
    sections = []
    current_heading = "PREAMBLE"
    current_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_lines.append("")
            continue

        # Detect section boundary
        is_heading = (
            # "SECTION 3. INFORMATION SHEET"
            bool(re.match(r"^SECTION\s+\d+", stripped)) or
            # "Section 3. Information Sheet"
            bool(re.match(r"^Section\s+\d+\.", stripped)) or
            # All caps short line (heading)
            (stripped.isupper() and 5 < len(stripped) < 80 and not stripped.endswith(":")) or
            # Numbered section like "3. Eligibility"
            bool(re.match(r"^\d+\.\s+[A-Z][a-z]", stripped))
        )

        if is_heading and current_lines:
            # Save current section
            sections.append((current_heading, "\n".join(current_lines)))
            current_heading = stripped
            current_lines = []
        else:
            current_lines.append(stripped)

    # Save last section
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines)))

    return sections


def _filter_useful_sections(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Filter sections into three buckets:
    - KEEP: matches useful patterns (TOR, eligibility, info sheet)
    - SKIP: matches skip patterns (forms, GCC)
    - ANALYSE: neither — check content density to decide
    """
    useful = []

    for heading, text in sections:
        heading_lower = heading.lower()

        # Explicit skip
        if any(re.search(p, heading_lower) for p in SKIP_SECTION_PATTERNS):
            continue

        # Explicit keep
        if any(re.search(p, heading_lower) for p in USEFUL_SECTION_PATTERNS):
            cleaned = _remove_blank_form_lines(text)
            if len(cleaned.strip()) > 100:
                useful.append((heading, cleaned))
            continue

        # Content density check for unrecognised sections
        # Blank forms have high ratio of empty/label lines vs content lines
        content_lines = [l for l in text.split("\n") if l.strip() and not _is_blank_label(l)]
        total_lines = len([l for l in text.split("\n") if l.strip()])

        if total_lines > 0:
            density = len(content_lines) / total_lines
            # Keep if >40% of lines have real content (not just labels)
            if density > 0.4 and len(text) > 200:
                # Also skip if it's mostly boilerplate instructions
                if not _is_boilerplate(text):
                    useful.append((heading, _remove_blank_form_lines(text)))

    return useful


def _is_blank_label(line: str) -> bool:
    """Check if a line is an empty form label like 'Name:' with no value."""
    stripped = line.strip().lower()
    return any(stripped == label or stripped == label.rstrip(":") + ":"
               for label in BLANK_FORM_LABELS)


def _is_boilerplate(text: str) -> bool:
    """Detect boilerplate legal/procedural text that adds no extraction value."""
    boilerplate_signals = [
        "shall be governed by the laws",
        "in witness whereof",
        "the parties hereto have",
        "force majeure",
        "governing law and jurisdiction",
        "entire agreement",
        "counterparts",
    ]
    text_lower = text.lower()
    matches = sum(1 for s in boilerplate_signals if s in text_lower)
    return matches >= 2


def _remove_blank_form_lines(text: str) -> str:
    """Remove lines that are blank form labels with no values."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if not _is_blank_label(line):
            cleaned.append(line)
    return "\n".join(cleaned)


def _smart_truncate(text: str, max_chars: int) -> str:
    """
    Fallback: truncate text but try to include content from different parts
    of the document (beginning + middle + end) rather than just the top.
    """
    if len(text) <= max_chars:
        return text

    # Take 40% from start, 40% from end (where eligibility often is), 20% from middle
    chunk = max_chars // 3
    start = text[:chunk * 2]
    mid_start = len(text) // 2 - chunk // 2
    middle = text[mid_start:mid_start + chunk // 2]
    end = text[-chunk:]

    return (
        start + "\n\n[... middle section ...]\n\n" +
        middle + "\n\n[... end of document ...]\n\n" + end
    )
