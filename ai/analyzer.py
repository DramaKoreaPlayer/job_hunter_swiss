"""Analyse IA des offres d'emploi — scoring batch intelligent + filtrage."""

from __future__ import annotations

import json
import re
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

import config
from scrapers.base import JobOffer

console = Console()


# ═══════════════════════════════════════════════════════
# FILTRAGE INTELLIGENT — Éliminer les postes inaccessibles
# ═══════════════════════════════════════════════════════
def _is_disqualified(offer: JobOffer) -> bool:
    """Vérifie si l'offre est clairement hors profil."""
    title_low = offer.title.lower()

    for keyword in config.DISQUALIFY_KEYWORDS:
        if keyword in title_low:
            return True
    return False


# ═══════════════════════════════════════════════════════
# SCORING PAR MOTS-CLÉS (amélioré et plus intelligent)
# ═══════════════════════════════════════════════════════
def _keyword_score(offer: JobOffer) -> dict:
    """Scoring intelligent par mots-clés — adapté au profil actif."""
    title = offer.title.lower()
    text = f"{title} {offer.description} {offer.company} {offer.location}".lower()

    # ═══════════ SCORING TITRE (le plus important) ═══════════
    title_score = 0
    title_matched = []

    # Tier 1 — Jobs parfaitement accessibles (forte pondération)
    tier1 = {
        "étudiant": 25, "student": 25, "job étudiant": 30,
        "caissier": 20, "caissière": 20,
        "vendeur": 18, "vendeuse": 18,
        "employé de vente": 20, "conseiller vente": 18,
        "assistant administratif": 25, "assistante administrative": 25,
        "aide administrative": 22,
        "employé de commerce": 20, "employée de commerce": 20,
        "réceptionniste": 20,
        "accueil": 15,
        "secrétaire": 18, "secrétariat": 18,
        "saisie de données": 18, "data entry": 18,
        "service client": 20, "service clientèle": 20,
        "conseiller clientèle": 18,
        "call center": 15, "centre d'appels": 15,
        "community manager": 25,
        "social media": 25, "réseaux sociaux": 25,
        "monteur vidéo": 25, "video editor": 25,
        "marketing digital": 22, "digital marketing": 22,
        "assistant marketing": 22,
        "stage": 20, "stagiaire": 20,
        "temporaire": 12, "intérim": 12,
    }

    for keyword, points in tier1.items():
        if keyword in title:
            title_score += points
            title_matched.append(keyword)

    # Tier 2 — Mots qui renforcent la pertinence dans le texte complet
    tier2 = {
        "trilingue": 12, "bilingue": 10,
        "français": 5, "allemand": 8, "anglais": 5,
        "lausanne": 8, "renens": 10, "crissier": 8, "prilly": 8,
        "chavannes": 8, "ecublens": 8, "bussigny": 8, "morges": 6,
        "excel": 4, "office": 4, "microsoft": 4,
        "tiktok": 12, "youtube": 12, "instagram": 10,
        "contenu": 8, "content": 8,
        "communication": 6,
        "logistique": 8, "manutention": 8,
        "coop": 10, "migros": 10, "denner": 10, "lidl": 10, "aldi": 10,
        "assurance": 8, "banque": 8, "poste": 8,
        "débutant": 12, "sans expérience": 15,
    }

    for keyword, points in tier2.items():
        if keyword in text:
            title_score += points
            title_matched.append(keyword)

    # ═══════════ PÉNALITÉS ═══════════
    penalties = {
        "senior": -25, "directeur": -30, "director": -30,
        "5 ans d'expérience": -25, "10 ans": -30,
        "expérience requise": -15, "expérience confirmée": -20,
        "chef de projet": -15, "cadre supérieur": -20,
        "phd": -25, "doctorat": -25,
        "cfc requis": -10, "diplôme hes": -10,
        "responsable": -8,
    }

    for keyword, points in penalties.items():
        if keyword in text:
            title_score += points

    # ═══════════ BONUS TAUX D'ACTIVITÉ ═══════════
    if offer.work_rate:
        rate = offer.work_rate.lower()
        if any(r in rate for r in ["40%", "50%", "60%", "30%"]):
            title_score += 8
        elif "100%" in rate:
            title_score += 3

    # ═══════════ CALCUL FINAL ═══════════
    base = 30
    relevance = max(0, min(100, base + title_score))

    if relevance >= 70:
        success = int(relevance * 0.75)
    elif relevance >= 50:
        success = int(relevance * 0.60)
    else:
        success = int(relevance * 0.45)

    success = max(0, min(100, success))

    # Résumé auto
    summary_parts = []
    if any(k in title_matched for k in ("étudiant", "student", "job étudiant")):
        summary_parts.append("Job étudiant")
    if any(k in title_matched for k in ("caissier", "caissière", "vendeur", "vendeuse", "employé de vente")):
        summary_parts.append("Vente/caisse")
    if any(k in title_matched for k in ("assistant administratif", "aide administrative", "secrétaire")):
        summary_parts.append("Admin")
    if any(k in title_matched for k in ("social media", "community manager", "tiktok", "youtube")):
        summary_parts.append("Digital/Social")
    if any(k in title_matched for k in ("stage", "stagiaire")):
        summary_parts.append("Stage")
    if any(k in title_matched for k in ("service client", "conseiller clientèle", "call center")):
        summary_parts.append("Service client")

    cat = " + ".join(summary_parts) if summary_parts else "Divers"
    company = offer.company.split("\n")[0][:30] if offer.company else "N/C"

    return {
        "relevance_score": relevance,
        "success_probability": success,
        "summary": f"[{cat}] {offer.title[:50]} — {company}",
        "keywords": title_matched[:5],
    }


