"""Scraper pour jobs.ch (même groupe que jobup.ch — JobCloud AG, mêmes sélecteurs)."""

from __future__ import annotations

import re
import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


def _looks_like_work_rate(text: str) -> bool:
    """Vérifie si le texte ressemble à un taux de travail (ex: 60-100%, 80%)."""
    return bool(re.search(r'\d+\s*[-–]\s*\d+%|^\d+%|\d+%\s*(-\s*\d+%)?', text))


class JobsChScraper(BaseScraper):
    name = "Jobs.ch"
    base_url = "https://www.jobs.ch"

    async def search(
        self,
        query: str,
        location: str = config.DEFAULT_LOCATION,
        max_pages: int = config.MAX_PAGES_PER_SITE,
    ) -> list[JobOffer]:
        offers: list[JobOffer] = []

        try:
            context = await self._get_context()
            page = await context.new_page()

            try:
                for page_num in range(1, max_pages + 1):
                    params = urllib.parse.urlencode({
                        "term": query,
                        "location": location,
                        "page": page_num,
                    })
                    url = f"{self.base_url}/fr/offres-emplois/?{params}"
                    self._log(f"Page {page_num}/{max_pages}...")

                    if not await self._fetch_page(page, url):
                        break

                    await self._accept_cookies(page)

                    # Jobs.ch utilise le même système que Jobup (JobCloud AG)
                    job_cards = await page.query_selector_all('a[id^="vacancy-link-"]')

                    if not job_cards:
                        job_cards = await page.query_selector_all(
                            'a[href*="/offres-emplois/detail/"], a[href*="/detail/"]'
                        )

                    seen_urls = set()
                    for card in job_cards:
                        try:
                            href = await card.get_attribute("href")
                            if not href or href in seen_urls:
                                continue
                            seen_urls.add(href)
                            full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                            # Titre — priorité à l'attribut title (le plus fiable)
                            title = ""
                            title_attr = await card.get_attribute("title")
                            if title_attr:
                                title = title_attr.strip()
                            if not title:
                                title_el = await card.query_selector('span.fw_bold')
                                if title_el:
                                    title = (await title_el.inner_text()).strip()
                            if not title:
                                title_el = await card.query_selector('span[class*="textStyle_body"]')
                                if title_el:
                                    title = (await title_el.inner_text()).strip()
                            if not title:
                                full_text = (await card.inner_text()).strip()
                                title = full_text.split("\n")[0].strip()

                            # Entreprise et lieu
                            company = ""
                            loc_text = location
                            work_rate = ""
                            caption_els = await card.query_selector_all('p.textStyle_caption1, p[class*="caption"]')
                            for cap in caption_els:
                                text = (await cap.inner_text()).strip()
                                if not text:
                                    continue
                                low = text.lower()
                                # Lieu : contient un nom de ville reconnue
                                if any(loc in low for loc in [
                                    "lausanne", "renens", "vaud", "morges", "nyon",
                                    "yverdon", "pully", "prilly", "ecublens", "bussigny"
                                ]):
                                    loc_text = text
                                # Work rate : pattern "XX-XX%" ou "XX%"
                                elif "%" in text and _looks_like_work_rate(text):
                                    work_rate = text.strip()
                                elif not company:
                                    company = text

                            if title and len(title) > 3:
                                offers.append(JobOffer(
                                    title=title,
                                    company=company,
                                    location=loc_text,
                                    url=full_url,
                                    source=self.name,
                                    work_rate=work_rate,
                                ))
                        except Exception:
                            continue

                    if not job_cards:
                        break

                    await self._delay()

            finally:
                await context.close()

        except Exception as e:
            self._log_error(f"Erreur générale: {e}")

        self._log_success(len(offers), query)
        return offers
