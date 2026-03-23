# utils/doc_parser.py
# Smart document section extractor.
# Instead of sending the whole document to Gemini (too long + full of blank forms),
# we classify each section by type and send only the useful ones.
#
# PRIORITY ORDER: Eligibility > Info Sheet > TOR > (skip forms + boilerplate)
# CHARACTER LIMIT: 35,000 for document content (Gemini 2.0 Flash handles 1M tokens)

import re

MAX_DOC_CHARS = 35_000

# ── Section type keywords ──────────────────────────────────────────────────────
# Each bucket has heading keywords that identify the section type.
# Matching is case-insensitive, partial match on the paragraph text.

SECTION_BUCKETS = {
    "ELIGIBILITY": [
        "eligibility", "qualification criteria", "evaluation criteria",
        "minimum criteria", "technical criteria", "pass/fail", "pass score",
        "previous experience", "financial standing", "qualification",
        "requirements", "section 5", "section 6",
    ],
    "INFO_SHEET": [
        "information sheet", "section 3", "general information",
        "solicitation details", "contract details", "deadline",
        "offer validity", "pre-proposal", "pre-bid", "pre bid",
        "proposal security", "performance security", "currency",
        "method of evaluation", "contract award",
    ],
    "TOR": [
        "terms of reference", "scope of work", "section 4",
        "background", "objectives", "deliverables", "expected outputs",
        "expected results", "duties and responsibilities",
        "time frame", "duration", "location of work",
        "description of services",
    ],
    "FORMS": [
        "form a", "form b", "form c", "form d", "form e",
        "form f", "form g", "form h", "form i",
        "annex i", "annex ii", "annex iii", "annex iv", "annex v",
        "annex 1", "annex 2", "annex 3",
        "format of financial proposal", "format for cv",
        "proposer information form", "proposal submission form",
        "joint venture", "consortium", "statement of exclusivity",
        "eligibility and qualification form",  # the blank form (not the criteria section)
    ],
    "BOILERPLATE": [
        "instructions to vendors", "general provisions",
        "general conditions of contract", "letter of invitation",
        "section 1", "section 2",
        "scope\n", "interpretation of", "supplier code of conduct",
        "preparation of proposals", "evaluation of proposals",
        "award of contract", "solicitation documents",
    ],
}

# A section heading is a short paragraph (< 100 chars) that looks like a title
MAX_HEADING_LEN = 100


def _classify_heading(text: str) -> str:
    """
    Classify a paragraph as a section type based on keyword matching.
    Returns one of: ELIGIBILITY, INFO_SHEET, TOR, FORMS, BOILERPLATE, CONTENT
    """
    t = text.lower().strip()
    for bucket, keywords in SECTION_BUCKETS.items():
        for kw in keywords:
            if kw in t:
                return bucket
    return "CONTENT"


def _looks_like_heading(text: str) -> bool:
    """A heading is short, often uppercase or title-case, no sentence punctuation."""
    if len(text) > MAX_HEADING_LEN:
        return False
    # All caps, or ends with colon, or matches "Section N" pattern
    if text.isupper():
        return True
    if text.endswith(":"):
        return True
    if re.match(r"^(section|annex|form)\s+\d", text, re.IGNORECASE):
        return True
    if re.match(r"^(section|annex|form)\s+[a-z]", text, re.IGNORECASE):
        return True
    # Title case with no lowercase start
    words = text.split()
    if len(words) >= 2 and sum(1 for w in words if w[0].isupper()) >= len(words) * 0.7:
        return True
    return False


def _is_blank_form_content(text: str) -> bool:
    """
    Detect blank form rows — these are template labels with no filled values.
    E.g. "Name:", "Address:", "Signature:", "Date:"
    These appear in Forms D-I and are useless noise.
    """
    stripped = text.strip()
    # Single label ending in colon with no value
    if re.match(r"^[A-Za-z\s/()]{1,40}:$", stripped):
        return True
    # Very short standalone labels
    if len(stripped) <= 4 and stripped.endswith(":"):
        return True
    return False


