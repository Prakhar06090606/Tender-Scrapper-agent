# config.py — All settings, keywords, and company profile in one place
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH   = DATA_DIR / "tenders.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# ── API Keys ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID   = os.getenv("GOOGLE_CSE_ID", "")

# ── Scraping schedule ─────────────────────────────────────────────────────────
SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", "6"))

# ── Google Sheet ──────────────────────────────────────────────────────────────
GOOGLE_SHEET_ID = os.getenv(
    "GOOGLE_SHEET_ID",
    "1VYww31tciOSUvlEgAMPpYQiKXxETIpfm4yLoYNmBeCI"
)

# ── Company profile (used by Gemini for relevance assessment) ─────────────────
# Keep this up to date — the more specific, the better the relevance scoring
COMPANY_PROFILE = """
Company Name: EduBild Technologies LLP
Website: https://www.edubild.com
Type: AI/EdTech startup

What we do:
- AI-powered skill and employability assessment platform
- AI-driven mock interviews and career guidance for students
- Automated hiring and recruitment solutions for corporates
- Student-to-job readiness tools and training
- Connecting academic institutions with employers
- Workforce development and capacity building using AI

Our core capabilities:
- Artificial Intelligence (AI) development and implementation
- EdTech platform development
- Skill assessment and gap analysis
- Training program design and delivery
- Digital learning solutions
- HR Tech and recruitment automation
- Data analytics for education and employment

We serve:
- Universities and colleges (institutes)
- Corporate employers (HR departments)
- Students and fresh graduates
- Government skill development initiatives

Sectors we work in:
- Education Technology (EdTech)
- Human Resources Technology (HRTech)
- Skill Development
- Employability
- Artificial Intelligence
- Digital Transformation
"""

# ── Relevance keywords (what makes a tender relevant to EduBild) ──────────────
# These are used for quick pre-filter before sending to Gemini
RELEVANCE_KEYWORDS = [
    # Core AI/Tech
    "artificial intelligence", "machine learning", "AI", "deep learning",
    "natural language processing", "NLP", "computer vision",
    # EdTech
    "edtech", "e-learning", "online learning", "digital learning",
    "learning management", "LMS", "educational technology",
    "education technology", "ed-tech",
    # Skill development
    "skill development", "skill assessment", "employability", "upskilling",
    "reskilling", "capacity building", "workforce development",
    "vocational training", "competency", "aptitude",
    # Training & Education
    "training", "learning", "education", "curriculum", "pedagogy",
    "coaching", "mentoring", "career guidance", "career counseling",
    # Hiring & HR
    "recruitment", "hiring", "talent acquisition", "human resources",
    "HR technology", "assessment center", "psychometric",
    # Platform/Digital
    "platform development", "software development", "digital platform",
    "mobile application", "web application", "SaaS",
    # Government skill schemes
    "NSDC", "skill india", "pradhan mantri", "PMKVY", "DDU-GKY",
    "national skill", "NITI aayog", "ministry of education",
    "ministry of skill", "digital india",
    # Consulting
    "consulting", "consultancy", "advisory", "assessment", "evaluation",
    "research", "study", "survey",
]

