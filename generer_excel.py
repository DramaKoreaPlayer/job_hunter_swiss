#!/usr/bin/env python3
"""Score les offres du JSON et génère un Excel trié par pertinence."""

import json
import sys
import os

# Ajouter le chemin du projet
sys.path.insert(0, "/Users/gazmendgashi/Documents/Offres d'emploi/job_hunter")

import config
from scrapers.base import JobOffer
from ai.analyzer import _keyword_score, _is_disqualified
from utils.exporter import export_to_excel

# Charger le JSON
json_path = "/Users/gazmendgashi/Documents/Offres d'emploi/job_hunter/results/offres_2026-02-20.json"
with open(json_path, "r") as f:
    data = json.load(f)

raw_offers = data.get("offers", data.get("offres", []))
print(f"📄 {len(raw_offers)} offres chargées depuis le JSON")

# Convertir en objets JobOffer
offers = []
for o in raw_offers:
    offers.append(JobOffer(
        title=o.get("title", ""),
        company=o.get("company", ""),
        location=o.get("location", ""),
        url=o.get("url", ""),
        source=o.get("source", ""),
        description=o.get("description", ""),
        work_rate=o.get("work_rate", ""),
        contract_type=o.get("contract_type", ""),
        date_posted=o.get("date_posted", ""),
    ))

# Filtrer les offres hors profil
before = len(offers)
offers = [o for o in offers if not _is_disqualified(o)]
print(f"🗑  {before - len(offers)} offres hors profil éliminées")
print(f"✅ {len(offers)} offres à scorer")

# Scorer chaque offre
for offer in offers:
    result = _keyword_score(offer)
    offer.relevance_score = result["relevance_score"]
    offer.success_probability = result["success_probability"]
    offer.ai_summary = result["summary"]
    offer.ai_keywords = result["keywords"]

# Trier par pertinence
offers.sort(key=lambda x: (x.relevance_score, x.success_probability), reverse=True)

# Exporter
filepath = export_to_excel(offers, config.SEARCH_QUERIES)
print(f"\n📊 Excel généré : {filepath}")
print(f"   Top 10 :")
for i, o in enumerate(offers[:10], 1):
    print(f"   {i}. [{o.relevance_score}/100] {o.title[:60]} — {o.location[:20]}")
