"""Configuration centrale pour le Job Hunter."""

import os

# ═══════════════════════════════════════════════════════
# PROFILS — Chaque personne a son propre profil
# ═══════════════════════════════════════════════════════
PROFILES = {
    "user": {
        "candidate": {
            "name": "YOUR_NAME",
            "education": "YOUR_EDUCATION",
            "languages": ["Français", "Anglais (C1)", "Allemand (B2)"],
            "skills": [
                "Stratégie digitale",
                "Analyse de données",
                "Communication / Marketing",
                "Excel, R, Word, Suite Office",
                "Gestion de réseaux sociaux",
            ],
            "experience_summary": (
                "Décrivez ici votre expérience professionnelle. "
                "Adaptez ce résumé à votre profil."
            ),
            "location": "Lausanne VD",
            "availability": "100%",
        },
        "queries": [
            # === ADMIN / BUREAU ===
            "assistant administratif",
            "secrétariat",
            "employé de commerce",
            "aide administrative",
            "réceptionniste",
            "saisie de données",
            "employé de bureau",
            # === VENTE / COMMERCE ===
            "caissier",
            "vendeur",
            "conseiller vente",
            "employé de vente",
            # === SUPERMARCHÉ / LOGISTIQUE ===
            "Coop emploi",
            "Migros emploi",
            "magasinier",
            "manutentionnaire",
            "préparateur de commandes",
            # === ASSURANCE / BANQUE / FINANCE ===
            "employé assurance",
            "conseiller clientèle",
            "service client",
            "call center Lausanne",
            # === DIGITAL / CRÉATIF ===
            "community manager",
            "social media",
            "monteur vidéo",
            "assistant marketing",
            # === JOBS ÉTUDIANTS / STAGES ===
            "emploi étudiant",
            "stage Lausanne",
            "job étudiant Lausanne",
            "emploi temporaire",
            # === HÔTELLERIE / ACCUEIL ===
            "accueil",
            "hôte accueil",
        ],
        "location": "Lausanne",
        "region": "Vaud",
        "telegram_chat_id_env": "TELEGRAM_CHAT_ID",
    },

    # --- EXEMPLE DE PROFIL SUPPLÉMENTAIRE ---
    # "user2": {
    #     "candidate": {
    #         "name": "Cousine",
    #         "education": "Recherche apprentissage / emploi",
    #         "languages": ["Français (natif)"],
    #         "skills": [
    #             "Vente",
    #             "Service client",
    #             "Accueil",
    #         ],
    #         "experience_summary": "Recherche un apprentissage d'assistante dentaire ou un emploi dans la vente / caisse.",
    #         "location": "Yverdon-les-Bains VD",
    #         "availability": "100%",
    #     },
    #     "queries": [
    #         # === APPRENTISSAGE DENTAIRE ===
    #         "apprentissage assistante dentaire",
    #         "assistante dentaire",
    #         "apprentissage dentaire",
    #         "assistant médical apprentissage",
    #         "apprentissage cabinet dentaire",
    #         "assistante médicale",
    #         # === VENTE / CAISSE ===
    #         "caissière",
    #         "vendeuse",
    #         "vendeur",
    #         "employée de vente",
    #         "conseillère vente",
    #         # === SUPERMARCHÉ ===
    #         "Coop emploi",
    #         "Migros emploi",
    #         "Lidl emploi",
    #         "Aldi emploi",
    #         # === ACCUEIL / SERVICE ===
    #         "réceptionniste",
    #         "accueil",
    #         "service client",
    #         # === APPRENTISSAGES GÉNÉRAUX ===
    #         "apprentissage commerce",
    #         "apprentissage vente",
    #         "emploi temporaire",
    #     ],
    #     "location": "Yverdon-les-Bains",
    #     "region": "Vaud",
    #     "telegram_chat_id_env": "TELEGRAM_CHAT_ID_COUSIN",
    # },
}

# ═══════════════════════════════════════════════════════
# PROFIL ACTIF — sélectionné via --profile ou env var
# ═══════════════════════════════════════════════════════
ACTIVE_PROFILE_NAME = os.environ.get("JOB_HUNTER_PROFILE", "user")
ACTIVE_PROFILE = PROFILES.get(ACTIVE_PROFILE_NAME, PROFILES["user"])

CANDIDATE_PROFILE = ACTIVE_PROFILE["candidate"]
SEARCH_QUERIES = ACTIVE_PROFILE["queries"]
DEFAULT_LOCATION = ACTIVE_PROFILE["location"]
DEFAULT_REGION = ACTIVE_PROFILE["region"]
SEARCH_RADIUS_KM = 30

# Mots-clés qui disqualifient un poste (pas accessible)
DISQUALIFY_KEYWORDS = [
    "infirmier", "infirmière", "médecin", "chirurgie", "soins",
    "monteur électricien", "monteur sanitaire", "monteur chauffage",
    "monteur ventilation", "plombier", "serrurier", "maçon",
    "conducteur de travaux", "installateur", "soudeur",
    "professeur hes", "postdoc", "doctorant",
    "ingénieur", "architecte", "pharmacien",
    "femme de chambre", "horticulteur",
    "éducateur social", "travailleur social",
    "concierge technique",
]

# ═══════════════════════════════════════════════════════
# SCRAPING
# ═══════════════════════════════════════════════════════
MAX_PAGES_PER_SITE = 3              # pages par site par recherche
REQUEST_DELAY_MIN = 1.0             # réduit (était 1.5)
REQUEST_DELAY_MAX = 3.0             # réduit (était 4.0)
BROWSER_TIMEOUT_MS = 30000
MAX_CONCURRENT_SCRAPERS = 3         # scrapers en parallèle (utilisé maintenant!)
SCRAPER_GLOBAL_TIMEOUT = 120        # timeout global par scraper+query (secondes)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# ═══════════════════════════════════════════════════════
# IA (Ollama)
# ═══════════════════════════════════════════════════════
OLLAMA_MODEL = "gemma3:12b"
OLLAMA_ENABLED = True
OLLAMA_TIMEOUT = 60
OLLAMA_BATCH_SIZE = 5               # offres par prompt (batch scoring)

# ═══════════════════════════════════════════════════════
# CACHE & MODE INCRÉMENTAL
# ═══════════════════════════════════════════════════════
CACHE_ENABLED = True
CACHE_DB_PATH = "results/job_cache.db"
CACHE_EXPIRY_DAYS = 14              # offres plus vieilles = ignorées

# ═══════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════
RESULTS_DIR = "results"
EXCEL_FILENAME_TEMPLATE = "recherche_{date}_{time}.xlsx"

# ═══════════════════════════════════════════════════════
# SITES ACTIVÉS
# ═══════════════════════════════════════════════════════
ENABLED_SITES = [
    "jobup",
    "jobs_ch",
    "indeed",
    "manpower",
    "adecco",
    "randstad",
    "linkedin",
    "michael_page",
    "jobscout24",
    "coop",
    "heccareer",
]