# ═══════════════════════════════════════════════════════
# PROMPT OLLAMA — MODE BATCH
# ═══════════════════════════════════════════════════════
def _build_batch_prompt(offers: list[JobOffer], profile: dict) -> str:
    """Construit un prompt pour scorer plusieurs offres en un seul appel."""
    offers_text = "\n".join(
        f'[{i}] Titre: "{o.title}" | Entreprise: "{o.company}" | '
        f'Lieu: "{o.location}" | Taux: "{o.work_rate or "N/S"}" | '
        f'Description: "{o.description[:200] if o.description else "N/D"}"'
        for i, o in enumerate(offers)
    )

    return f"""Tu es un expert en recrutement en Suisse romande. Évalue ces {len(offers)} offres pour le candidat ci-dessous.

## Candidat
- **Nom** : {profile['name']}
- **Formation** : {profile['education']}
- **Langues** : {', '.join(profile['languages'])}
- **Compétences** : {', '.join(profile['skills'])}
- **Expérience** : {profile['experience_summary']}
- **Lieu** : {profile['location']}
- **Disponibilité** : {profile.get('availability', '100%')}

## Offres à évaluer
{offers_text}

## Instructions
Réponds UNIQUEMENT avec un JSON array valide contenant un objet par offre, dans l'ordre :
[
  {{"index": 0, "relevance_score": <0-100>, "success_probability": <0-100>, "summary": "<résumé 1 phrase>", "keywords": ["mot1", "mot2"]}},
  ...
]

Critères :
- Le candidat est disponible quasi à 100% (très peu de cours)
- Il cherche tout : admin, vente, caisse, service client, digital, assurance, intérim
- PÉNALISE les postes qui demandent un diplôme spécifique (infirmier, ingénieur, CFC technique)
- FAVORISE les postes accessibles sans expérience ou avec formation sur place"""


def _build_single_prompt(offer: JobOffer, profile: dict) -> str:
    """Fallback : prompt pour une seule offre."""
    return f"""Tu es un expert en recrutement en Suisse romande. Évalue cette offre pour le candidat ci-dessous.

## Candidat
- **Nom** : {profile['name']}
- **Formation** : {profile['education']}
- **Langues** : {', '.join(profile['languages'])}
- **Compétences** : {', '.join(profile['skills'])}
- **Expérience** : {profile['experience_summary']}
- **Lieu** : {profile['location']}
- **Disponibilité** : {profile.get('availability', '100%')}

## Offre
- **Titre** : {offer.title}
- **Entreprise** : {offer.company}
- **Lieu** : {offer.location}
- **Taux** : {offer.work_rate or 'Non spécifié'}
- **Description** : {offer.description[:500] if offer.description else 'Non disponible'}

## Instructions
Réponds UNIQUEMENT avec un JSON valide :
{{
  "relevance_score": <0-100>,
  "success_probability": <0-100>,
  "summary": "<résumé 1 phrase>",
  "keywords": ["mot1", "mot2", "mot3"]
}}

Critères importants :
- Le candidat est disponible quasi à 100% (très peu de cours)
- Il cherche tout : admin, vente, caisse, service client, digital, assurance, intérim
- PÉNALISE les postes qui demandent un diplôme spécifique (infirmier, ingénieur, CFC technique)
- FAVORISE les postes accessibles sans expérience ou avec formation sur place"""


def _parse_ai_response(response_text: str) -> Optional[dict]:
    """Parse une réponse JSON unique."""
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'\{[^{}]*\}', response_text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    scores = {}
    relevance = re.search(r'"?relevance_score"?\s*:\s*(\d+)', response_text)
    success = re.search(r'"?success_probability"?\s*:\s*(\d+)', response_text)
    summary = re.search(r'"?summary"?\s*:\s*"([^"]*)"', response_text)

    if relevance:
        scores["relevance_score"] = int(relevance.group(1))
    if success:
        scores["success_probability"] = int(success.group(1))
    if summary:
        scores["summary"] = summary.group(1)

    return scores if scores else None


