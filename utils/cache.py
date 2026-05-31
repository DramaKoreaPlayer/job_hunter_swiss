"""Cache SQLite pour le mode incrémental — évite de re-traiter les offres déjà vues."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from rich.console import Console

import config
from scrapers.base import JobOffer

console = Console()


class JobCache:
    """Gère un historique SQLite des offres déjà scrapées."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), "..", config.CACHE_DB_PATH
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Crée la table si elle n'existe pas."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_offers (
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    company TEXT,
                    source TEXT,
                    relevance_score INTEGER DEFAULT 0,
                    first_seen TEXT,
                    last_seen TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_seen
                ON seen_offers(last_seen)
            """)
            conn.commit()

    def filter_new(self, offers: list[JobOffer]) -> list[JobOffer]:
        """Retourne uniquement les offres qui ne sont PAS dans le cache."""
        if not offers:
            return []

        with sqlite3.connect(self.db_path) as conn:
            # Récupérer toutes les URLs connues
            cursor = conn.execute("SELECT url FROM seen_offers")
            known_urls = {row[0] for row in cursor.fetchall()}

        new_offers = []
        for offer in offers:
            clean_url = offer.url.rstrip("/").split("?")[0] if offer.url else ""
            if clean_url and clean_url not in known_urls:
                new_offers.append(offer)
            elif not clean_url:
                # Pas d'URL → on la garde par sécurité
                new_offers.append(offer)

        return new_offers

    def save_offers(self, offers: list[JobOffer]):
        """Sauvegarde les offres dans le cache."""
        if not offers:
            return

        now = datetime.now().isoformat()

        with sqlite3.connect(self.db_path) as conn:
            for offer in offers:
                clean_url = offer.url.rstrip("/").split("?")[0] if offer.url else ""
                if not clean_url:
                    continue

                conn.execute("""
                    INSERT INTO seen_offers (url, title, company, source, relevance_score, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        relevance_score = excluded.relevance_score
                """, (
                    clean_url,
                    offer.title[:200],
                    offer.company[:100],
                    offer.source[:50],
                    offer.relevance_score,
                    now,
                    now,
                ))
            conn.commit()

        console.print(f"[dim]💾 Cache mis à jour : {len(offers)} offres enregistrées[/dim]")

    def cleanup(self, days: int | None = None):
        """Supprime les offres plus anciennes que X jours."""
        days = days or config.CACHE_EXPIRY_DAYS
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM seen_offers WHERE last_seen < ?", (cutoff,)
            )
            removed = cursor.rowcount
            conn.commit()

        if removed:
            console.print(f"[dim]🧹 Cache nettoyé : {removed} offres expirées supprimées[/dim]")

    def stats(self) -> dict:
        """Retourne les statistiques du cache."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM seen_offers").fetchone()[0]
            sources = conn.execute(
                "SELECT source, COUNT(*) FROM seen_offers GROUP BY source"
            ).fetchall()

        return {
            "total": total,
            "by_source": dict(sources),
        }
