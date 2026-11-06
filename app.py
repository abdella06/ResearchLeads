import streamlit as st
import pandas as pd

from src.openalex import search_authors
from src.contact_enrichment import extract_page_contacts
from src.database import (
    save_leads,
    save_contacts,
    get_leads,
    get_contacts,
    get_statistics,
    record_search,
)

st.set_page_config(
    page_title="ResearchLeads",
    page_icon="🔬",
    layout="wide"
)

st.title("🔬 ResearchLeads")
st.caption("Academic Researcher Discovery & Public Contact Enrichment")

stats = get_statistics()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Researchers", stats["total_leads"])
c2.metric("Public Contacts", stats["total_contacts"])
c3.metric("Countries", stats["countries"])
c4.metric("Searches", stats["searches"])

tab1, tab2, tab3 = st.tabs([
    "🔎 Researcher Search",
    "📧 Contact Enrichment",
    "📁 Database"
])

with tab1:
    st.header("Find Academic Researchers")

    keyword = st.text_input(
        "Research keyword",
        placeholder="Example: Cardiology, Artificial Intelligence..."
    )

    country = st.text_input(
        "Country code (optional)",
        placeholder="FR, MA, US, GB..."
    )

    if st.button("Search Researchers", type="primary"):
        try:
            with st.spinner("Searching OpenAlex..."):
                result = search_authors(
                    keyword=keyword,
                    country_code=country.strip().upper() or None,
                    per_page=100
                )

                researchers = result["results"]
                saved = save_leads(researchers)

                record_search(
                    keyword or "All fields",
                    country.strip().upper() or None,
                    len(researchers)
                )

            st.success(
                f"Found {len(researchers)} researchers. "
                f"Saved {saved} new records."
            )

            if researchers:
                st.dataframe(
                    pd.DataFrame(researchers),
                    use_container_width=True
                )

        except Exception as error:
            st.error(f"Search failed: {error}")

with tab2:
    st.header("Extract Public Professional Contacts")

    st.write(
        "Enter public university or laboratory pages, one URL per line."
    )

    urls_text = st.text_area(
        "Institution / laboratory URLs",
        placeholder=(
            "https://www.sorbonne-universite.fr/"
            "structures-de-recherche/lbcplm\n"
            "https://www.sorbonne-universite.fr/"
            "structures-de-recherche/ad2m"
        ),
        height=150
    )

    if st.button("Extract and Save Contacts", type="primary"):
        urls = list(dict.fromkeys(
            line.strip()
            for line in urls_text.splitlines()
            if line.strip()
        ))

        if not urls:
            st.warning("Please enter at least one URL.")
        else:
            all_contacts = []

            progress = st.progress(0)

            for index, url in enumerate(urls):
                try:
                    contacts = extract_page_contacts(url)
                    all_contacts.extend(contacts)
                    st.write(
                        f"✓ {url} — {len(contacts)} contacts"
                    )
                except Exception as error:
                    st.warning(f"Failed: {url} — {error}")

                progress.progress((index + 1) / len(urls))

            if all_contacts:
                result = save_contacts(all_contacts)

                st.success(
                    f"Saved: {result['saved']} | "
                    f"Updated: {result['updated']}"
                )
            else:
                st.info("No public email contacts found.")

with tab3:
    st.header("Saved Database")

    section = st.radio(
        "Choose records",
        ["Contacts", "Researchers"],
        horizontal=True
    )

    if section == "Contacts":
        records = get_contacts()

        if records:
            df = pd.DataFrame(records)
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                "Download Contacts CSV",
                data=csv,
                file_name="research_contacts.csv",
                mime="text/csv"
            )
        else:
            st.info("No contacts saved yet.")

    else:
        records = get_leads()

        if records:
            df = pd.DataFrame(records)
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                "Download Researchers CSV",
                data=csv,
                file_name="researchers.csv",
                mime="text/csv"
            )
        else:
            st.info("No researchers saved yet.")

st.divider()
st.caption(
    "ResearchLeads | Only publicly published professional contact data. "
    "Always respect website terms, privacy rules and opt-out requests."
)
