# models.py — Database table structure (26 sheet columns + tracking fields)
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class Tender(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    category:   str   # Sheet tab: Consulting / IT / Training and Skill / Medical Oxygen
    source_site: str  # UNGM / GeM / eProcure / DefProc / Google

    # ── Sheet columns 1–18 ────────────────────────────────────────────────────
    agency:                   Optional[str] = None
    tender_title:             Optional[str] = None
    link:                     Optional[str] = None
    area:                     Optional[str] = None
    submission_deadline_date: Optional[str] = None
    submission_deadline_time: Optional[str] = None
    date_scouted_on:          Optional[str] = None
    company_eligibility:      Optional[str] = None  # Verbatim criteria + Solo/JV assessment
    bid_strategy:             Optional[str] = None  # Solo—EduBild / Solo—Kamtech / JV Recommended / JV Required / Not Eligible
    personnel_eligibility:    Optional[str] = None
    language_requirement:     Optional[str] = None
    financial_eligibility:    Optional[str] = None
    currency_for_proposal:    Optional[str] = None
    pre_bid_meeting_date:     Optional[str] = None
    location:                 Optional[str] = None
    travel_required:          Optional[str] = None
    tax_inclusive_exclusive:  Optional[str] = None
    jv_consortium_allowed:    Optional[str] = None
    brief_specification:      Optional[str] = None

    # ── Sheet column 19 — Relevance ───────────────────────────────────────────
    relevance:        Optional[str] = None  # "Relevant" or "Not relevant"
    relevance_reason: Optional[str] = None  # Why relevant/not to EduBild

    # ── Sheet column 22 — Issues ─────────────────────────────────────────────
    issues_faced: Optional[str] = None     # Practical issues EduBild might face

    # ── Sheet columns 23–26 — Contact + Links ────────────────────────────────
    contact_name:    Optional[str] = None  # Procurement contact name
    contact_email:   Optional[str] = None  # Contact email
    contact_phone:   Optional[str] = None  # Contact phone
    important_links: Optional[str] = None  # "Label: URL | Label: URL | ..."

    # ── Internal tracking (NOT written to sheet) ──────────────────────────────
    created_at:       datetime = Field(default_factory=datetime.now)
    written_to_excel: bool     = Field(default=False)
    status:           str      = Field(default="pending")
    raw_content:      Optional[str] = None
    deadline_valid:   bool     = Field(default=True)
