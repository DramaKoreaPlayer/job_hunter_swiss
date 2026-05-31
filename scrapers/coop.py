"""Scraper pour jobs.coop.ch — portail emploi du groupe Coop Suisse."""

from __future__ import annotations

import urllib.parse

from scrapers.base import BaseScraper, JobOffer
import config


class CoopScraper(BaseScraper):
    name = "Coop Jobs"
    base_url = "https://jobs.coop.ch"

    # Termes de recherche spécifiques à Coop (ignore les autres)
    COOP_QUERIES = ["vendeur", "caisse"]

    async def search(
        self,
        query: str,
        location: str = config.DEFAULT_LOCATION,
        max_pages: int = config.MAX_PAGES_PER_SITE,
    ) -> list[JobOffer]:
        # Ne chercher que les termes pertinents pour Coop
        if query.lower() not in [q.lower() for q in self.COOP_QUERIES]:
            return []

        offers: list[JobOffer] = []

        try:
            context = await self._get_context()
            page = await context.new_page()

            try:
                for page_num in range(1, max_pages + 1):
                    # URL de recherche jobs.coop.ch
                    params = urllib.parse.urlencode({
                        "query": query,
                        "location": location,
                    })
                    url = f"{self.base_url}/search?{params}"
                    self._log(f"Page {page_num}/{max_pages}...")

                    if not await self._fetch_page(page, url, wait_ms=4000):
                        break

                    # Accepter cookies (texte en allemand sur jobs.coop.ch)
                    try:
                        cookie_btn = await page.query_selector(
                            'a:has-text("Akzeptieren"), '
                            'button:has-text("Akzeptieren"), '
                            'button:has-text("Accepter"), '
                            'button:has-text("OK")'
                        )
                        if cookie_btn:
                            await cookie_btn.click()
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass

                    # ── Chaque offre est une ligne tr.data-row ──
                    job_rows = await page.query_selector_all("tr.data-row")

                    seen_urls = set()
                    for row in job_rows:
                        try:
                            # Lien vers l'offre
                            link_el = await row.query_selector('a[href*="/job/"]')
                            if not link_el:
                                continue
                            href = await link_el.get_attribute("href")
                            if not href or href in seen_urls:
                                continue
                            seen_urls.add(href)
                            full_url = (
                                href if href.startswith("http")
                                else f"{self.base_url}{href}"
                            )

                            # Titre — td.colTitle
                            title = ""
                            title_td = await row.query_selector("td.colTitle")
                            if title_td:
                                title = (await title_td.inner_text()).strip()
                            if not title:
                                title = (await link_el.inner_text()).strip()

                            # Lieu — td.colLocation
                            loc_text = location
                            loc_td = await row.query_selector("td.colLocation")
                            if loc_td:
                                loc_text = (await loc_td.inner_text()).strip()

                            # Catégorie — td.colShifttype
                            category = ""
                            cat_td = await row.query_selector("td.colShifttype")
                            if cat_td:
                                category = (await cat_td.inner_text()).strip()

                            # Taux d'activité — td.colFacility
                            work_rate = ""
                            rate_td = await row.query_selector("td.colFacility")
                            if rate_td:
                                work_rate = (await rate_td.inner_text()).strip()

                            if title and len(title) > 3:
                                offers.append(JobOffer(
                                    title=title[:100],
                                    company="Coop",
                                    location=loc_text,
                                    url=full_url,
                                    source=self.name,
                                    work_rate=work_rate,
                                    contract_type=category,
                                ))
                        except Exception:
                            continue

                    if not job_rows:
                        break

                    await self._delay()

            finally:
                await context.close()

        except Exception as e:
            self._log_error(f"Erreur générale: {e}")

        self._log_success(len(offers), query)
        return offers
