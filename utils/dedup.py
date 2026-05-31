"""Déduplication optimisée des offres d'emploi multi-sources.

Utilise un système de buckets pour éviter la complexité O(n²).
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict

from rich.console import Console

from scrapers.base import JobOffer

console = Console()


def _normalize(text: str) -> str:
    """Normalise un texte pour la comparaison."""
    return " ".join(text.lower().strip().split())


def _bucket_key(text: str) -> str:
    """Génère une clé de bucket à partir d'un texte (premiers mots significatifs)."""
    words = re.sub(r'[^a-zà-ÿ0-9\s]', '', text.lower()).split()
    # Prendre les 3 premiers mots significatifs (> 2 chars)
    significant = [w for w in words if len(w) > 2][:3]
    return " ".join(significant)


def _similarity(a: str, b: str) -> float:
    """Calcule la similarité entre deux chaînes (0.0 - 1.0)."""
    a_norm = _normalize(a)
    b_norm = _normalize(b)
    if not a_norm or not b_norm:
        return 0.0
    return difflib.SequenceMatcher(None, a_norm, b_norm).ratio()


def _is_duplicate(offer_a: JobOffer, offer_b: JobOffer) -> bool:
    """Vérifie si deux offres sont probablement des doublons."""
    # Même URL = doublon certain
    if offer_a.url and offer_b.url:
        url_a = offer_a.url.rstrip("/").split("?")[0]
        url_b = offer_b.url.rstrip("/").split("?")[0]
        if url_a == url_b:
            return True

    # Titre très similaire + même entreprise
    title_sim = _similarity(offer_a.title, offer_b.title)
    company_sim = _similarity(offer_a.company, offer_b.company)

    if title_sim > 0.85 and company_sim > 0.7:
        return True

    if title_sim > 0.95:
        return True

    # Même entreprise + titre similaire + même localisation
    if (company_sim > 0.8 and title_sim > 0.7
            and _similarity(offer_a.location, offer_b.location) > 0.6):
        return True

    return False


def _best_offer(offer_a: JobOffer, offer_b: JobOffer) -> JobOffer:
    """Retourne la meilleure version entre deux doublons."""
    score_a = sum([
        len(offer_a.description) > 0,
        len(offer_a.company) > 0,
        len(offer_a.work_rate) > 0,
        len(offer_a.contract_type) > 0,
        len(offer_a.date_posted) > 0,
    ])
    score_b = sum([
        len(offer_b.description) > 0,
        len(offer_b.company) > 0,
        len(offer_b.work_rate) > 0,
        len(offer_b.contract_type) > 0,
        len(offer_b.date_posted) > 0,
    ])

    best = offer_a if score_a >= score_b else offer_b
    other = offer_b if best is offer_a else offer_a

    # Fusionner les infos manquantes
    if not best.company and other.company:
        best.company = other.company
    if not best.description and other.description:
        best.description = other.description
    if not best.work_rate and other.work_rate:
        best.work_rate = other.work_rate
    if not best.contract_type and other.contract_type:
        best.contract_type = other.contract_type

    # Ajouter la source alternative
    if other.source not in best.source:
        best.source = f"{best.source} + {other.source}"

    return best


def deduplicate(offers: list[JobOffer]) -> list[JobOffer]:
    """Déduplique les offres avec un système de buckets optimisé.

    Au lieu de comparer chaque offre à toutes les autres (O(n²)),
    on regroupe par bucket (titre normalisé) et on ne compare
    que dans les buckets voisins → quasi O(n).
    """
    if not offers:
        return []

    original_count = len(offers)

    # ── Phase 1 : Dédup rapide par URL exacte ──
    url_index: dict[str, int] = {}
    url_deduped: list[JobOffer] = []

    for offer in offers:
        clean_url = offer.url.rstrip("/").split("?")[0] if offer.url else ""
        if clean_url and clean_url in url_index:
            # Fusionner avec l'existant
            idx = url_index[clean_url]
            url_deduped[idx] = _best_offer(url_deduped[idx], offer)
        else:
            if clean_url:
                url_index[clean_url] = len(url_deduped)
            url_deduped.append(offer)

    # ── Phase 2 : Dédup fuzzy par buckets de titre ──
    buckets: dict[str, list[int]] = defaultdict(list)
    unique: list[JobOffer] = []

    for offer in url_deduped:
        key = _bucket_key(offer.title)
        is_dup = False

        # Chercher dans le même bucket
        if key in buckets:
            for idx in buckets[key]:
                if _is_duplicate(offer, unique[idx]):
                    unique[idx] = _best_offer(unique[idx], offer)
                    is_dup = True
                    break

        if not is_dup:
            idx = len(unique)
            unique.append(offer)
            buckets[key].append(idx)

    removed = original_count - len(unique)
    if removed > 0:
        console.print(
            f"\n[dim]🔄 Déduplication : {original_count} → {len(unique)} "
            f"([red]-{removed}[/red] doublons supprimés)[/dim]"
        )
    else:
        console.print(f"\n[dim]🔄 Aucun doublon détecté parmi {len(unique)} offres[/dim]")

    return unique
