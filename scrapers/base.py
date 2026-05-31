"""Classe de base pour tous les scrapers, BrowserManager, et dataclass JobOffer."""

from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rich.console import Console

import config

console = Console()


# ═══════════════════════════════════════════════════════
# BROWSER MANAGER — Pool de navigateurs réutilisables
# ═══════════════════════════════════════════════════════
class BrowserManager:
    """Singleton qui gère un pool de navigateurs Playwright.

    Au lieu de lancer/fermer Chromium à chaque scraper × query,
    on réutilise un seul navigateur avec des contextes isolés.
    """

    _instance: Optional[BrowserManager] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._pw = None
        self._browser = None
        self._started = False

    @classmethod
    async def get(cls) -> BrowserManager:
        """Retourne l'instance singleton, thread-safe."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    async def start(self):
        """Lance Playwright + Chromium une seule fois."""
        if self._started:
            return
        async with self._lock:
            if self._started:
                return
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
            self._started = True
            console.print("[dim]🌐 BrowserManager — Chromium lancé[/dim]")

    async def new_context(self):
        """Crée un nouveau contexte isolé (cookies, storage séparés)."""
        if not self._started:
            await self.start()
        return await self._browser.new_context(
            user_agent=config.USER_AGENT,
            locale="fr-CH",
        )

    async def shutdown(self):
        """Ferme tout proprement."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._started = False
        self._browser = None
        self._pw = None
        BrowserManager._instance = None
        console.print("[dim]🌐 BrowserManager — Chromium fermé[/dim]")


# ═══════════════════════════════════════════════════════
# JOB OFFER DATACLASS
# ═══════════════════════════════════════════════════════
@dataclass
class JobOffer:
    """Représente une offre d'emploi."""
    title: str
    company: str
    location: str
    url: str
    source: str  # nom du site
    description: str = ""
    date_posted: str = ""
    work_rate: str = ""  # taux d'activité (ex: "60-100%")
    contract_type: str = ""  # CDI, CDD, temporaire, etc.

    # Champs remplis par l'IA
    relevance_score: int = 0  # 0-100
    success_probability: int = 0  # 0-100, probabilité de réussite si candidature
    ai_summary: str = ""
    ai_keywords: list[str] = field(default_factory=list)

    # Métadonnées internes
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def _key(self):
        """Clé unique pour hash et comparaison."""
        return (self.title.lower().strip(), self.company.lower().strip(), self.url)

    def __hash__(self):
        return hash(self._key)

    def __eq__(self, other):
        if not isinstance(other, JobOffer):
            return False
        return self._key == other._key


# ═══════════════════════════════════════════════════════
# BASE SCRAPER
# ═══════════════════════════════════════════════════════
class BaseScraper(ABC):
    """Classe abstraite pour les scrapers avec browser partagé et retry."""

    name: str = "BaseScraper"
    base_url: str = ""

    def __init__(self):
        self._request_count = 0

    @abstractmethod
    async def search(
        self,
        query: str,
        location: str = config.DEFAULT_LOCATION,
        max_pages: int = config.MAX_PAGES_PER_SITE,
    ) -> list[JobOffer]:
        """Recherche des offres d'emploi. À implémenter par chaque scraper."""
        ...

    async def _get_context(self):
        """Obtient un contexte navigateur depuis le BrowserManager."""
        mgr = await BrowserManager.get()
        return await mgr.new_context()

    async def _fetch_page(self, page, url: str, wait_ms: int = 2500, retries: int = 2):
        """Navigate vers une URL avec retry automatique."""
        last_error = None
        for attempt in range(retries + 1):
            try:
                await page.goto(url, timeout=config.BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(wait_ms)
                return True
            except Exception as e:
                last_error = e
                if attempt < retries:
                    wait = (attempt + 1) * 2
                    self._log(f"⚠ Retry {attempt + 1}/{retries} dans {wait}s...")
                    await asyncio.sleep(wait)
        self._log_error(f"Échec après {retries + 1} tentatives: {last_error}")
        return False

    async def _accept_cookies(self, page):
        """Accepte les cookies si un banner est présent."""
        try:
            cookie_btn = await page.query_selector(
                'button:has-text("OK"), button:has-text("Accepter"), '
                'button:has-text("Accept"), button[id*="cookie"] , '
                'button[class*="cookie"], a[class*="cookie"]'
            )
            if cookie_btn:
                await cookie_btn.click()
                await page.wait_for_timeout(500)
        except Exception:
            pass

    async def _delay(self):
        """Pause anti-ban entre les requêtes."""
        delay = random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
        await asyncio.sleep(delay)
        self._request_count += 1

    def _log(self, message: str):
        """Log formaté avec le nom du scraper."""
        console.print(f"  [dim]\\[{self.name}][/dim] {message}")

    def _log_success(self, count: int, query: str):
        """Log du nombre de résultats trouvés."""
        if count > 0:
            console.print(
                f"  [green]✓[/green] [bold]{self.name}[/bold] → "
                f"[green]{count}[/green] offres pour « {query} »"
            )
        else:
            console.print(
                f"  [yellow]○[/yellow] [bold]{self.name}[/bold] → "
                f"[dim]aucune offre pour « {query} »[/dim]"
            )

    def _log_error(self, error: str):
        """Log d'erreur."""
        console.print(f"  [red]✗[/red] [bold]{self.name}[/bold] → {error}")
