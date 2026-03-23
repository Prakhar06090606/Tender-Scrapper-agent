# excel/writer.py — 26 columns matching Copy_of_Tender_List__3_.xlsx
import gspread
from google.oauth2.service_account import Credentials
from pathlib import Path
import time
from config import BASE_DIR

SHEET_ID = "1VYww31tciOSUvlEgAMPpYQiKXxETIpfm4yLoYNmBeCI"
SERVICE_ACCOUNT_PATH = BASE_DIR / "data" / "service_account.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "S.no",                                    # 1
    "Agency",                                  # 2
    "Tender Title",                            # 3
    "Link",                                    # 4
    "Area",                                    # 5
    "Submission Deadline Date",                # 6
    "Submission Deadline Time",                # 7
    "Date Scouted on",                         # 8
    "Company Eligibility",                     # 9
    "Bid Strategy",                            # 10  ← NEW (Solo—EduBild / JV Required etc.)
    "Personnel Eligibility",                   # 11
    "Language Requirement",                    # 12
    "Financial Eligibility",                   # 13
    "Currency for proposal",                   # 14
    "Pre-Bid Meeting Date",                    # 15
    "Location (home based / duty station)",    # 16
    "Travel Required or not",                  # 17
    "Tax inclusive / exclusive",               # 18
    "JV / Consortium allowed or not",          # 19  col S (header was blank in sheet)
    "Brief Specification of Expected Outcome", # 20
    "Relevance",                               # 21
    "Reason of Relevance",                     # 22
    "Issues which might be faced",             # 23
    "contact name or surname",                 # 24
    "contact email address",                   # 25
    "contact phone number",                    # 26
    "links",                                   # 27
]


def _get_client():
    if not SERVICE_ACCOUNT_PATH.exists():
        raise FileNotFoundError(f"service_account.json not found at {SERVICE_ACCOUNT_PATH}")
    creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_PATH), scopes=SCOPES)
    return gspread.authorize(creds)


# Track which sheets already have formatting applied (avoid re-applying each write)
_formatted_sheets = set()

def _get_worksheet(client, tab_name):
    spreadsheet = client.open_by_key(SHEET_ID)
    existing = [ws.title for ws in spreadsheet.worksheets()]
    is_new = tab_name not in existing

    if is_new:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=28)
        ws.append_row(HEADERS)
    else:
        ws = spreadsheet.worksheet(tab_name)
        rows = ws.get_all_values()
        if not rows:
            ws.append_row(HEADERS)
        elif len(rows[0]) < 27:
            for i, h in enumerate(HEADERS[len(rows[0]):], start=len(rows[0])+1):
                ws.update_cell(1, i, h)

    # Apply conditional formatting once per sheet per session
    if tab_name not in _formatted_sheets:
        _apply_conditional_formatting(spreadsheet, ws)
        _formatted_sheets.add(tab_name)

    return ws


def _resolve_tab(category):
    m = {
        "consulting":             "Consulting",
        "it":                     "IT",
        "information technology": "IT",
        "ai":                     "IT",          # No AI tab yet — route to IT
        "artificial intelligence":"IT",
        "edtech":                 "Consulting",  # No EdTech tab yet — route to Consulting
        "ed-tech":                "Consulting",
        "education technology":   "Consulting",
        "training and skill":     "Training and Skill",
        "training":               "Training and Skill",
        "skill":                  "Training and Skill",
        "medical oxygen":         "Medical Oxygen",
        "medical":                "Medical Oxygen",
        "oxygen":                 "Medical Oxygen",
    }
    return m.get(category.lower().strip(), "Consulting")


def _c(v):
    if v is None or str(v).strip() == "":
        return "Info not fetched"
    return str(v).strip()


def _next_sno(ws):
    return max(1, len(ws.get_all_values()))


