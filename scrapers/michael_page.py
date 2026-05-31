"""Scraper pour Michael Page Suisse."""

from __future__ import annotations

import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


class MichaelPageScraper(BaseScraper):
    name = "Michael Page"
    base_url = "https://www.michaelpage.ch"

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
                    # Nouvelle URL Michael Page : /fr/jobs/
                    url = (
                        f"{self.base_url}/fr/jobs/"
                        f"{urllib.parse.quote(query.replace(' ', '-'))}/"
                        f"in-{urllib.parse.quote(location)}"
                    )
                    if page_num > 1:
                        url += f"?page={page_num}"

                    self._log(f"Page {page_num}/{max_pages}...")

                    if not await self._fetch_page(page, url, wait_ms=3500):
                        break

                    await self._accept_cookies(page)

                    # Chercher les offres
                    job_cards = await page.query_selector_all(
                        'article[class*="job"], div[class*="job-item"], '
                        'li[class*="job-item"], div[class*="search-result"], '
                        'div[class*="card"]'
                    )

                    if job_cards:
                        for card in job_cards:
                            try:
                                title_el = await card.query_selector(
                                    'h2, h3, a[class*="title"], [class*="title"]'
                                )
                                title = (await title_el.inner_text()).strip() if title_el else ""

                                link_el = await card.query_selector('a[href]')
                                href = (await link_el.get_attribute("href")) if link_el else ""
                                full_url = ""
                                if href:
                                    full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                                loc_el = await card.query_selector('[class*="location"]')
                                loc = (await loc_el.inner_text()).strip() if loc_el else location

                                if title and len(title) > 3:
                                    offers.append(JobOffer(
                                        title=title,
                                        company="Michael Page",
                                        location=loc,
                                        url=full_url,
                                        source=self.name,
                                    ))
                            except Exception:
                                continue
                    else:
                        # Fallback : liens directs
                        links = await page.query_selector_all(
                            'a[href*="/job-detail/"], a[href*="/jobs/"], '
                            'a[href*="/emploi/"]'
                        )
                        seen = set()
                        for link in links:
                            try:
                                href = await link.get_attribute("href")
                                text = (await link.inner_text()).strip()
                                if not text or len(text) < 5 or href in seen:
                                    continue
                                # Ignorer les liens de navigation
                                if any(x in text.lower() for x in [
                                    "suivant", "précédent", "voir plus", "page"
                                ]):
                                    continue
                                seen.add(href)
                                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                                offers.append(JobOffer(
                                    title=text.split("\n")[0].strip(),
                                    company="Michael Page",
                                    location=location,
                                    url=full_url,
                                    source=self.name,
                                ))
                            except Exception:
                                continue

                    if not job_cards and not offers:
                        break

                    await self._delay()

            finally:
                await context.close()

        except Exception as e:
            self._log_error(f"Erreur générale: {e}")

        self._log_success(len(offers), query)
        return offers
