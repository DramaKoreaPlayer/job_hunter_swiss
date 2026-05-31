"""Scraper pour randstad.ch — agence de placement."""

from __future__ import annotations

import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


class RandstadScraper(BaseScraper):
    name = "Randstad.ch"
    base_url = "https://www.randstad.ch"

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
                    # Randstad utilise des "pretty URLs" : /q-keyword/ci-city/pn-page/
                    q_slug = urllib.parse.quote(query.replace(" ", "-"))
                    loc_slug = urllib.parse.quote(location.lower())
                    url = (
                        f"{self.base_url}/fr/emploi/"
                        f"q-{q_slug}/"
                        f"ci-{loc_slug}/"
                        f"pn-{page_num}/"
                    )
                    self._log(f"Page {page_num}/{max_pages}...")

                    if not await self._fetch_page(page, url, wait_ms=3000):
                        break

                    await self._accept_cookies(page)

                    # Sélecteur principal : a.cards__link
                    job_cards = await page.query_selector_all('a.cards__link')

                    if not job_cards:
                        # Fallback
                        job_cards = await page.query_selector_all(
                            'a[href*="/fr/emploi/"], a[href*="/job/"]'
                        )

                    seen = set()
                    for card in job_cards:
                        try:
                            href = await card.get_attribute("href")
                            if not href or href in seen:
                                continue
                            # Filtrer les liens de navigation/pagination
                            text = (await card.inner_text()).strip()
                            if not text or len(text) < 5:
                                continue
                            seen.add(href)
                            full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                            title = text.split("\n")[0].strip()

                            # Chercher le lieu dans le texte
                            lines = [l.strip() for l in text.split("\n") if l.strip()]
                            loc = location
                            for line in lines[1:]:
                                low = line.lower()
                                if any(c in low for c in [
                                    "lausanne", "renens", "vaud", "morges", "nyon",
                                    "yverdon", "pully", "prilly", "ecublens", "bussigny"
                                ]):
                                    loc = line
                                    break

                            if title and len(title) > 3:
                                offers.append(JobOffer(
                                    title=title,
                                    company="Randstad",
                                    location=loc,
                                    url=full_url.split("?")[0],
                                    source=self.name,
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
