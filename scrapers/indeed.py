"""Scraper pour indeed.ch — site d'emploi international."""

from __future__ import annotations

import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


class IndeedScraper(BaseScraper):
    name = "Indeed.ch"
    base_url = "https://ch.indeed.com"

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
                for page_num in range(max_pages):
                    start = page_num * 10
                    params = urllib.parse.urlencode({
                        "q": query,
                        "l": location,
                        "start": start,
                    })
                    url = f"{self.base_url}/emplois?{params}"
                    self._log(f"Page {page_num + 1}/{max_pages}...")

                    if not await self._fetch_page(page, url):
                        break

                    # Indeed utilise des divs avec data-jk pour chaque offre
                    job_cards = await page.query_selector_all(
                        'div.job_seen_beacon, div[class*="cardOutline"], '
                        'div.slider_item, td.resultContent, div[data-jk]'
                    )

                    if not job_cards:
                        job_cards = await page.query_selector_all(
                            'a[data-jk], a[id^="job_"], h2.jobTitle a'
                        )

                    for card in job_cards:
                        try:
                            # Titre
                            title_el = await card.query_selector(
                                'h2.jobTitle a, h2.jobTitle span, a[data-jk] span, '
                                '[class*="jobTitle"], .jobTitle'
                            )
                            title = (await title_el.inner_text()).strip() if title_el else ""

                            # Lien
                            link_el = await card.query_selector(
                                'h2.jobTitle a, a[data-jk], a[id^="job_"]'
                            )
                            href = (await link_el.get_attribute("href")) if link_el else ""
                            full_url = ""
                            if href:
                                full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                            # Entreprise
                            company_el = await card.query_selector(
                                '[data-testid="company-name"], span.css-92r8pb, '
                                '.companyName, [class*="company"]'
                            )
                            company = (await company_el.inner_text()).strip() if company_el else ""

                            # Lieu
                            loc_el = await card.query_selector(
                                '[data-testid="text-location"], .companyLocation, '
                                '[class*="location"]'
                            )
                            loc = (await loc_el.inner_text()).strip() if loc_el else location

                            if title:
                                offers.append(JobOffer(
                                    title=title,
                                    company=company,
                                    location=loc,
                                    url=full_url,
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
