# database.py
# ─────────────────────────────────────────────────────────────────────────────
# WHY THIS FILE EXISTS:
# This file handles ALL communication with the SQLite database.
# It creates the database (and tables) on first run, and provides a
# "session" object that every other file uses to read/write data.
#
# KEY CONCEPT — async/await:
# All database operations use "async" functions. This means Python doesn't
# WAIT for the DB to respond before doing other things — it continues
# working and comes back when the DB is ready. This is crucial for a
# web server that handles multiple requests at once.
#
# KEY CONCEPT — Session:
# A "session" is like a conversation with the database. You open one,
# do your reads/writes, then close it. SQLModel manages this for you.
#
# KEY CONCEPT — why SQLite:
# SQLite is a single file on disk. No server, no password, no installation.
# Perfect for a solo-user agent running on one machine. If you scale up
# later, you change DATABASE_URL in config.py to PostgreSQL and NOTHING
# else in the code changes.
# ─────────────────────────────────────────────────────────────────────────────

from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL, DB_PATH

# ── Engine ─────────────────────────────────────────────────────────────────
# The "engine" is the low-level connection to the database file.
# connect_args={"check_same_thread": False} is required for SQLite +
# async usage — SQLite normally only allows one thread, this disables that check.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,               # set True to print every SQL query (useful for debugging)
    connect_args={"check_same_thread": False},
)

# ── Session factory ────────────────────────────────────────────────────────
# AsyncSessionLocal() creates a new session whenever we need one.
# expire_on_commit=False means objects stay usable after we commit a transaction.
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """
    Called ONCE when the app starts.
    Creates all tables defined in models.py if they don't exist yet.
    If the tables already exist, this does nothing — safe to call every time.
    """
    # Ensure the data directory exists before trying to create the DB file
    import pathlib
    pathlib.Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        # SQLModel.metadata contains info about ALL your table classes
        # create_all() turns them into actual SQL tables in the .db file
        await conn.run_sync(SQLModel.metadata.create_all)
    print("✅ Database initialized at", DATABASE_URL)


async def get_session():
    """
    This is a "dependency" — FastAPI calls this automatically for every
    API request that needs a DB session. It yields a session, the endpoint
    does its work, then the session is closed automatically.

    Usage in an endpoint:
        async def my_endpoint(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        yield session


async def save_tender(session: AsyncSession, tender_data: dict) -> "Tender":
    """
    Helper function — takes a dictionary of tender fields and saves it
    to the database. Returns the saved Tender object with its new id.

    WHY A HELPER:
    Every scraper calls this same function. If we change how saving works
    (e.g., add deduplication logic), we change it here ONCE.
    """
    from models import Tender

    # Create a Tender object from the dictionary
    tender = Tender(**tender_data)
    session.add(tender)           # queue it to be inserted
    await session.commit()        # actually write to disk
    await session.refresh(tender) # reload so tender.id is populated
    return tender


async def is_duplicate(session: AsyncSession, link: str) -> bool:
    """
    Check if a tender with this exact URL already exists in the database.
    This prevents the same tender from being inserted multiple times across
    different scraping runs.

    Returns True if duplicate, False if new.
    """
    from sqlmodel import select
    from models import Tender

    if not link:
        return False

    result = await session.exec(select(Tender).where(Tender.link == link))
    existing = result.first()
    return existing is not None


async def get_pending_tenders(session: AsyncSession):
    """
    Fetch all tenders that haven't been written to Excel yet.
    The Excel writer calls this to know what rows to add.
    """
    from sqlmodel import select
    from models import Tender

    result = await session.exec(
        select(Tender).where(Tender.written_to_excel == False)
    )
    return result.all()


async def mark_written(session: AsyncSession, tender_id: int):
    """
    After a tender is successfully written to Excel, mark it as done.
    This prevents it from being written again on the next run.
    """
    from sqlmodel import select
    from models import Tender

    result = await session.exec(select(Tender).where(Tender.id == tender_id))
    tender = result.first()
    if tender:
        tender.written_to_excel = True
        session.add(tender)
        await session.commit()