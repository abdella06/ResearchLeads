import os
import re
import requests
import phonenumbers

API_URL = "https://api.openalex.org/works"

COUNTRIES = {
    "United States": "US",
    "United Kingdom": "GB",
    "France": "FR",
    "Germany": "DE",
    "Canada": "CA",
    "Australia": "AU",
    "India": "IN",
    "China": "CN",
    "Spain": "ES",
    "Italy": "IT",
    "Netherlands": "NL",
    "Switzerland": "CH",
    "Belgium": "BE",
    "Morocco": "MA",
    "Saudi Arabia": "SA",
    "United Arab Emirates": "AE",
    "Turkey": "TR",
    "Brazil": "BR",
    "Japan": "JP",
    "South Africa": "ZA",
}

EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE
)


def get_api_key():
    return os.getenv("OPENALEX_API_KEY", "").strip()


def extract_contacts(text, region=None):
    if not text:
        return [], []

    emails = list(dict.fromkeys(EMAIL_PATTERN.findall(text)))
    phones = []

    try:
        for match in phonenumbers.PhoneNumberMatcher(text, region):
            number = match.number

            if phonenumbers.is_valid_number(number):
                formatted = phonenumbers.format_number(
                    number,
                    phonenumbers.PhoneNumberFormat.E164
                )

                if formatted not in phones:
                    phones.append(formatted)

    except (phonenumbers.NumberParseException, ValueError):
        pass

    return emails, phones


def search_authors(
    keyword="",
    country_code=None,
    per_page=100,
    cursor="*"
):
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100.")

    params = {
        "per_page": per_page,
        "cursor": cursor,
        "select": "id,title,doi,publication_year,authorships",
    }

    if keyword and keyword.strip():
        params["search"] = keyword.strip()
    else:
        params["sort"] = "publication_date:desc"

    if country_code:
        country_code = country_code.upper()
        params["filter"] = (
            f"authorships.institutions.country_code:{country_code}"
        )

    api_key = get_api_key()

    if api_key:
        params["api_key"] = api_key

    response = requests.get(
        API_URL,
        params=params,
        timeout=60,
        headers={"User-Agent": "ResearchLeads/1.0"}
    )

    response.raise_for_status()
    payload = response.json()

    authors = {}

    for work in payload.get("results", []):
        work_url = work.get("id")

        for authorship in work.get("authorships", []):
            author = authorship.get("author") or {}
            author_id = author.get("id")
            author_name = author.get("display_name")

            if not author_id or not author_name:
                continue

            institutions = authorship.get("institutions") or []

            if country_code:
                matching = [
                    inst for inst in institutions
                    if inst.get("country_code") == country_code
                ]
                if not matching:
                    continue
            else:
                matching = institutions

            if author_id not in authors:
                authors[author_id] = {
                    "openalex_id": author_id,
                    "name": author_name,
                    "orcid": author.get("orcid"),
                    "works_count": 0,
                    "cited_by_count": 0,
                    "institution": None,
                    "country": None,
                    "institutions": [],
                    "score": 0,
                    "source_url": author_id,
                    "email": None,
                    "phone": None,
                    "email_source": None,
                    "phone_source": None,
                    "publications": [],
                }

            lead = authors[author_id]
            lead["works_count"] += 1

            for inst in matching:
                institution = {
                    "id": inst.get("id"),
                    "name": inst.get("display_name"),
                    "country": inst.get("country_code"),
                    "type": inst.get("type"),
                }

                if institution not in lead["institutions"]:
                    lead["institutions"].append(institution)

            if matching and not lead["institution"]:
                preferred = next(
                    (
                        inst for inst in matching
                        if inst.get("type") in ("education", "healthcare")
                    ),
                    matching[0]
                )

                lead["institution"] = preferred.get("display_name")
                lead["country"] = preferred.get("country_code")

            raw_affiliations = (
                authorship.get("raw_affiliation_strings") or []
            )

            affiliation_text = " ".join(raw_affiliations)

            region = (
                matching[0].get("country_code")
                if matching else None
            )

            emails, phones = extract_contacts(
                affiliation_text,
                region
            )

            if emails and not lead["email"]:
                lead["email"] = emails[0]
                lead["email_source"] = work_url

            if phones and not lead["phone"]:
                lead["phone"] = phones[0]
                lead["phone_source"] = work_url

            if work_url and work_url not in lead["publications"]:
                lead["publications"].append(work_url)

    results = list(authors.values())

    for lead in results:
        lead["score"] = min(100, lead["works_count"] * 2)

    return {
        "results": results,
        "next_cursor": payload.get("meta", {}).get("next_cursor"),
        "count": payload.get("meta", {}).get("count", 0),
    }


def format_author(author):
    return {
        "openalex_id": author.get("id"),
        "name": author.get("display_name") or "Unknown",
        "orcid": author.get("orcid"),
        "works_count": author.get("works_count") or 0,
        "cited_by_count": author.get("cited_by_count") or 0,
        "institution": None,
        "country": None,
        "score": 0,
        "source_url": author.get("id"),
    }
