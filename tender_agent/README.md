# Tender Agent — Setup Guide

## What this does
- Scrapes UNGM, GeM, eProcure, DefProc every 6 hours (configurable)
- Uses free Gemini AI to extract all 19 fields from tender pages
- Classifies tenders into the correct Excel sheet automatically
- Writes new rows to Tender_List.xlsx preserving all existing data

---

## Step 1 — Install Python
Needs Python 3.11+. Check: `python --version`
Download: https://www.python.org/downloads/

## Step 2 — Install dependencies
```bash
cd tender_agent
pip install -r requirements.txt
playwright install chromium
```

## Step 3 — Get free Gemini API key
1. Go to: https://aistudio.google.com/app/apikey
2. Sign in with Google account
3. Click "Create API Key"
4. Copy the key

## Step 4 — Configure .env
```bash
# Copy the example file
cp .env.example .env

# Open .env in any text editor and set:
GEMINI_API_KEY=paste_your_key_here

# Optional: set path to your Excel file
EXCEL_PATH=C:\Users\YourName\Documents\Tender_List.xlsx
```

## Step 5 — Copy your Excel file
Copy your Tender_List.xlsx to the `data/` folder:
```bash
cp /path/to/Tender_List.xlsx data/Tender_List.xlsx
```
OR set EXCEL_PATH in .env to point to wherever your file lives.

## Step 6 — Run the agent
```bash
python main.py
```

You should see:
```
✅ Database initialized
⏰ Scheduler started — pipeline runs every 6 hours
🚀 Starting scraping pipeline...
🌐 Opening UNGM listing page...
```

## Step 7 — View API docs
Open in browser: http://localhost:8000/docs

You can:
- See all found tenders: GET /tenders
- Trigger a manual run: POST /run-now
- See statistics: GET /stats

---

## File structure explained
```
tender_agent/
├── main.py              ← START HERE — runs the app
├── config.py            ← All settings (edit this)
├── models.py            ← Database table structure
├── database.py          ← DB read/write functions
├── scheduler.py         ← Runs pipeline every N hours
├── requirements.txt     ← Python packages to install
├── .env.example         ← Copy to .env and add your keys
├── data/
│   ├── Tender_List.xlsx ← Your Excel file (put it here)
│   ├── tenders.db       ← SQLite database (auto-created)
│   └── backups/         ← Auto backups before each write
├── scraper/
│   ├── ungm.py          ← UNGM scraper
│   ├── gem.py           ← GeM scraper
│   ├── eprocure.py      ← eProcure + DefProc scrapers
│   └── google_search.py ← Google/DuckDuckGo search
├── ai/
│   └── extractor.py     ← Gemini AI field extraction
└── excel/
    └── writer.py        ← Writes tenders to correct sheet
```

---

## Troubleshooting

**"Gemini API key not set"**
→ Make sure .env exists and GEMINI_API_KEY is filled in

**"Playwright executable not found"**
→ Run: `playwright install chromium`

**"Excel file not found"**
→ Either copy Tender_List.xlsx to data/ OR set EXCEL_PATH in .env

**"Site timed out"**
→ Government portals (eProcure, DefProc) are slow. This is normal.
   The scraper will retry on the next scheduled run.

**Want to change scraping frequency?**
→ Edit SCRAPE_INTERVAL_HOURS in .env (default: 6 hours)

---

## Phase 2 (coming next)
- Next.js dashboard to review tenders visually
- Approve / Reject / Reconsider buttons
- Auto-submission of tender offers