def extract_useful_sections(full_text: str) -> str:
    """
    Parse a full document text and return only the useful sections
    in priority order: ELIGIBILITY > INFO_SHEET > TOR.

    Skips: FORMS, BOILERPLATE, blank form content.
    Caps output at MAX_DOC_CHARS.

    Args:
        full_text: Full extracted text from PDF/DOCX

    Returns:
        Filtered and prioritized text, max 35,000 chars
    """
    lines = full_text.split("\n")

    # ── Pass 1: Split document into labelled sections ─────────────────────────
    sections = []  # list of {"type": str, "heading": str, "lines": [str]}
    current = {"type": "CONTENT", "heading": "", "lines": []}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current["lines"].append("")
            continue

        if _looks_like_heading(stripped):
            bucket = _classify_heading(stripped)
            if bucket != "CONTENT":
                # Save previous section
                if current["lines"]:
                    sections.append(current)
                current = {"type": bucket, "heading": stripped, "lines": []}
                continue

        # Skip blank form content
        if _is_blank_form_content(stripped):
            continue

        current["lines"].append(stripped)

    if current["lines"]:
        sections.append(current)

    # ── Pass 2: Collect sections by priority ──────────────────────────────────
    priority_order = ["ELIGIBILITY", "INFO_SHEET", "TOR"]
    collected = {p: [] for p in priority_order}

    for section in sections:
        stype = section["type"]
        if stype in priority_order:
            heading_line = f"\n{'='*50}\n{section['heading']}\n{'='*50}" if section["heading"] else ""
            content = "\n".join(section["lines"]).strip()
            if content:
                collected[stype].append(f"{heading_line}\n{content}")

    # ── Pass 3: Concatenate in priority order up to MAX_DOC_CHARS ─────────────
    result_parts = []
    total_chars = 0

    for bucket in priority_order:
        if not collected[bucket]:
            continue

        bucket_text = f"\n\n[{bucket} SECTIONS]\n" + "\n\n".join(collected[bucket])

        if total_chars + len(bucket_text) <= MAX_DOC_CHARS:
            result_parts.append(bucket_text)
            total_chars += len(bucket_text)
        else:
            # Take as much as we can
            remaining = MAX_DOC_CHARS - total_chars
            if remaining > 500:
                result_parts.append(bucket_text[:remaining])
            break

    if not result_parts:
        # Fallback — nothing was classified, return raw text truncated
        return full_text[:MAX_DOC_CHARS]

    skipped = [s["type"] for s in sections if s["type"] in ("FORMS", "BOILERPLATE")]
    skip_summary = f"\n[NOTE: Skipped {len(skipped)} form/boilerplate sections]" if skipped else ""

    return "".join(result_parts) + skip_summary


def smart_extract_document(raw_text: str, filename: str = "") -> str:
    """
    Main entry point. Applies smart extraction for known document types,
    falls back to truncation for unknown types.

    Args:
        raw_text:  Full text extracted from PDF/DOCX/XLSX
        filename:  Original filename (used for type hints)

    Returns:
        Filtered text ready to send to Gemini
    """
    if not raw_text or len(raw_text) < 500:
        return raw_text

    fname_lower = filename.lower()

    # Always skip pure financial templates, CV forms, blank annexes
    skip_keywords = [
        "financial_template", "financial template",
        "form_f", "form f", "cv_format", "cv format",
        "terms_and_conditions", "general_conditions",
    ]
    if any(kw in fname_lower for kw in skip_keywords):
        print(f"    ⏭️  Skipping template file: {filename}")
        return ""

    # Apply smart section extraction for RFP/TOR documents
    rfp_keywords = ["rfp", "tor", "request_for_proposal", "terms_of_reference",
                    "solicitation", "proposal", "tender"]
    if any(kw in fname_lower for kw in rfp_keywords) or len(raw_text) > 5000:
        extracted = extract_useful_sections(raw_text)
        reduction = 100 - int(len(extracted) / max(len(raw_text), 1) * 100)
        print(f"    📊 Smart extraction: {len(raw_text):,} → {len(extracted):,} chars ({reduction}% reduced)")
        return extracted

    # Short documents — return as-is (up to limit)
    return raw_text[:MAX_DOC_CHARS]
