from pathlib import Path
import sqlite3
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "researchleads.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:

        # Existing researchers table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                openalex_id TEXT UNIQUE,
                name TEXT NOT NULL,
                orcid TEXT,
                works_count INTEGER DEFAULT 0,
                cited_by_count INTEGER DEFAULT 0,
                institution TEXT,
                country TEXT,
                score INTEGER DEFAULT 0,
                source_url TEXT,
                status TEXT DEFAULT 'New',
                created_at TEXT NOT NULL
            )
        """)

        # Safe migration: add missing columns without deleting old data
        existing_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(leads)"
            ).fetchall()
        }

        new_columns = {
            "email": "TEXT",
            "phone": "TEXT",
            "email_source": "TEXT",
            "phone_source": "TEXT",
            "contact_checked_at": "TEXT"
        }

        for column, definition in new_columns.items():
            if column not in existing_columns:
                conn.execute(
                    f"ALTER TABLE leads ADD COLUMN {column} {definition}"
                )

        # Public contacts discovered on institutional pages
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                phone TEXT,
                source_url TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                status TEXT DEFAULT 'New',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                country TEXT,
                results_count INTEGER DEFAULT 0,
                searched_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_leads_country
            ON leads(country)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_leads_status
            ON leads(status)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contacts_status
            ON contacts(status)
        """)


def save_leads(leads):
    saved = 0

    with get_connection() as conn:
        for lead in leads:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO leads (
                    openalex_id, name, orcid,
                    works_count, cited_by_count,
                    institution, country, score,
                    source_url, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead.get("openalex_id"),
                lead.get("name") or "Unknown",
                lead.get("orcid"),
                lead.get("works_count", 0),
                lead.get("cited_by_count", 0),
                lead.get("institution"),
                lead.get("country"),
                lead.get("score", 0),
                lead.get("source_url"),
                "New",
                now()
            ))

            saved += cursor.rowcount

    return saved


def save_contacts(contacts):
    saved = 0
    updated = 0

    with get_connection() as conn:
        for contact in contacts:
            email = (contact.get("email") or "").strip().lower()

            if not email or "@" not in email:
                continue

            existing = conn.execute("""
                SELECT id FROM contacts
                WHERE email = ?
            """, (email,)).fetchone()

            if existing:
                conn.execute("""
                    UPDATE contacts
                    SET
                        name = COALESCE(?, name),
                        phone = COALESCE(?, phone),
                        source_url = ?,
                        checked_at = ?
                    WHERE id = ?
                """, (
                    contact.get("name"),
                    contact.get("phone"),
                    contact.get("source") or contact.get("source_url"),
                    contact.get("checked_at") or now(),
                    existing["id"]
                ))
                updated += 1

            else:
                conn.execute("""
                    INSERT INTO contacts (
                        name, email, phone,
                        source_url, checked_at,
                        status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'New', ?)
                """, (
                    contact.get("name"),
                    email,
                    contact.get("phone"),
                    contact.get("source"),
                    contact.get("checked_at") or contact.get("contact_checked_at") or now(),
                    now()
                ))
                saved += 1

    return {
        "saved": saved,
        "updated": updated
    }


def get_contacts(status=None):
    query = "SELECT * FROM contacts WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def get_leads(country=None, status=None):
    query = "SELECT * FROM leads WHERE 1=1"
    params = []

    if country:
        query += " AND country = ?"
        params.append(country)

    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def update_status(lead_id, status):
    allowed_statuses = [
        "New",
        "Researching",
        "Qualified",
        "Awaiting permission",
        "Permissioned",
        "Contacted",
        "Interested",
        "Customer",
        "Opted out"
    ]

    if status not in allowed_statuses:
        raise ValueError("Invalid lead status")

    with get_connection() as conn:
        conn.execute(
            "UPDATE leads SET status = ? WHERE id = ?",
            (status, lead_id)
        )


def update_contact_status(contact_id, status):
    allowed_statuses = [
        "New",
        "Researching",
        "Qualified",
        "Awaiting permission",
        "Permissioned",
        "Contacted",
        "Interested",
        "Customer",
        "Opted out"
    ]

    if status not in allowed_statuses:
        raise ValueError("Invalid contact status")

    with get_connection() as conn:
        conn.execute(
            "UPDATE contacts SET status = ? WHERE id = ?",
            (status, contact_id)
        )


def record_search(keyword, country, results_count):
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO search_history (
                keyword, country, results_count, searched_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            keyword,
            country,
            results_count,
            now()
        ))


def get_statistics():
    with get_connection() as conn:
        total_leads = conn.execute(
            "SELECT COUNT(*) FROM leads"
        ).fetchone()[0]

        countries = conn.execute(
            "SELECT COUNT(DISTINCT country) FROM leads"
        ).fetchone()[0]

        searches = conn.execute(
            "SELECT COUNT(*) FROM search_history"
        ).fetchone()[0]

        total_contacts = conn.execute(
            "SELECT COUNT(*) FROM contacts"
        ).fetchone()[0]

    return {
        "total_leads": total_leads,
        "total_contacts": total_contacts,
        "countries": countries,
        "searches": searches
    }


init_db()
