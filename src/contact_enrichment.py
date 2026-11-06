import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import unquote

EMAIL_PATTERN = re.compile(
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
    re.IGNORECASE
)

HEADERS = {
    "User-Agent": "ResearchLeads/1.0"
}


def extract_page_contacts(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    contacts = []
    seen_emails = set()

    for link in soup.select('a[href^="mailto:"]'):
        raw_email = unquote(
            link.get("href", "")[7:]
        ).split("?")[0].strip()

        match = EMAIL_PATTERN.search(raw_email)

        if not match:
            continue

        email = match.group(0).lower()

        if email in seen_emails:
            continue

        seen_emails.add(email)

        name = None
        phone = None

        block = link.find_parent(
            "ul",
            class_="field-info__list"
        )

        if block:
            for item in block.select("li.list-ico__item"):
                icon = item.select_one("i")
                value = item.get_text(" ", strip=True)

                if not icon:
                    continue

                classes = icon.get("class", [])

                if "ico-user-circle" in classes:
                    name = value or None

                elif "ico-phone-empty" in classes:
                    phone = value or None

        contacts.append({
            "name": name,
            "email": email,
            "phone": phone,
            "source": url,
            "checked_at": datetime.now(
                timezone.utc
            ).isoformat()
        })

    return contacts
