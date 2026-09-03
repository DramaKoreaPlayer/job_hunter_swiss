#!/usr/bin/env python3
"""
🔍 Job Hunter — Agent IA de recherche d'emploi en Suisse romande
================================================================

Usage:
    python main.py                          # Recherche complète avec config par défaut
    python main.py --queries "étudiant"     # Recherche spécifique
    python main.py --sites jobup,indeed     # Sites spécifiques
    python main.py --max-pages 2            # Limiter les pages
    python main.py --no-ai                  # Sans scoring Ollama
    python main.py --quick                  # Mode rapide (1 page, 7 sites)
    python main.py --incremental            # Ne montre que les nouvelles offres
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import config
from scrapers.base import BrowserManager, JobOffer

console = Console()


# ═══════════════════════════════════════════════════════
# REGISTRY DES SCRAPERS
# ═══════════════════════════════════════════════════════
def _get_scraper(name: str):
    """Importe et retourne un scraper par nom."""
    scrapers_map = {
        "jobup": ("scrapers.jobup", "JobupScraper"),
        "jobs_ch": ("scrapers.jobs_ch", "JobsChScraper"),
        "indeed": ("scrapers.indeed", "IndeedScraper"),
        "manpower": ("scrapers.manpower", "ManpowerScraper"),
        "adecco": ("scrapers.adecco", "AdeccoScraper"),
        "randstad": ("scrapers.randstad", "RandstadScraper"),
        "linkedin": ("scrapers.linkedin", "LinkedinScraper"),
        "michael_page": ("scrapers.michael_page", "MichaelPageScraper"),
        "jobscout24": ("scrapers.jobscout24", "JobScout24Scraper"),
        "coop": ("scrapers.coop", "CoopScraper"),
        "heccareer": ("scrapers.heccareer", "HecCareerScraper"),
    }

    if name not in scrapers_map:
        console.print(f"[red]Scraper inconnu : {name}[/red]")
        return None

    module_path, class_name = scrapers_map[name]
    try:
        import importlib
        module = importlib.import_module(module_path)
        scraper_class = getattr(module, class_name)
        return scraper_class()
    except Exception as e:
        console.print(f"[red]Erreur lors du chargement de {name}: {e}[/red]")
        return None


# ═══════════════════════════════════════════════════════
# RECHERCHE PARALLÈLE
# ═══════════════════════════════════════════════════════
async def run_search(
    queries: list[str],
    sites: list[str],
    location: str,
    max_pages: int,
) -> list[JobOffer]:
    """Lance la recherche en parallèle sur tous les sites et toutes les requêtes."""

    all_offers: list[JobOffer] = []

    # Initialiser les scrapers
    scrapers = []
    for site_name in sites:
        scraper = _get_scraper(site_name)
        if scraper:
            scrapers.append(scraper)

    if not scrapers:
        console.print("[red]Aucun scraper disponible ![/red]")
        return []

    total_searches = len(scrapers) * len(queries)
    console.print(
        f"\n[bold]🚀 Lancement : {len(scrapers)} sites × {len(queries)} recherches "
        f"= {total_searches} scans[/bold]"
    )
    console.print(
        f"[dim]⚡ Mode parallèle — max {config.MAX_CONCURRENT_SCRAPERS} scrapers simultanés[/dim]\n"
    )

    # ── Semaphore pour limiter les scrapers concurrents ──
    sem = asyncio.Semaphore(config.MAX_CONCURRENT_SCRAPERS)
    results_lock = asyncio.Lock()

    async def _run_one(scraper, query: str) -> None:
        """Exécute un scraper pour une requête avec timeout et semaphore."""
        async with sem:
            try:
                results = await asyncio.wait_for(
                    scraper.search(query, location, max_pages),
                    timeout=config.SCRAPER_GLOBAL_TIMEOUT,
                )
                if results:
                    async with results_lock:
                        all_offers.extend(results)
            except asyncio.TimeoutError:
                console.print(
                    f"  [yellow]⏱[/yellow] [bold]{scraper.name}[/bold] — "
                    f"timeout pour « {query} »"
                )
            except Exception as e:
                console.print(f"  [red]✗ {scraper.name} — Erreur: {e}[/red]")

    # ── Lancer toutes les tâches en parallèle ──
    # Scraper sans query (ex: HEC Career) → une seule fois
    # Scraper avec query → pour chaque query
    tasks = []
    for scraper in scrapers:
        if getattr(scraper, "supports_query", True) is False:
            # Une seule fois, sans query significative
            tasks.append(_run_one(scraper, ""))
        else:
            for query in queries:
                tasks.append(_run_one(scraper, query))
    await asyncio.gather(*tasks)

    return all_offers


# ═══════════════════════════════════════════════════════
# AFFICHAGE RÉSUMÉ
# ═══════════════════════════════════════════════════════
def show_summary(offers: list[JobOffer]):
    """Affiche un résumé des résultats dans le terminal."""
    if not offers:
        console.print("\n[yellow]Aucune offre trouvée.[/yellow]")
        return

    # Top 15 offres
    top = offers[:15]

    table = Table(
        title="🏆 Top 15 des offres les plus pertinentes",
        show_lines=True,
        border_style="dim",
    )
    table.add_column("Score", style="bold", justify="center", width=8)
    table.add_column("Prob.", justify="center", width=7)
    table.add_column("Poste", style="cyan", max_width=35)
    table.add_column("Entreprise", max_width=25)
    table.add_column("Lieu", max_width=20)
    table.add_column("Source", style="dim", max_width=15)

    for offer in top:
        # Couleur du score
        if offer.relevance_score >= 75:
            score_style = "green bold"
        elif offer.relevance_score >= 50:
            score_style = "yellow"
        else:
            score_style = "dim"

        # Couleur probabilité
        if offer.success_probability >= 70:
            prob_style = "green"
        elif offer.success_probability >= 45:
            prob_style = "yellow"
        else:
            prob_style = "red"

        table.add_row(
            Text(f"{offer.relevance_score}/100", style=score_style),
            Text(f"{offer.success_probability}%", style=prob_style),
            offer.title[:35],
            offer.company[:25] or "—",
            offer.location[:20] or "—",
            offer.source.split(" + ")[0][:15],
        )

    console.print()
    console.print(table)

    # Stats rapides
    high = sum(1 for o in offers if o.relevance_score >= 75)
    mid = sum(1 for o in offers if 50 <= o.relevance_score < 75)
    low = sum(1 for o in offers if o.relevance_score < 50)
    avg_prob = sum(o.success_probability for o in offers) / len(offers) if offers else 0

    stats = Panel(
        f"[green]🟢 Haute pertinence : {high}[/green]  |  "
        f"[yellow]🟡 Moyenne : {mid}[/yellow]  |  "
        f"[dim]⚪ Basse : {low}[/dim]\n"
        f"📊 Probabilité moyenne de réussite : [bold]{avg_prob:.0f}%[/bold]",
        title="📈 Statistiques",
        border_style="blue",
    )
    console.print(stats)


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
async def main():
    parser = argparse.ArgumentParser(
        description="🔍 Job Hunter — Agent IA de recherche d'emploi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--queries", "-q",
        type=str,
        help="Termes de recherche (séparés par des virgules). Par défaut: config.py",
    )
    parser.add_argument(
        "--sites", "-s",
        type=str,
        help=f"Sites à scraper (séparés par virgules). Dispo: {', '.join(config.ENABLED_SITES)}",
    )
    parser.add_argument(
        "--location", "-l",
        type=str,
        default=config.DEFAULT_LOCATION,
        help=f"Lieu de recherche (défaut: {config.DEFAULT_LOCATION})",
    )
    parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=config.MAX_PAGES_PER_SITE,
        help=f"Pages max par site (défaut: {config.MAX_PAGES_PER_SITE})",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Désactiver le scoring Ollama (utilise le scoring par mots-clés)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Mode rapide : 1 page, 7 sites principaux",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Mode incrémental : ne montre que les nouvelles offres (ignore le cache)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Envoyer les résultats sur Telegram",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help=f"Profil à utiliser ({', '.join(config.PROFILES.keys())}). Défaut: gazmend",
    )

    args = parser.parse_args()

    # ═══════════════════════════════
    # Profil actif
    # ═══════════════════════════════
    if args.profile and args.profile in config.PROFILES:
        profile = config.PROFILES[args.profile]
        config.CANDIDATE_PROFILE = profile["candidate"]
        config.SEARCH_QUERIES = profile["queries"]
        config.DEFAULT_LOCATION = profile["location"]
        config.DEFAULT_REGION = profile["region"]
        config.ACTIVE_PROFILE = profile
        config.ACTIVE_PROFILE_NAME = args.profile
        # Mettre à jour la location si pas spécifiée manuellement
        if args.location == "Lausanne":  # valeur par défaut = pas changée par l'user
            args.location = profile["location"]

    # ═══════════════════════════════
    # Configuration
    # ═══════════════════════════════
    queries = (
        [q.strip() for q in args.queries.split(",")]
        if args.queries
        else config.SEARCH_QUERIES
    )

    if args.quick:
        sites = ["jobup", "indeed", "jobs_ch", "linkedin", "coop", "heccareer"]
        max_pages = 1
    else:
        sites = (
            [s.strip() for s in args.sites.split(",")]
            if args.sites
            else config.ENABLED_SITES
        )
        max_pages = args.max_pages

    use_ai = not args.no_ai

    # ═══════════════════════════════
    # Bannière
    # ═══════════════════════════════
    banner = Panel(
        f"[bold white]Candidat :[/bold white] {config.CANDIDATE_PROFILE['name']}\n"
        f"[bold white]Recherche :[/bold white] {', '.join(queries[:4])}{'...' if len(queries) > 4 else ''}\n"
        f"[bold white]Région :[/bold white] {args.location}\n"
        f"[bold white]Sites :[/bold white] {len(sites)} actifs\n"
        f"[bold white]Pages/site :[/bold white] {max_pages}\n"
        f"[bold white]IA Ollama :[/bold white] {'✅ Activée' if use_ai else '❌ Désactivée'}\n"
        f"[bold white]Mode :[/bold white] {'🔄 Incrémental' if args.incremental else '🔍 Complet'}\n"
        f"[bold white]Telegram :[/bold white] {'📱 Activé' if args.notify else '❌ Désactivé'}\n"
        f"[bold white]Parallélisme :[/bold white] ⚡ {config.MAX_CONCURRENT_SCRAPERS} scrapers simultanés",
        title="[bold blue]🔍 JOB HUNTER — Suisse Romande[/bold blue]",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(banner)

    # ═══════════════════════════════
    # Démarrer le BrowserManager
    # ═══════════════════════════════
    browser_mgr = await BrowserManager.get()
    await browser_mgr.start()

    try:
        # ═══════════════════════════════
        # Recherche
        # ═══════════════════════════════
        start_time = time.time()

        all_offers = await run_search(
            queries=queries,
            sites=sites,
            location=args.location,
            max_pages=max_pages,
        )

        scrape_time = time.time() - start_time
        console.print(
            f"\n[bold]📦 Total brut : {len(all_offers)} offres récoltées "
            f"en {scrape_time:.1f}s[/bold]"
        )

        # ═══════════════════════════════
        # Déduplication
        # ═══════════════════════════════
        from utils.dedup import deduplicate
        unique_offers = deduplicate(all_offers)

        # ═══════════════════════════════
        # Mode incrémental — filtrer les déjà vues
        # ═══════════════════════════════
        if args.incremental and config.CACHE_ENABLED:
            from utils.cache import JobCache
            cache = JobCache()
            before = len(unique_offers)
            unique_offers = cache.filter_new(unique_offers)
            cached = before - len(unique_offers)
            if cached:
                console.print(
                    f"[dim]🔄 Mode incrémental : {cached} offres déjà vues ignorées, "
                    f"{len(unique_offers)} nouvelles[/dim]"
                )

        # ═══════════════════════════════
        # Analyse IA
        # ═══════════════════════════════
        from ai.analyzer import analyze_offers
        analyzed_offers = await analyze_offers(unique_offers, use_ollama=use_ai)

        # ═══════════════════════════════
        # Sauvegarder dans le cache
        # ═══════════════════════════════
        if config.CACHE_ENABLED:
            from utils.cache import JobCache
            cache = JobCache()
            cache.save_offers(analyzed_offers)

        # ═══════════════════════════════
        # Export Excel
        # ═══════════════════════════════
        from utils.exporter import export_to_excel
        filepath = export_to_excel(analyzed_offers, queries)

        # ═══════════════════════════════
        # Export JSON (avec scores IA cette fois!)
        # ═══════════════════════════════
        from utils.json_exporter import export_to_json
        json_path = export_to_json(analyzed_offers, queries)

        # ═══════════════════════════════
        # Synchronisation vers l'app web Job Hunter
        # ═══════════════════════════════
        from utils.jobhunter_sync import sync_to_jobhunter
        synced = await sync_to_jobhunter(analyzed_offers)
        if synced >= 0:
            console.print(
                f"[bold green]🌐 Job Hunter : {synced} offres synchronisées vers l'app[/bold green]"
            )

        # ═══════════════════════════════
        # Notification Telegram
        # ═══════════════════════════════
        if args.notify:
            from utils.telegram_notifier import send_telegram_alert, send_telegram_message
            # Utiliser le chat_id du profil actif
            chat_id_env = config.ACTIVE_PROFILE.get("telegram_chat_id_env", "TELEGRAM_CHAT_ID")
            profile_chat_id = os.environ.get(chat_id_env, "")
            if analyzed_offers:
                sent = await send_telegram_alert(analyzed_offers, chat_id_override=profile_chat_id)
                if sent:
                    console.print(
                        f"[bold green]📱 Telegram ({config.ACTIVE_PROFILE_NAME}) : "
                        f"{min(15, len(analyzed_offers))} offres envoyées ![/bold green]"
                    )
                else:
                    console.print(
                        "[yellow]⚠ Telegram non configuré "
                        "(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants)[/yellow]"
                    )
            else:
                # Aucune nouvelle offre
                await send_telegram_message(
                    "🔍 Job Hunter — Scan terminé\n\n"
                    "Pas de nouvelles offres intéressantes pour l'instant.\n"
                    "Prochain scan dans 6h. ⏳",
                    chat_id_override=profile_chat_id,
                )
                console.print("[dim]📱 Telegram : pas de nouvelles offres signalées[/dim]")

        # ═══════════════════════════════
        # Résumé
        # ═══════════════════════════════
        elapsed = time.time() - start_time
        show_summary(analyzed_offers)

        console.print(
            f"\n[bold green]✅ Terminé en {elapsed / 60:.1f} minutes[/bold green] — "
            f"[bold]{len(analyzed_offers)}[/bold] offres uniques exportées\n"
        )

    finally:
        # ═══════════════════════════════
        # Fermer le navigateur proprement
        # ═══════════════════════════════
        await browser_mgr.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
