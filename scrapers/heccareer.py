"""Scraper pour HEC Career (heccareer.ch) — portail emploi/stage HEC Lausanne."""

from __future__ import annotations

import asyncio
from scrapers.base import BaseScraper, JobOffer
import config


class HecCareerScraper(BaseScraper):
    name = "HEC Career"
    base_url = "https://heccareer.ch"
    # HEC Career a une liste fixe de ~20-30 offres, ignore les queries
    supports_query = False

    # Mots-clés pour GARDER une offre (au moins un doit matcher)
    INCLUDE_KEYWORDS = [
        "étudiant", "étudiante", "student",
        "mission étudiante", "job étudiant",
        "assistant", "assistante",
        "auxiliaire",
        "temps partiel", "à temps partiel",
        "extra", "renfort",
        "aide",
        "employé", "employée",
        "collaborateur", "collaboratrice",
    ]

    # Mots-clés pour EXCLURE une offre (stage / internship)
    EXCLUDE_KEYWORDS = [
        "stage", "stagiaire",
        "intern", "internship",
        "trainee",
        "graduate programme", "graduate program",
        "werkstudent",
    ]

    def _is_relevant(self, title: str) -> bool:
        """Vérifie si l'offre correspond à un job étudiant (pas un stage)."""
        title_lower = title.lower()

        # D'abord exclure les stages
        for kw in self.EXCLUDE_KEYWORDS:
            if kw in title_lower:
                return False

        # Ensuite vérifier qu'au moins un mot-clé inclus est présent
        for kw in self.INCLUDE_KEYWORDS:
            if kw in title_lower:
                return True

        return False

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
                url = f"{self.base_url}/fr/offres-stageemploi/"
                self._log(f"Chargement de la page...")

                if not await self._fetch_page(page, url, wait_ms=4000):
                    return offers

                await self._accept_cookies(page)

                # ── Scroll minimal pour lazy-loading AngularJS ──
                # HEC Career a ~20-30 offres max,固定 liste, pas de lazy-loading réel
                SCROLL_INCREMENT = 3000
                MAX_SCROLLS = 2      # 2 scrolls suffisent
                SCROLL_DELAY = 0.4   # rapide

                last_height = 0
                no_new_content_count = 0

                for scroll_num in range(MAX_SCROLLS):
                    # Scroll down
                    await page.evaluate(f"window.scrollBy(0, {SCROLL_INCREMENT})")
                    await asyncio.sleep(SCROLL_DELAY)

                    # Check si nouveau contenu chargé
                    new_height = await page.evaluate("document.body.scrollHeight")
                    if new_height > last_height:
                        no_new_content_count = 0
                        last_height = new_height
                    else:
                        no_new_content_count += 1
                        if no_new_content_count >= 2:
                            break

                # ── Utiliser la barre de recherche si query fournie ──
                search_input = await page.query_selector(
                    'input[placeholder*="Nom d\'emploi"], '
                    'input[placeholder*="emploi"], '
                    'input[type="search"]'
                )
                if search_input and query:
                    await search_input.fill(query)
                    await page.wait_for_timeout(2000)  # Attendre le filtrage AngularJS

                # ── Extraire les offres via les liens a.open ──
                job_links = await page.query_selector_all('a.open')

                if not job_links:
                    # Fallback : liens contenant /offres-stageemploi/détail/
                    job_links = await page.query_selector_all(
                        'a[href*="offres-stageemploi"]'
                    )

                seen_urls = set()
                for link in job_links:
                    try:
                        href = await link.get_attribute("href")
                        if not href or "détail" not in href:
                            continue
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        full_url = href if href.startswith("http") else f"{self.base_url}{href}"

                        # Titre : h1 dans le lien
                        title = ""
                        title_el = await link.query_selector("h1")
                        if title_el:
                            title = (await title_el.inner_text()).strip()
                        if not title:
                            text = (await link.inner_text()).strip()
                            title = text.split("\n")[0].strip()
                            # Supprimer "en savoir plus" du titre
                            title = title.replace("en savoir plus", "").strip()

                        if not title or len(title) < 3:
                            continue

                        # ── Filtrer : garder seulement les jobs étudiants ──
                        if not self._is_relevant(title):
                            continue

                        # ── Remonter au parent pour les métadonnées ──
                        # La structure parent contient : metadata (lieu | taux | date),
                        # nom entreprise, et le lien a.open
                        parent = await link.evaluate_handle(
                            "el => el.parentElement"
                        )

                        parent_text = ""
                        if parent:
                            try:
                                parent_text = await parent.evaluate(
                                    "el => el.innerText"
                                )
                            except Exception:
                                pass

                        # Parser les métadonnées depuis le texte parent
                        # Structure : "location\nwork_rate\ndate\ncompany\ntitle\nen savoir plus..."
                        company = ""
                        loc_text = ""
                        work_rate = ""
                        date_posted = ""

                        if parent_text:
                            lines = [
                                l.strip()
                                for l in parent_text.split("\n")
                                if l.strip()
                                and l.strip() != "en savoir plus"
                                and "arrow_right_alt" not in l.strip()
                                and l.strip() != "favorite_border"
                                and l.strip() != title
                            ]

                            for line in lines:
                                # Taux d'activité : contient "%"
                                if "%" in line and len(line) <= 10:
                                    work_rate = line
                                # Date : format JJ.MM.AAAA
                                elif len(line) == 10 and line[2] == "." and line[5] == ".":
                                    date_posted = line
                                # Première ligne non identifiée → lieu
                                elif not loc_text:
                                    loc_text = line
                                # Deuxième ligne non identifiée → entreprise
                                elif not company:
                                    company = line

                        offers.append(JobOffer(
                            title=title,
                            company=company,
                            location=loc_text or location,
                            url=full_url,
                            source=self.name,
                            work_rate=work_rate,
                            date_posted=date_posted,
                        ))
                    except Exception:
                        continue

            finally:
                await context.close()

        except Exception as e:
            self._log_error(f"Erreur générale: {e}")

        self._log_success(len(offers), query)
        return offers
