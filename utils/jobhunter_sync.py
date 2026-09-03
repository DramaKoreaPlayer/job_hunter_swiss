"""Synchronisation des offres vers l'app web Job Hunter.

Pousse les offres analysées vers l'endpoint d'ingestion de l'app
(`{JOBHUNTER_URL}/api/public/offers`) pour les retrouver dans l'interface
et générer CV + lettres de motivation.

Configuration via deux variables d'environnement (GitHub Secrets en prod) :

    JOBHUNTER_URL           ex : https://job-hunter.lovable.app
    JOBHUNTER_INGEST_TOKEN  jeton visible dans Réglages > Scraper de l'app

Si l'une des deux manque, la synchro est ignorée sans erreur.
"""

from __future__ import annotations

import os
import re

import httpx
from rich.console import Console

from scrapers.base import JobOffer

console = Console()

_ENDPOINT = "/api/public/offers"
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_TRAILING_ID_RE = re.compile(r"(\d{6,})/?$")


def _clean_url(url: str) -> str:
    return re.sub(r"[?#].*$", "", url or "").rstrip("/")


def _external_id(offer: JobOffer) -> str:
    """Identifiant stable pour l'upsert côté app (déduplication sur external_id)."""
    url = _clean_url(offer.url)
    if not url:
        return ""
    source = (offer.source or "").split(" + ")[0].strip().lower().replace(" ", "-") or "web"
    uuid_match = _UUID_RE.search(url)
    if uuid_match:
        return f"{source}-{uuid_match.group(0)}"[:200]
    id_match = _TRAILING_ID_RE.search(url)
    if id_match:
        return f"{source}-{id_match.group(1)}"[:200]
    return url[:200]


def _to_payload(offer: JobOffer) -> dict:
    return {
        "external_id": _external_id(offer),
        "title": offer.title,
        "company": offer.company,
        "location": offer.location,
        "work_rate": offer.work_rate,
        "source": offer.source,
        "url": offer.url,
        "score": int(offer.relevance_score or 0),
        "summary": offer.ai_summary or offer.description[:280],
        "description": offer.description,
    }


async def sync_to_jobhunter(offers: list[JobOffer]) -> int:
    """Envoie les offres à l'app Job Hunter.

    Returns:
        Nombre d'offres acceptées par l'app, 0 en cas d'échec,
        -1 si la synchro n'est pas configurée (env vars absentes).
    """
    base = os.environ.get("JOBHUNTER_URL", "").strip().rstrip("/")
    token = os.environ.get("JOBHUNTER_INGEST_TOKEN", "").strip()
    if not base or not token:
        return -1
    if not offers:
        return 0

    payload = {"offers": [_to_payload(offer) for offer in offers[:500]]}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{base}{_ENDPOINT}",
                headers={"x-ingest-token": token},
                json=payload,
            )
    except Exception as exc:  # noqa: BLE001 — on ne veut jamais casser le scan
        console.print(f"[yellow]⚠ Job Hunter sync : requête échouée ({exc})[/yellow]")
        return 0

    if resp.status_code == 200:
        try:
            return int(resp.json().get("received", len(payload["offers"])))
        except Exception:
            return len(payload["offers"])

    console.print(
        f"[yellow]⚠ Job Hunter sync : HTTP {resp.status_code} — {resp.text[:200]}[/yellow]"
    )
    return 0