# ── Category keywords (for sheet routing) ─────────────────────────────────────
# 5 categories for EduBild + Kamtech JV:
#   Consulting     — policy, strategy, advisory, research, M&E, social sector,
#                    climate. Also sub-tags: communications/digital marketing
#                    as outreach components (not a separate category)
#   IT             — software dev, mobile apps, web portals, UI/UX, e-commerce,
#                    CMS (WordPress/Drupal), Shopify — Kamtech's primary domain
#   AI             — AI/ML, data science, big data analytics, NLP, computer vision
#   Training       — capacity building, workshops, ToT, curriculum, skill dev
#   EdTech         — LMS, e-learning platforms, digital learning, educational apps
#
# REMOVED: "Medical Oxygen" — not relevant to EduBild or Kamtech
CATEGORY_KEYWORDS = {
    "Consulting": [
        # Core consulting
        "consulting", "consultancy", "advisory", "policy", "strategy",
        "assessment", "evaluation", "study", "survey", "analysis", "review",
        "research", "report", "baseline", "feasibility",
        # Technical assistance
        "technical assistance", "capacity building", "institutional strengthening",
        "programme management", "project management", "PMU", "PMC",
        # Social sector
        "social sector", "livelihoods", "gender", "women empowerment",
        "youth", "community", "social development",
        # Climate / environment
        "climate", "sustainability", "environment", "green", "carbon",
        "ESG", "renewable", "clean energy",
        # M&E
        "monitoring", "evaluation", "M&E", "impact assessment",
        # Communications (sub-tag — stays in Consulting)
        "communications", "outreach", "digital marketing", "campaign",
        "social media", "content strategy",
    ],
    "IT": [
        # Development
        "software development", "web development", "mobile app", "android",
        "iOS", "custom software", "web application", "web portal",
        "portal development", "system development", "platform development",
        # CMS / e-commerce
        "wordpress", "drupal", "shopify", "e-commerce", "ecommerce",
        "marketplace", "multi-vendor",
        # Design
        "UI UX", "UI/UX", "user interface", "user experience", "design",
        # Infrastructure (software side only)
        "IT", "information technology", "ERP", "CRM", "MIS",
        "database", "cloud", "SaaS", "API", "integration",
        "cybersecurity", "network software", "automation",
        # Outsourcing
        "software outsourcing", "IT outsourcing", "managed services",
    ],
    "AI": [
        "artificial intelligence", "machine learning", "deep learning",
        "natural language processing", "NLP", "computer vision",
        "data science", "data analytics", "big data", "predictive analytics",
        "AI model", "ML model", "neural network", "generative AI",
        "chatbot", "AI platform", "intelligence system",
    ],
    "Training and Skill": [
        "training", "skill development", "capacity building", "workshop",
        "seminar", "facilitation", "coaching", "mentoring",
        "curriculum development", "course design", "ToT",
        "train the trainer", "upskilling", "reskilling",
        "vocational", "employability", "career guidance",
        "NSDC", "skill india", "PMKVY", "DDU-GKY",
        "IT training", "certification", "awareness programme",
    ],
    "EdTech": [
        "e-learning", "elearning", "online learning", "digital learning",
        "LMS", "learning management system", "educational platform",
        "edtech", "ed-tech", "education technology",
        "e-learning app", "learning app", "educational app",
        "virtual classroom", "MOOCs", "digital education",
        "blended learning", "distance learning",
    ],
}

# ── Tender sites configuration ─────────────────────────────────────────────────
# Each site has a config dict with:
#   name:           Display name
#   url:            Entry/listing URL
#   requires_login: Whether login is needed for full details
#   login_url:      Where to log in (if applicable)
#   username_env:   Env var name for username credential
#   password_env:   Env var name for password credential
#   site_type:      How to navigate it (ungm/gem/eprocure/defproc/generic)
TENDER_SITES = [
    {
        "name": "UNGM",
        "url": "https://www.ungm.org/Public/Notice",
        "requires_login": False,
        "login_url": "https://www.ungm.org/Login",
        "username_env": "UNGM_USERNAME",
        "password_env": "UNGM_PASSWORD",
        "site_type": "ungm",
    },
    {
        "name": "GeM",
        "url": "https://bidplus.gem.gov.in/all-bids",
        "requires_login": False,
        "site_type": "gem",
    },
    {
        "name": "eProcure",
        "url": "https://eprocure.gov.in/eprocure/app",
        "requires_login": False,
        "site_type": "eprocure",
    },
    {
        "name": "DefProc",
        "url": "https://defproc.gov.in/nicgep/app",
        "requires_login": False,
        "site_type": "defproc",
    },
]

# ── Google search queries for tender discovery ─────────────────────────────────
GOOGLE_SEARCH_QUERIES = [
    "UNDP UNICEF RFP consulting advisory India 2026",
    "World Bank tender IT software development India 2026",
    "RFP e-learning LMS platform government India 2026",
    "tender AI machine learning data analytics India 2026",
    "RFP capacity building training skill development India 2026",
    "tender mobile app web portal government ministry India 2026",
    "UNDP tender digital transformation India 2026",
    "RFP research assessment evaluation social sector India 2026",
]
