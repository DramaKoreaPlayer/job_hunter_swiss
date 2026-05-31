"""Scraper pour LinkedIn Jobs (sans login, via la vue publique)."""

from __future__ import annotations

import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


class LinkedinScraper(BaseScraper):
    name = "LinkedIn"
    base_url = "https://www.linkedin.com"

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
                    start = page_num * 25
                    params = urllib.parse.urlencode({
                        "keywords": query,
                        "location": f"{location}, Vaud, Suisse",
                        "start": start,
                        "f_TPR": "r604800",  # dernière semaine
                    })
                    url = f"{self.base_url}/jobs/search/?{params}"
                    self._log(f"Page {page_num + 1}/{max_pages}...")

                    if not await self._fetch_page(page, url, wait_ms=3000):
                        break

                    # LinkedIn public listings
                    job_cards = await page.query_selector_all(
                        'div.base-card, div.job-search-card, '
                        'li[class*="result-card"], div[class*="jobs-search__result"]'
                    )

                    if not job_cards:
                        # Fallback
                        links = await page.query_selector_all(
                            'a[href*="/jobs/view/"], a[data-tracking-control-name*="job"]'
                        )
                        seen = set()
                        for link in links:
                            try:
                                href = await link.get_attribute("href")
                                text = (await link.inner_text()).strip()
                                if not text or len(text) < 5 or href in seen:
                                    continue
                                seen.add(href)
                                full_url = href if href.startswith("http") else f"{self.base_url}{href}"
                                offers.append(JobOffer(
                                    title=text.split("\n")[0].strip(),
                                    company="",
                                    location=location,
                                    url=full_url.split("?")[0],
                                    source=self.name,
                                ))
                            except Exception:
                                continue
                    else:
                        for card in job_cards:
                            try:
                                title_el = await card.query_selector(
                                    'h3[class*="title"], span[class*="title"], '
                                    'a[class*="title"], h3'
                                )
                                title = (await title_el.inner_text()).strip() if title_el else ""

                                link_el = await card.query_selector(
                                    'a[href*="/jobs/view/"], a.base-card__full-link'
                                )
                                href = (await link_el.get_attribute("href")) if link_el else ""
                                full_url = href.split("?")[0] if href else ""

                                company_el = await card.query_selector(
                                    'h4[class*="company"], a[class*="company"], '
                                    'span[class*="company"], h4'
                                )
                                company = (await company_el.inner_text()).strip() if company_el else ""

                                loc_el = await card.query_selector(
                                    'span[class*="location"], span[class*="bullet"]'
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

                    if not job_cards and not offers:
                        break

                    await self._delay()

            finally:
                await context.close()

        except Exception as e:
            self._log_error(f"Erreur générale: {e}")

        self._log_success(len(offers), query)
        return offers
