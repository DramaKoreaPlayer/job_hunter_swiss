"""Notifier Telegram — envoie les meilleures offres directement sur ton téléphone."""

from __future__ import annotations

import os
import httpx
from scrapers.base import JobOffer

# Clés lues depuis les variables d'environnement (GitHub Secrets en prod)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


async def send_telegram_message(text: str, chat_id_override: str = "") -> bool:
    """Envoie un simple message texte sur Telegram."""
    token = TELEGRAM_BOT_TOKEN
    chat_id = chat_id_override or TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            return resp.status_code == 200
    except Exception:
        return False


def _escape_md(text: str) -> str:
    """Échappe les caractères spéciaux pour Telegram MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    for char in special:
        text = text.replace(char, f"\\{char}")
    return text


async def send_telegram_alert(
    offers: list[JobOffer],
    max_offers: int = 15,
    chat_id_override: str = "",
) -> bool:
    """Envoie un résumé des meilleures offres via Telegram.

    Returns:
        True si le message a été envoyé, False sinon.
    """
    token = TELEGRAM_BOT_TOKEN
    chat_id = chat_id_override or TELEGRAM_CHAT_ID

    if not token or not chat_id:
        return False

    # Trier par score de pertinence (desc)
    sorted_offers = sorted(offers, key=lambda o: o.relevance_score, reverse=True)
    top = sorted_offers[:max_offers]

    if not top:
        return False

    # ── Construire le message ──
    lines = [f"🔍 *Job Hunter — {len(offers)} nouvelles offres\\!*\n"]

    for i, offer in enumerate(top, 1):
        score = offer.relevance_score
        if score >= 75:
            emoji = "🟢"
        elif score >= 50:
            emoji = "🟡"
        else:
            emoji = "⚪"

        title = _escape_md(offer.title[:50])
        company = _escape_md(offer.company[:30]) if offer.company else "—"
        location = _escape_md(offer.location[:25]) if offer.location else "—"
        url = offer.url
        work_rate = _escape_md(offer.work_rate) if offer.work_rate else ""

        rate_line = f" ⏰ {work_rate}" if work_rate else ""

        lines.append(
            f"{emoji} *{i}\\.* [{title}]({url})\n"
            f"   🏢 {company} · 📍 {location}{rate_line} · 📊 {score}/100"
        )

    if len(offers) > max_offers:
        rest = len(offers) - max_offers
        lines.append(f"\n\\.\\.\\.et {rest} autres offres dans l'Excel")

    message = "\n\n".join(lines)

    # ── Envoyer via l'API Telegram ──
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            })

            if resp.status_code == 200:
                return True
            else:
                # Fallback : envoyer en texte brut si le markdown échoue
                plain = f"🔍 Job Hunter — {len(offers)} nouvelles offres!\n\n"
                for i, offer in enumerate(top, 1):
                    plain += (
                        f"{i}. {offer.title[:50]}\n"
                        f"   {offer.company or '—'} · {offer.location or '—'} · "
                        f"Score: {offer.relevance_score}/100\n"
                        f"   {offer.url}\n\n"
                    )
                await client.post(api_url, json={
                    "chat_id": chat_id,
                    "text": plain,
                    "disable_web_page_preview": True,
                })
                return True

    except Exception:
        return False