def _parse_batch_response(response_text: str, count: int) -> Optional[list[dict]]:
    """Parse une réponse JSON array (batch)."""
    # Essayer de parser directement
    try:
        result = json.loads(response_text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Chercher un array JSON dans le texte
    array_match = re.search(r'\[[\s\S]*\]', response_text)
    if array_match:
        try:
            result = json.loads(array_match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Chercher des objets JSON individuels
    objects = re.findall(r'\{[^{}]*\}', response_text)
    if objects:
        parsed = []
        for obj_str in objects:
            try:
                parsed.append(json.loads(obj_str))
            except json.JSONDecodeError:
                continue
        if parsed:
            return parsed

    return None


def _apply_score(offer: JobOffer, result: dict):
    """Applique les scores d'un résultat à une offre."""
    offer.relevance_score = min(100, max(0, result.get("relevance_score", 0)))
    offer.success_probability = min(100, max(0, result.get("success_probability", 0)))
    offer.ai_summary = result.get("summary", "")
    offer.ai_keywords = result.get("keywords", [])


def _apply_keyword_fallback(offer: JobOffer):
    """Applique le scoring par mots-clés en fallback."""
    result = _keyword_score(offer)
    offer.relevance_score = result["relevance_score"]
    offer.success_probability = result["success_probability"]
    offer.ai_summary = result["summary"]
    offer.ai_keywords = result["keywords"]


# ═══════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ═══════════════════════════════════════════════════════
async def analyze_offers(
    offers: list[JobOffer],
    use_ollama: bool = True,
) -> list[JobOffer]:
    """Analyse toutes les offres : filtrage + scoring batch."""

    if not offers:
        return offers

    # ── ÉTAPE 1 : Filtrer les offres clairement hors profil ──
    before = len(offers)
    offers = [o for o in offers if not _is_disqualified(o)]
    filtered_out = before - len(offers)
    if filtered_out:
        console.print(
            f"\n[dim]🗑 {filtered_out} offres hors profil éliminées "
            f"(infirmier, monteur électricien, etc.)[/dim]"
        )

    # ── ÉTAPE 2 : Scoring ──
    ollama_available = False

    if use_ollama and config.OLLAMA_ENABLED:
        try:
            import ollama as ollama_lib
            ollama_lib.list()
            ollama_available = True
            console.print(
                f"\n[green]🤖 Ollama connecté[/green] — modèle : [bold]{config.OLLAMA_MODEL}[/bold]"
                f" — batch de {config.OLLAMA_BATCH_SIZE}"
            )
        except Exception as e:
            console.print(f"\n[yellow]⚠ Ollama indisponible ({e})[/yellow] → scoring par mots-clés")

    total = len(offers)
    batch_size = config.OLLAMA_BATCH_SIZE

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console,
    ) as progress:
        task = progress.add_task("🧠 Analyse des offres...", total=total)

        if ollama_available:
            import ollama as ollama_lib

            # ── MODE BATCH : grouper les offres par paquets ──
            for i in range(0, total, batch_size):
                batch = offers[i:i + batch_size]

                try:
                    if len(batch) > 1:
                        # Batch prompt
                        prompt = _build_batch_prompt(batch, config.CANDIDATE_PROFILE)
                        response = ollama_lib.chat(
                            model=config.OLLAMA_MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            options={"temperature": 0.3},
                        )
                        results = _parse_batch_response(
                            response["message"]["content"], len(batch)
                        )

                        if results and len(results) >= len(batch):
                            for offer, result in zip(batch, results):
                                _apply_score(offer, result)
                        elif results:
                            # Résultats partiels — appliquer ce qu'on a
                            for j, result in enumerate(results):
                                if j < len(batch):
                                    idx = result.get("index", j)
                                    if 0 <= idx < len(batch):
                                        _apply_score(batch[idx], result)
                                    else:
                                        _apply_score(batch[j], result)
                            # Fallback pour ceux sans résultat
                            for offer in batch:
                                if offer.relevance_score == 0 and offer.ai_summary == "":
                                    _apply_keyword_fallback(offer)
                        else:
                            # Parse échoué — fallback mots-clés pour tout le batch
                            for offer in batch:
                                _apply_keyword_fallback(offer)
                    else:
                        # Une seule offre — prompt simple
                        offer = batch[0]
                        prompt = _build_single_prompt(offer, config.CANDIDATE_PROFILE)
                        response = ollama_lib.chat(
                            model=config.OLLAMA_MODEL,
                            messages=[{"role": "user", "content": prompt}],
                            options={"temperature": 0.3},
                        )
                        result = _parse_ai_response(response["message"]["content"])
                        if result:
                            _apply_score(offer, result)
                        else:
                            _apply_keyword_fallback(offer)

                except Exception as e:
                    console.print(f"  [yellow]⚠ Batch {i//batch_size + 1} erreur: {e}[/yellow]")
                    for offer in batch:
                        _apply_keyword_fallback(offer)

                progress.update(task, advance=len(batch))
        else:
            # ── MODE MOTS-CLÉS ──
            for offer in offers:
                _apply_keyword_fallback(offer)
                progress.update(task, advance=1)

    # Trier par pertinence décroissante
    offers.sort(key=lambda x: (x.relevance_score, x.success_probability), reverse=True)

    return offers
