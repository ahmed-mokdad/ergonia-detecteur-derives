# Détecteur de dérives multifluides — Équipe Ergonia

Energ-IACK 2026 (Energ-IA Transition), défi 4 « Le détecteur de dérives ». Équipe Ergonia : Ahmed, Ibrahima, Aziz, Fahd, Cédric.

**But.** Repérer, parmi les courbes électricité, gaz, eau, chaleur à distance et photovoltaïque d'une commune, les dérives qui comptent, les dater, les chiffrer en kWh, CHF et CO₂, et les classer par priorité — en se taisant sur les séries saines et en séparant strictement les défauts de données des dérives.

État : partie 1 « Dérives » (liste priorisée, fiche avec preuve, qualité des données, sites sains, performance) et partie 2 « Causes et solutions » (causes classées avec indices pour et contre, vérifications, actions, fiche d'intervention exportable) démontrables. Méthode : `METHODS.md`. Données et prix : `DATA_SOURCES.md`. Pitch et fiche projet : `docs/`.

## Installation

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS / Linux
```

Copier `.env.example` en `.env` et renseigner la source des données (voir ci-dessous). `.env` n'est jamais suivi par git.

## Données : aucune dans le dépôt

L'application n'embarque **aucun fichier de données**. Elle lit, au moment de l'exécution, les seuls fichiers de la liste blanche `config/sources.yaml` (lots ouverts Rive-Claire 1, 4 et 5 ; PV en v2 seulement), et vérifie l'empreinte SHA-256 de chacun. Tout autre fichier est refusé ; les lots Ville de Genève et Quanthome ne sont ni lus, ni copiés, ni envoyés à un service.

- **En local** : `DATA_CONNECTEUR=local` et `DATA_LOCAL_DIR=<dossier hors du dépôt>` contenant les sous-dossiers `1-Donnees-Rive-Claire/`, `4-Donnees-Rive-Claire-Courbes/`, `5-Donnees-Rive-Claire-S04/` avec les seuls fichiers de la liste blanche.
- **En ligne** : `DATA_CONNECTEUR=http` et `DATA_SOURCE_URL=<URL de base>` ; chaque fichier est demandé à `<URL de base>/<chemin de la liste blanche>`, mis en cache dans `.cache/` après contrôle d'intégrité.
- Une commune peut brancher sa télérelève en implémentant `ConnecteurAPI` (`src/connecteurs/api.py`) : trois méthodes, le moteur ne change pas.

Si la source est injoignable, l'application le dit et propose `DATA_LOCAL_DIR` ; elle ne se rabat jamais sur des données cachées dans le code.

## Commandes (pas de make)

| Commande | Effet |
|---|---|
| `python -m src.outils verifier` | vérifie que la source fournit tous les fichiers attendus (SHA-256) |
| `python -m src.pipeline` | calcule tout et écrit `outputs/` (régénéré à chaque fois, ignoré par git) |
| `python -m streamlit run streamlit_app.py` | lance l'application |
| `python -m src.outils demo` | calcule puis lance l'application, sans LLM |
| `python -m src.banc` | banc d'essai court, écrit `outputs/evaluation.md` (onglet Performance) |
| `python -m src.outils purge` | supprime `.cache/`, `outputs/` et `logs/` |
| `python -m pytest -q` | lance les tests (fixtures synthétiques générées par le code) |

## Déploiement (Streamlit Community Cloud ou équivalent)

1. Pousser le dépôt public (code, configuration, documentation, tests ; **aucune donnée, aucun `.env`**). Le test `tests/test_garde_fous.py` échoue si un fichier de données, un fichier restreint ou un secret s'y trouve : le lancer avant chaque push.
2. Déposer les fichiers ouverts de la liste blanche sur un stockage maîtrisé par l'équipe, en conservant les chemins relatifs de `config/sources.yaml`.
3. Créer l'application en pointant sur `streamlit_app.py`, Python 3.11 ou plus.
4. Dans les **secrets** de l'hébergeur (jamais dans le code) :

   | Secret | Valeur |
   |---|---|
   | `DATA_CONNECTEUR` | `http` |
   | `DATA_SOURCE_URL` | URL de base du stockage des fichiers ouverts |
   | `LLM_ACTIF` | laisser vide : le LLM est désactivé par défaut en ligne |
   | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | seulement si le LLM est activé |

5. Au premier lancement, l'application télécharge les fichiers, vérifie leurs empreintes et calcule. La barre latérale affiche la source (hôte seulement) et la date de récupération.

Le LLM, s'il est activé, ne reçoit que des agrégats issus des données ouvertes et ne produit que du texte, jamais un chiffre. L'application fonctionne entièrement sans lui.

## Méthode en bref

1. **Qualité d'abord** : pas manquants (changement d'heure compris : 92 et 100 quarts d'heure), doublons, valeurs négatives, changement d'échelle, valeur figée, contrôle physique du chauffage à distance (énergie ≈ 1,163 × débit × ΔT). Un jour n'est jugé que si 18 h sur 24 sont mesurées. Un défaut de donnée va dans l'onglet Qualité, jamais dans les dérives.
2. **Moteur autonome — le détecteur.** L'attendu du jour est appris sur le passé seulement : historique mensuel 2021-2024 (signature par degrés-jours, niveau du même mois, ratio de performance du PV), puis jours sains de 2025 sur fenêtre glissante, à type de jour et météo égaux. Toutes les alertes affichées viennent de lui.
3. **Décision** : CUSUM, persistance (10 jours sur 14), écart cumulé d'au moins 10 %, référence gelée au début de la dérive, filtre de sobriété (un épisode retombé sous le seuil n'est pas affiché).
3 bis. **Rapprochement v2 — la vérification.** Le mensuel v2 de 2025 contient la part normale : il n'entre jamais dans la détection. Après coup seulement, il dit si une alerte est « confirmée par le rapprochement mensuel », donne un chiffrage de contrôle et sert de vérité pour `outputs/evaluation.md`. Les alertes non confirmées restent affichées comme telles et n'entrent pas dans les totaux.
4. **Impact** : seule la dérive constatée compte (« au moins »), avec une borne prudente ; la projection 12 mois est à part et hors score. Pas de double compte parent / sous-compteur ni PV / soutirage.

Détail des essais et des réglages : `CHANGELOG.md`.

## Limites

- **Le moteur autonome n'est pas sobre** : sur 2025, 9 dérives de contrôle sur 11 sont recouvertes par une alerte, et 7 alertes sur 18 ne sont pas confirmées par le rapprochement (précision 61 %). Elles se concentrent aux changements de saison : dans l'historique, un même mois varie de 5 à 10 % d'une année à l'autre.
- **Comparaison entre compteurs pairs** (gaz, chaleur à distance) : l'écart partagé le même jour par les autres compteurs de chauffage est retiré de l'attendu. Elle a supprimé 5 fausses alertes de reprise de chauffe et fait perdre une vraie dérive (gaz de S26, +17 %), confondue avec la reprise commune.
- **Dérives lentes ou sous 10 %** : S31 (+7 %) est manquée ; S30 (+6 %) et S32 (+7 %) sont trouvées avec 2 à 5 mois de retard ; trois alertes commencent avant la dérive de contrôle et la recouvrent sans la prouver. Détail dans `outputs/evaluation.md`.
- La précision sur un vrai parc n'est pas mesurable ici, et les seuils du moteur autonome ont été choisis après avoir vu ces données.
- **Couche mensuelle sur tout le parc** (102 séries : gaz, chaleur à distance, électricité générale, eau, COP), moteur autonome sans second relevé pour la vérifier. Non jugés : mazout et granulés, sous-compteurs, PV, et 5 compteurs dont le site a changé d'installation depuis 2021.
- **Prix** : seul le tarif électrique du jeu (0,27 CHF/kWh) est utilisé. Gaz, chaleur à distance, eau et solaire sont « non chiffrés » en CHF ; leurs alertes sont classées par kWh.
- **Moteur figé en version 1.0.0** (`CHANGELOG.md`) : plus aucun réglage guidé par l'évaluation.
- Pas encore couvert : heures réelles de démarrage et d'arrêt, LLM (l'app fonctionne entièrement par gabarits).
- Les causes viennent d'une base de règles écrite par l'équipe, non validée par un exploitant. Le banc d'essai est court et dit ce qu'il ne prouve pas.
- Au pas journalier, une fuite d'eau de nuit n'est pas observable. Mazout et granulés : livraisons sans stocks, consommation mensuelle inconnue.
- Quelques seuils ont été ajustés après avoir vu les données réelles (liste dans `CHANGELOG.md`).
- **Dérives déjà contenues dans la référence** (le rapprochement v2 ne les voit pas) : COP de S09 (2025), ventilation de S26 (+50 % depuis février 2024, sous-compteur ; une partie peut être un recâblage, le reste du site baissant d'environ 3 000 kWh/an), gaz de S22 (depuis le printemps 2023). Baisse du gaz de S38 (−38 % depuis 2023-24) sans événement déclaré, à expliquer.

## Attributions

- « Energ-IA Transition, Energ-IACK 2026 » (Rive-Claire v2)
- « Energ-IA Transition, Energ-IACK 2026, Rive-Claire courbes électriques v1 »
- « Energ-IA Transition, Energ-IACK 2026, Rive-Claire fluides, PV et chauffage à distance v2 »
- « Energ-IA Transition, Energ-IACK 2026, Rive-Claire S04 v2 »
- « Température et rayonnement : MétéoSuisse, station Genève-Cointrin »

Licence des données : [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr). Code : licence MIT (`LICENSE`). Briques tierces : `THIRD_PARTY_LICENSES.md`. Usage de l'IA : `AI_USAGE.md`.

Chiffres d'impact = surplus estimés ; causes et économies à vérifier sur le terrain.
