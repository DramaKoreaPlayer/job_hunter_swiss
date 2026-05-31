"""Scraper pour manpower.ch — agence de placement."""

from __future__ import annotations

import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


class ManpowerScraper(BaseScraper):
    name = "Manpower.ch"
    base_url = "https://www.manpower.ch"

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
                    # Manpower nouvelle URL : /fr/recherche
                    url = (
                        f"{self.base_url}/fr/recherche"
                        f"?searchKeyword={urllib.parse.quote(query)}"
                        f"&searchLocation={urllib.parse.quote(location)}"
                        f"&page={page_num}"
                    )
                    self._log(f"Page {page_num}/{max_pages}...")

                    if not await self._fetch_page(page, url, wait_ms=3500):
                        break

                    await self._accept_cookies(page)

                    # Sélecteur : liens avec aria-label pointant vers /fr/job/
                    job_cards = await page.query_selector_all(
                        'a[aria-label*="/fr/job/"], a[href*="/fr/job/"]'
                    )

                    if not job_cards:
                        # Fallback plus large
                        job_cards = await page.query_selector_all(
                            'a[href*="/job/"], a[href*="/emploi/"]'
                        )

                    seen = set()
                    for card in job_cards:
                        try:
                            href = await card.get_attribute("href")
                            if not href or href in seen:
                                continue

                            text = (await card.inner_text()).strip()
                            if not text or len(text) < 5:
                                continue

                            seen.add(href)
                            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                            title = text.split("\n")[0].strip()

                            # Chercher info dans le parent
                            loc = location
                            try:
                                parent = await card.evaluate_handle(
                                    "el => el.closest('div[class*=\"card\"], article, li')"
                                )
                                if parent:
                                    parent_text = await parent.inner_text()
                                    lines = [l.strip() for l in parent_text.split("\n") if l.strip()]
                                    for line in lines:
                                        low = line.lower()
                                        if any(c in low for c in [
                                            "lausanne", "renens", "vaud", "morges",
                                            "nyon", "yverdon", "pully"
                                        ]):
                                            loc = line
                                            break
                            except Exception:
                                pass

                            if title and len(title) > 3:
                                offers.append(JobOffer(
                                    title=title,
                                    company="Manpower",
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
