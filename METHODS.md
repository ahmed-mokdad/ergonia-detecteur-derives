# Méthodes

Principe : on ne compare jamais une mesure brute à une moyenne. On la compare à ce qu'elle aurait dû être, puis on exige que l'écart soit significatif, persistant et chiffrable, et qu'il ne s'explique ni par la météo, ni par le calendrier, ni par un événement connu, ni par un défaut de donnée.

## Couche 0 — Qualité (`src/qualite/controles.py`)

| Contrôle | Règle | Effet |
|---|---|---|
| Pas manquants | nombre de pas du jour comparé au calendrier (92 / 96 / 100 quarts d'heure) | jour non jugé sous 18 h mesurées sur 24 |
| Doublons d'horodatage | même texte d'horodatage (le décalage +01:00 / +02:00 distingue l'heure doublée d'octobre) | première occurrence gardée |
| Valeurs négatives | valeur < 0 | pas exclu |
| Échelle ou pic | pas > 30 × la médiane de la série | pas exclu ; ×1000 signalé comme probable Wh au lieu de kWh |
| Valeur figée | même valeur non nulle 24 pas de suite (15 min ou heure), 5 jours de suite (jour) | pas exclus |
| Chauffage à distance | écart à 1,163 × débit × ΔT > 8 % et > 1 kWh | heure exclue ; défaut si plus de 2 % des heures |
| Mensuel v2 | doublon (compteur, mois), « manquant », « estimé », négatif | mois non utilisé |
| S04 | ruptures d'index, quantité ≠ différence d'index, registres échangés, période en double, onduleur sans connexion, avoir de mazout, double compte de la synthèse | onglet Qualité seulement |

Aucune interpolation. Un jour partiel jugé est ramené au prorata des pas mesurés. Heures locales Europe/Zurich lues dans le texte, instants en UTC.

## Deux couches distinctes (organisation retenue)

1. **Moteur autonome = le détecteur.** Décrit sous « Référence autonome » ci-dessous ; il s'applique à toutes les séries. Seuils propres (`config/seuils.yaml`, `detection.autonome`) : h = 12, persistance 10 jours sur 14, écart cumulé 10 % (8 % pour le retour CAD). Un épisode dont l'écart cumulé retombe sous ce seuil n'est pas affiché. Détection = jour où la règle se déclenche, sans regarder le futur.
2. **Rapprochement v2 = la vérification, a posteriori.** La « référence ancrée » ci-dessous n'est plus une source de détection : le mensuel v2 de 2025 contient la part normale, et répartir un total mensuel sur ses jours regarde le futur. Elle sert à (a) étiqueter chaque alerte « confirmé / non confirmé par le rapprochement mensuel » (au moins un mois de la période à 3 % ou plus dans le même sens), (b) donner un chiffrage de contrôle, (c) fournir la vérité de contrôle de `outputs/evaluation.md`. Le chiffrage affiché vient du moteur autonome ; les alertes non confirmées n'entrent pas dans les totaux.

Les paragraphes qui suivent décrivent les deux calculs ; les règles « mois net », « fusion » et « rattrapage mensuel » ne concernent que la vérité de contrôle.

## Couche 1 — L'attendu

**Référence ancrée, utilisée en vérification seulement** (`src/detection/ancre.py`), pour les 36 séries qui ont un mensuel v2 du même identifiant : le total mensuel v2 2025 est réparti sur les jours du mois par une régression robuste (Huber) apprise sur les mois qui retombent sur la v2 à moins de 3 % :

`part du jour = effet du type de jour + effets météo (degrés-jours, rayonnement, chaleur, centrés sur le mois) + tendance intra-mensuelle`

- types de jour : ouvré, mercredi parascolaire (écoles), samedi, dimanche/férié, ouvré de vacances scolaires ;
- un effet météo n'est appris que s'il est actif 40 jours ; pénalité ridge sur les effets météo ;
- périodes déclarées (fermeture technique de la piscine du 11 au 24 août, crèche fermée entre Noël et Nouvel An) : jours non jugés ;
- bande à 95 % : ±1,96 écart-type robuste des résidus des mois conformes, avec plancher relatif de 3 %.

**Référence autonome** (`src/modeles/reference.py`, `src/detection/journalier.py`), pour toutes les séries. Niveau tiré du mensuel 2021-2024 après le dernier événement connu du fluide : signature base + pente × degrés-jours du jour (gaz, chaleur à distance, chaleur PAC), niveau du même mois corrigé de la part de jours de vacances (électricité, eau), kWc × rayonnement × ratio de performance du même mois (PV). Effets météo appris sur tout le passé de 2025, effet du type de jour recalé sur les 90 derniers jours sains. Apprise sur le passé seulement, réajustée chaque semaine, premier jugement après 49 jours, gelée au début d'un épisode. Une baisse durable dans le sens non surveillé devient le nouveau niveau après 60 jours (repli documenté).

**Sites avec PV** : soutirage, production et injection ont chacun leur série et leur mensuel v2. La consommation reconstituée (soutirage + production − injection) sert au contrôle de cohérence. Le soutirage nul à midi n'est jamais un défaut.

**Sous-compteurs** : seul le compteur général est suivi au pas fin ; jamais d'addition parent + enfant.

## Couche 2 — Décision (`src/detection/cusum.py`)

Une alerte exige tout à la fois :
1. CUSUM des résidus normalisés au-dessus de h = 8, avec tolérance k = 0,75 ; chaque résidu est borné à ±6 pour qu'un pic isolé ne déclenche jamais ;
2. persistance : 7 des 10 derniers jours jugés hors tolérance, et au moins 7 jours jugés depuis le début estimé ;
3. écart relatif cumulé d'au moins 4 % (8 % pour la température de retour) ;
4. pour la référence ancrée : au moins un mois de l'épisode s'écarte de la v2 de 3 % ou plus dans le même sens.

Début : point de rupture le plus probable d'un saut de moyenne, estimé avec les seuls jours connus au moment de l'alerte. Clôture : 14 jours jugés revenus dans la tolérance, ou 14 jours d'écart cumulé sous 2 %. Deux épisodes sont fusionnés si tous les mois intermédiaires restent en écart net. Rattrapage : deux mois consécutifs d'écart net sans épisode journalier donnent une alerte datée au mois. Un jour non jugé est sauté.

Date de détection : clôture du mois où la règle journalière se déclenche (le total mensuel n'est connu qu'alors). Le jour de la règle est conservé dans `detection_regle_journaliere`.

## Couche 4 — Impact (`src/impact/chiffrage.py`)

- **Constaté** = Σ (mesuré − attendu) sur les jours jugés de l'épisode, affiché « au moins ». **Borne prudente** = seule la part qui sort de la bande à 95 %.
- **Rythme mensuel** = excès moyen par jour des 30 derniers jours jugés × 30. **Projection 12 mois** = rythme × 12, hypothèse « dérive constante », hors score.
- **Priorité** = rythme en CHF/mois × confiance × urgence (Critique 3 dès 1 000 CHF/mois, Élevée 2 dès 300, Modérée 1) × 1,5 pour l'eau. Plancher : 30 CHF/mois (sauf eau).
- **Confiance** = 0,35 + 0,25 × min(1, |z moyen| / 3) + 0,20 × min(1, jours jugés / 30) + 0,10 × part de jours jugés + 0,10 si datation au jour ; plafonnée à 0,95. Indice d'ordonnancement, pas une probabilité calibrée.
- **Double compte** : perte PV = injection perdue + autoconsommation perdue ; si le soutirage du même site est en alerte sur la même période, seule l'injection perdue de la perte PV entre dans le total du parc.

## Causes (`knowledge/signatures.yaml`, `src/causes/moteur.py`)

Dix signatures. Chaque cause a une plausibilité de départ, relevée ou abaissée par des indices nommés calculés sur l'alerte (puissance de nuit avant / pendant, part du surplus les jours fermés, proximité d'un changement d'heure, autre fluide du même site, ΔT et débit…). L'app affiche ce qui soutient et ce qui contredit chaque hypothèse. Les pondérations sont des jugements de l'équipe, non calibrés sur des cas réels.

## Ce qui ne marche pas, ou pas encore

- **Comparaison entre compteurs pairs** (`pipeline.mode_commun`) : pour le gaz, la chaleur à distance et la chaleur PAC (11 séries), la médiane du résidu normalisé des AUTRES compteurs, lissée sur les 7 jours précédents, est retirée de l'attendu. Une dérive est propre à un site ; un écart commun vient de la météo ou de la saison mal modélisée. Non appliquée à l'électricité (6 compteurs sur 10 dérivent : leur médiane n'est pas un témoin, l'essai faisait perdre 4 vraies dérives) ni à l'eau, au PV et à l'injection (usages trop différents ou trop peu de pairs).
- **Le moteur autonome reste peu sobre.** Sur 2025 : 18 alertes sur les séries contrôlables, 11 confirmées, 7 fausses (précision 61 %) ; 9 dérives de contrôle sur 11 recouvertes ; S31 manquée (sous 10 %), gaz de S26 manqué (confondu avec la reprise de chauffe commune par la comparaison aux pairs) ; S30 et S32 trouvées avec 62 et 166 jours de retard, trois alertes commencées avant la dérive. Avant la comparaison aux pairs : 24 alertes, 12 fausses, 10 dérives sur 11. La raison est mesurée : dans le mensuel v2, un même mois varie de ±5 à 10 % d'une année à l'autre, et les fausses alertes tombent aux changements de saison (reprise de chauffe, fin de saison de glace, vacances).
- **Datation** : à quelques jours près quand le saut est net ; au mois pour les dérives lentes (S31-EL). Le début de S37-CAD (18 novembre) est probablement trop tardif : le mois de novembre entier est à +18 %.
- **Caractérisation nuit / jour** : comparaison brute des 60 jours précédents à la période de dérive, non corrigée de la saison.
- **Mensuel 2021-2025** (`src/detection/mensuel.py`) : moteur autonome, sans second relevé. Signature valeur/jour = base + pente × DJ/jour réapprise chaque mois sur au moins 24 mois sains (12 mois de chauffe pour le COP, modélisé selon la température du mois) ; alerte après deux mois consécutifs à plus de 2 écarts-types et de 10 % ; référence gelée ; clôture après deux mois revenus sous 5 %. Seuls gaz, chaleur à distance et COP sont rejoués ; les séries suivies au pas fin s'arrêtent à fin 2024. Ces alertes sont listées à part, hors total, sans causes. Le début de S22 (octobre 2023) est le premier couple de mois hors bande après l'apprentissage : la dérive peut être plus ancienne, ou tenir en partie à la forme linéaire de la signature.
- **Non couvert** : électricité et eau mensuelles, heures réelles de démarrage et d'arrêt, fuite d'eau de nuit (impossible au pas journalier), mazout et granulés (livraisons sans stocks).
- **S26, injection d'août** : classée dérive ; production et soutirage étant normaux, un défaut du registre d'injection est l'hypothèse la plus plausible.
- **Seuils** : cinq réglages ont été faits après avoir vu les données réelles (CHANGELOG). Le banc d'essai (`outputs/evaluation.md`) dit ce qu'il ne prouve pas.
