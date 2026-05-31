"""Export des résultats vers JSON pour analyse externe — inclut les scores IA."""

from __future__ import annotations

import json
import os
from datetime import date

from rich.console import Console

import config
from scrapers.base import JobOffer

console = Console()


def export_to_json(offers: list[JobOffer], search_queries: list[str]) -> str:
    """Exporte les offres vers un fichier JSON lisible, avec scores IA.

    Returns:
        Chemin absolu du fichier créé.
    """
    results_dir = os.path.join(os.path.dirname(__file__), "..", config.RESULTS_DIR)
    os.makedirs(results_dir, exist_ok=True)

    filename = f"offres_{date.today().strftime('%Y-%m-%d')}.json"
    filepath = os.path.join(results_dir, filename)

    data = {
        "date": date.today().isoformat(),
        "location": config.DEFAULT_LOCATION,
        "queries": search_queries,
        "total_offers": len(offers),
        "candidate": config.CANDIDATE_PROFILE,
        "offers": [
            {
                "title": o.title,
                "company": o.company,
                "location": o.location,
                "url": o.url,
                "source": o.source,
                "description": o.description,
                "work_rate": o.work_rate,
                "contract_type": o.contract_type,
                "date_posted": o.date_posted,
                # Scores IA maintenant inclus!
                "relevance_score": o.relevance_score,
                "success_probability": o.success_probability,
                "ai_summary": o.ai_summary,
                "ai_keywords": o.ai_keywords,
            }
            for o in offers
        ],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    abs_path = os.path.abspath(filepath)
    console.print(f"[green]📄 JSON sauvegardé :[/green] [bold]{abs_path}[/bold]")
    return abs_path
