"""Scraper pour JobScout24.ch."""

from __future__ import annotations

import re
import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


def _looks_like_work_rate(text: str) -> bool:
    """Vérifie si le texte ressemble à un taux de travail (ex: 60-100%, 80%)."""
    return bool(re.search(r'\d+\s*[-–]\s*\d+%|^\d+%|\d+%\s*(-\s*\d+%)?', text))


class JobScout24Scraper(BaseScraper):
    name = "JobScout24"
    base_url = "https://www.jobscout24.ch"

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
                    # Nouvelle URL JobScout24 : /fr/jobs/
                    params = urllib.parse.urlencode({
                        "term": query,
                        "location": location,
                        "page": page_num,
                    })
                    url = f"{self.base_url}/fr/jobs/?{params}"
                    self._log(f"Page {page_num}/{max_pages}...")

                    if not await self._fetch_page(page, url, wait_ms=3000):
                        break

                    await self._accept_cookies(page)

                    # Sélecteur principal : a.job-link-detail
                    job_cards = await page.query_selector_all('a.job-link-detail')

                    if not job_cards:
                        # Fallback : vacancy links (même système que jobs.ch)
                        job_cards = await page.query_selector_all(
                            'a[id^="vacancy-link-"], a[href*="/detail/"]'
                        )

                    if not job_cards:
                        # Fallback encore plus large
                        job_cards = await page.query_selector_all(
                            'a[href*="/jobs/detail/"]'
                        )

                    seen_urls = set()
                    for card in job_cards:
                        try:
                            href = await card.get_attribute("href")
                            if not href or href in seen_urls:
                                continue
                            seen_urls.add(href)
                            full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                            # Titre — attribut title ou contenu texte
                            title = ""
                            title_attr = await card.get_attribute("title")
                            if title_attr:
                                title = title_attr.strip()
                            if not title:
                                title_el = await card.query_selector('span.fw_bold, [class*="title"]')
                                if title_el:
                                    title = (await title_el.inner_text()).strip()
                            if not title:
                                text = (await card.inner_text()).strip()
                                title = text.split("\n")[0].strip()

                            # Entreprise et lieu
                            company = ""
                            loc_text = location
                            work_rate = ""
                            try:
                                caption_els = await card.query_selector_all(
                                    'p[class*="caption"], p, span[class*="company"]'
                                )
                                for cap in caption_els:
                                    cap_text = (await cap.inner_text()).strip()
                                    if not cap_text:
                                        continue
                                    low = cap_text.lower()
                                    if any(c in low for c in [
                                        "lausanne", "renens", "vaud", "morges",
                                        "nyon", "yverdon", "pully"
                                    ]):
                                        loc_text = cap_text
                                    elif "%" in cap_text and _looks_like_work_rate(cap_text):
                                        work_rate = cap_text.strip()
                                    elif not company and cap_text != title:
                                        company = cap_text
                            except Exception:
                                pass

                            if title and len(title) > 3:
                                offers.append(JobOffer(
                                    title=title,
                                    company=company,
                                    location=loc_text,
                                    url=full_url.split("?")[0],
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
