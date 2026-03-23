# migrate_db.py — Run once to add missing columns to existing database
# Usage: py migrate_db.py
import sqlite3, sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "tenders.db"

if not DB_PATH.exists():
    print("No database found — nothing to migrate (fresh install is fine)")
    sys.exit(0)

NEW_COLUMNS = [
    ("issues_faced",    "TEXT"),
    ("contact_name",    "TEXT"),
    ("contact_email",   "TEXT"),
    ("contact_phone",   "TEXT"),
    ("important_links", "TEXT"),
    ("bid_strategy",    "TEXT"),   # v27 — Solo—EduBild / Solo—Kamtech / JV Recommended / JV Required / Not Eligible
]

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

# Get existing columns
cur.execute("PRAGMA table_info(tender)")
existing = {row[1] for row in cur.fetchall()}

added = []
for col_name, col_type in NEW_COLUMNS:
    if col_name not in existing:
        cur.execute(f"ALTER TABLE tender ADD COLUMN {col_name} {col_type}")
        added.append(col_name)
        print(f"  ✅ Added column: {col_name}")
    else:
        print(f"  ℹ️  Already exists: {col_name}")

conn.commit()
conn.close()

if added:
    print(f"\n✅ Migration complete — added {len(added)} columns")
else:
    print("\n✅ Database already up to date")