def _apply_conditional_formatting(spreadsheet, ws):
    """
    Apply row-level conditional formatting to a worksheet via Sheets API.

    THREE RULES (applied in priority order — first match wins):

    1. RED   — Deadline has passed (today > deadline date)
               Condition: date in col F (index 5) < today
               Entire row background: light red #FFCDD2

    2. YELLOW — Deadline is within 2 days
               Condition: date in col F is between today and today+2
               Entire row background: light yellow #FFF9C4

    3. GREEN  — Tender is Relevant
               Condition: col T (index 19) contains "Relevant" but not "Not relevant"
               Entire row background: light green #C8E6C9

    WHY THIS APPROACH:
    gspread's add_conditional_format_rule() sends a batchUpdate request to
    the Sheets API with a BooleanRule. The condition evaluates a formula
    against each row. We use INDIRECT() to make the formula row-relative.

    PRIORITY: Rules are applied in the order they are added. We add RED first
    so an expired-but-relevant tender shows red (expired is more urgent info).
    """
    sheet_id = ws._properties["sheetId"]

    # Helper: add one conditional format rule
    def add_rule(condition_type, values, bg_color, priority=0):
        body = {
            "requests": [{
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,   # Skip header row (row 0)
                            "endRowIndex": 1000,
                            "startColumnIndex": 0,
                            "endColumnIndex": 27,  # All 27 columns
                        }],
                        "booleanRule": {
                            "condition": {
                                "type": condition_type,
                                "values": values,
                            },
                            "format": {
                                "backgroundColor": bg_color
                            }
                        }
                    },
                    "index": priority
                }
            }]
        }
        spreadsheet.batch_update(body)

    try:
        # ── RULE 1: RED — deadline has passed ─────────────────────────────────
        add_rule(
            condition_type="CUSTOM_FORMULA",
            values=[{"userEnteredValue": '=AND($F2<>"", $F2<>"Info not fetched", ISNUMBER($F2), $F2<TODAY())'}],
            bg_color={"red": 1.0, "green": 0.8, "blue": 0.8},
            priority=0
        )

        # ── RULE 2: YELLOW — deadline within 2 days ───────────────────────────
        add_rule(
            condition_type="CUSTOM_FORMULA",
            values=[{"userEnteredValue": '=AND($F2<>"", $F2<>"Info not fetched", ISNUMBER($F2), $F2>=TODAY(), $F2<=TODAY()+2)'}],
            bg_color={"red": 1.0, "green": 0.98, "blue": 0.76},
            priority=1
        )

        # ── RULE 3: GREEN — tender is relevant ────────────────────────────────
        # Relevance is now col U (col 21, index 20) after adding Bid Strategy at col 10
        add_rule(
            condition_type="CUSTOM_FORMULA",
            values=[{"userEnteredValue": '=AND($U2<>"", $U2="Relevant")'}],
            bg_color={"red": 0.78, "green": 0.93, "blue": 0.78},
            priority=2
        )

        # ── RULE 4: BLUE — JV Required bids ──────────────────────────────────
        # Bid Strategy is col J (col 10, index 9)
        # Highlight JV Required in light blue so they stand out for planning
        add_rule(
            condition_type="CUSTOM_FORMULA",
            values=[{"userEnteredValue": '=AND($J2<>"", $J2="JV Required")'}],
            bg_color={"red": 0.78, "green": 0.88, "blue": 1.0},  # light blue
            priority=3
        )

        print(f"  🎨 Conditional formatting applied to '{ws.title}'")

    except Exception as e:
        print(f"  ⚠️  Conditional formatting failed (non-critical): {e}")


def write_tenders_to_sheet(tenders):
    if not tenders:
        print("No new tenders to write.")
        return {"written": 0, "errors": 0, "by_sheet": {}}

    print(f"Writing {len(tenders)} tenders to Google Sheet...")
    try:
        client = _get_client()
    except Exception as e:
        print(f"Auth failed: {e}")
        return {"written": 0, "errors": len(tenders), "by_sheet": {}}

    stats = {"written": 0, "errors": 0, "by_sheet": {}}
    g = lambda attr: _c(getattr(tender, attr, None))

    for tender in tenders:
        try:
            tab = _resolve_tab(tender.category)
            ws = _get_worksheet(client, tab)
            sno = _next_sno(ws)

            row = [
                sno,                               # 1  S.no
                _c(tender.agency),                 # 2  Agency
                _c(tender.tender_title),           # 3  Tender Title
                _c(tender.link),                   # 4  Link
                _c(tender.area),                   # 5  Area
                _c(tender.submission_deadline_date),# 6  Deadline Date
                _c(tender.submission_deadline_time),# 7  Deadline Time
                _c(tender.date_scouted_on),        # 8  Date Scouted
                _c(tender.company_eligibility),    # 9  Company Eligibility
                _c(tender.bid_strategy),           # 10 Bid Strategy ← NEW
                _c(tender.personnel_eligibility),  # 11 Personnel Eligibility
                _c(tender.language_requirement),   # 12 Language
                _c(tender.financial_eligibility),  # 13 Financial Eligibility
                _c(tender.currency_for_proposal),  # 14 Currency
                _c(tender.pre_bid_meeting_date),   # 15 Pre-Bid Meeting
                _c(tender.location),               # 16 Location
                _c(tender.travel_required),        # 17 Travel Required
                _c(tender.tax_inclusive_exclusive), # 18 Tax
                _c(tender.jv_consortium_allowed),  # 19 JV/Consortium
                _c(tender.brief_specification),    # 20 Brief Specification
                g("relevance"),                    # 21 Relevance
                g("relevance_reason"),             # 22 Reason of Relevance
                g("issues_faced"),                 # 23 Issues
                g("contact_name"),                 # 24 Contact Name
                g("contact_email"),                # 25 Contact Email
                g("contact_phone"),                # 26 Contact Phone
                g("important_links"),              # 27 Links
            ]

            ws.append_row(row, value_input_option="USER_ENTERED")
            stats["written"] += 1
            stats["by_sheet"][tab] = stats["by_sheet"].get(tab, 0) + 1
            print(f"  ✅ [{tab}] [{g('relevance')}] {_c(tender.tender_title)[:50]}")
            time.sleep(1.1)

        except gspread.exceptions.APIError as e:
            if "429" in str(e):
                print("  Rate limited — waiting 60s...")
                time.sleep(60)
                try:
                    ws.append_row(row, value_input_option="USER_ENTERED")
                    stats["written"] += 1
                except Exception as e2:
                    print(f"  Retry failed: {e2}")
                    stats["errors"] += 1
            else:
                print(f"  API error: {e}")
                stats["errors"] += 1
        except Exception as e:
            print(f"  Error: {e}")
            stats["errors"] += 1

    print(f"\nDone — written: {stats['written']}, errors: {stats['errors']}")
    return stats


write_tenders_to_excel = write_tenders_to_sheet
