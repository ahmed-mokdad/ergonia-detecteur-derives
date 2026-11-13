# Journal du moteur (hackathon Energ-IACK 2026)

## Version 1.0.1 — documentation et facteur CO₂, aucun seuil modifié (vendredi 13.11.2026, soir)

Le moteur reste celui de la version 1.0.0 : aucune valeur de `config/seuils.yaml` n'a changé, les chiffres de
détection (9 dérives sur 11, 7 fausses alertes sur 18) sont inchangés.

- **Facteur CO₂ de l'électricité en cycle de vie : 94 → 125 g CO₂-éq/kWh.** Source primaire lue : KBOB/ecobau 2022
  v9.0, ligne 45.020 « CH-Verbrauchermix ». 94 g/kWh n'a été retrouvé ni dans KBOB ni dans les documents du
  hackathon. Seul `constate.kg_co2_cycle_de_vie` change (×1,33) ; le CO₂ direct et les priorités ne bougent pas.
- **Prix de référence sourcés** ajoutés dans `config/tarifs.yaml` (bloc `prix_references`) et `DATA_SOURCES.md`,
  **non utilisés** par le calcul : la règle « prix du jeu seulement » reste celle de l'équipe. Années signalées
  (injection : grille 2026 ; eau : non datée ; gaz : tarif au 1.10.2025).
- `docs/RECONCILIATION.md` : réconciliation série par série avec le projet deriv.io (S01, injection de S26, COP,
  CO₂), rejeu de deriv.io en temps réel, dérives déjà dans la référence, plafond d'injection de S32, causes et
  indices contraires, fourchettes en CHF.
- `METHODS.md` : injection de S26 lue comme défaut de comptage ; début de S22 au printemps 2023 ; définition du COP ;
  cause de S30 d'après le profil de nuit ; délai médian sans délais négatifs (11 jours).

**Candidates de version 1.1, non activées** (conçues en sachant quelles dérives étaient manquées : biais à dire) :
- R1, clôture mensuelle relative aux pairs (gaz, CAD, chaleur PAC ; attendu sans correction des pairs ; écart au
  mois moins médiane des pairs ≥ 10 % deux mois de suite) : retrouve S26 gaz le 30.11.2025 ; 2 fausses alertes
  ajoutées (S06 CAD et S32 gaz, en été).
- R3, saison ancrée sur son premier mois (régime saisonnier déclaré, S31) : retrouve S31 le 30.11.2025 ; 1 fausse
  alerte sur les trois saisons passées rejouées (décembre 2023).
- R2, rampe hebdomadaire : ne retrouve pas S31 et ajoute 9 fausses alertes ; rejetée.

## Version 1.0.0 — moteur figé (vendredi 13.11.2026)

Décision de l'équipe : **plus aucun réglage de seuil guidé par l'évaluation.** Toute modification ultérieure des valeurs ci-dessous serait une version 1.1 et devrait être justifiée sans regarder `outputs/evaluation.md`.

| Paramètre figé (`config/seuils.yaml`) | Valeur |
|---|---|
| Jour jugé | au moins 75 % des pas mesurés (18 h sur 24) |
| Valeur figée | 24 pas identiques (15 min ou heure), 5 jours (jour) ; échelle : 30 × la médiane |
| Contrôle chauffage à distance | écart à 1,163 × débit × ΔT > 8 % et > 1 kWh ; défaut si > 2 % des heures |
| Apprentissage du moteur autonome | 49 jours jugés, 5 jours par type de jour, réajustement hebdomadaire, fenêtre récente 90 jours |
| Détection au pas fin (moteur autonome) | CUSUM k 0,75, h 12 ; persistance 10 jours sur 14 ; écart cumulé 10 % (8 % retour CAD) ; clôture 14 jours ; acceptation d'une baisse 60 jours |
| Comparaison entre pairs | gaz, chaleur à distance, chaleur PAC ; au moins 4 pairs ; lissage 7 jours |
| Couche mensuelle | 24 mois d'apprentissage (12 mois de chauffe pour le COP), 2 mois consécutifs, plus de 2 écarts-types et de 10 % |
| Enjeu | plancher 30 CHF/mois ; urgence Élevée dès 300, Critique dès 1 000 CHF/mois ; × 1,5 pour l'eau |
| Vérification (hors détection) | mois « net » à 3 % ; CUSUM k 0,75, h 8, persistance 7 sur 10, écart 4 % |

Chiffres de la version 1.0.0 (`python -m src.pipeline`) : au pas fin, 19 alertes sur 40 séries ; contre la vérité de contrôle, 9 dérives sur 11 retrouvées, 7 fausses alertes sur 18, délai médian 8 jours ; dérives manquées : S31 électricité, S26 gaz. Couche mensuelle : 102 séries, 4 alertes.

Ajouts de la version 1.0.0 qui ne touchent aucun seuil du pas fin :
- **Prix : conventions du jeu seulement.** Électricité 0,27 CHF/kWh, CO₂ gaz 2,086 kg/m³, PCS mensuel de Ref_Conversion. Gaz, chaleur à distance, eau et kWh solaire perdu n'ont pas de prix dans le jeu : ils sont « non chiffrés » en CHF (kWh, m³ et CO₂ restent affichés). Conséquence : ces alertes n'ont ni urgence ni priorité en francs et sont classées après les autres, par kWh par mois ; le total en CHF ne couvre que l'électricité.
- **Couche mensuelle étendue à tout le parc** : électricité (compteur général) et eau, par le niveau du même mois des années précédentes appris sur le passé seulement, jugées en 2025. Mêmes seuils que le gaz et la chaleur à distance, fixés avant de voir le résultat.
- **COP** : comparaison annuelle S09 / S12 affichée (mesurée).
- La part 2025 des alertes mensuelles entre dans les totaux (c'est elle qui alimente le CO₂).

Tout est écrit pendant le hackathon, à partir de zéro. Chaque réglage fait après avoir vu les données réelles est noté ici.

## Vendredi 13.11.2026

**Socle.** Liste blanche des fichiers ouverts avec SHA-256 (`config/sources.yaml`), `ConnecteurLocal`, `ConnecteurHTTP` (testé sur serveur local), emplacement `ConnecteurAPI`, garde-fous (données, fichiers restreints, secrets).

**Qualité.** Contrôles au pas fin (pas manquants contre le calendrier, doublons, négatifs, échelle, valeur figée), contrôle physique CAD, mensuel v2, sources brutes S04.

**Référence, version 1 (abandonnée).** Attendu = niveau × type de jour + météo, appris jour après jour sur le passé de 2025. Constat sur les données réelles : alertes sur presque toutes les séries à la fin de l'apprentissage et à la reprise de chauffe (S01-CAD à +45 % toute l'année, par exemple).

**Référence, version 2 (abandonnée).** Niveau tiré de l'historique mensuel 2021-2024 (signature par degrés-jours pour le chauffage, même mois des années précédentes sinon, ratio de performance pour le PV), type de jour recalé sur 90 jours. Constat : encore une trentaine d'alertes. Mesure faite dans le mensuel v2 : un même mois varie de ±5 à 10 % d'une année à l'autre sur l'électricité (S47 : +25 à +40 % par an). Une référence historique ne peut pas isoler sobrement des dérives de 6 à 20 %.

**Référence, version 3 (retenue).** Le Lisez-moi des lots donne le mensuel v2 comme la « part normale » de chaque série. L'attendu du jour est le total mensuel v2 2025 du même compteur, réparti par type de jour, météo et tendance intra-mensuelle. La version 2 est conservée pour les séries sans second relevé (température de retour CAD).

**Réglages faits après avoir vu les données réelles** (risque de sur-ajustement, à dire) :
- seuil d'écart relatif de la température de retour CAD porté de 4 à 8 % : des variations de quelques kelvins fin décembre levaient des alertes sur S01 et S24 ;
- filtre « le mois doit s'écarter nettement de la v2 » (3 %) : sans lui, des répartitions différentes à l'intérieur d'un mois (ponts, fin de saison de chauffe, fermeture d'été de la crèche) étaient retenues ;
- rattrapage mensuel (deux mois consécutifs d'écart net) : S31-EL (+5 puis +9 %) restait sous le bruit journalier ;
- fusion des épisodes d'une même dérive quand les mois intermédiaires restent en écart net : S30-EL était coupée en trois ;
- sites avec PV : soutirage, production et injection suivis séparément. La consommation reconstituée amplifiait une erreur d'injection de 2 % en +12 %.

**Réglages faits sur le synthétique** : effet météo appris seulement s'il est actif 40 jours ; tendance intra-mensuelle ; début estimé par point de rupture (le test de datation échouait de 9 jours).

**Persistance après datation.** Deux alertes (S05 électricité et eau) étaient levées deux jours après leur début estimé : la règle exige désormais 7 jours jugés depuis ce début.

**Causes et solutions.** `knowledge/signatures.yaml` (dix signatures), règles pour / contre, fiche d'intervention par gabarit, test « aucun nombre absent des faits ».

**Banc d'essai court** (`python -m src.banc`) : référence naïve, autonome et ancrée sur 23 séries réelles saines perturbées. Aucun seuil n'a été modifié après le banc.

**Rejeu mensuel 2021-2025** (gaz, chaleur à distance, COP), moteur autonome. Réglage fait sur le synthétique : un mois de faible charge encore en écart relatif ne compte plus comme « calme » (une dérive constante de +25 % était coupée à chaque été ; sur les données réelles, S22 passait de trois alertes à une).

**Réorganisation en deux couches (décision de l'équipe).** La référence ancrée sur le mensuel v2 2025 regardait la réponse et le futur : elle n'est plus une source de détection. Détecteur = moteur autonome (version 2 ci-dessus), avec des seuils propres choisis après avoir vu les données (h 12, persistance 10 sur 14, écart cumulé 10 %) et un filtre de sobriété. Le rapprochement v2 ne sert plus qu'à étiqueter « confirmé / non confirmé », au chiffrage de contrôle et à l'évaluation. Résultat mesuré : 10 dérives de contrôle sur 11 recouvertes, 12 fausses alertes sur 24.

**Réduction des fausses alertes du moteur autonome.** Deux changements, choisis en regardant l'évaluation contre le rapprochement (donc ajustés sur la vérité de contrôle, à dire) :
- comparaison entre compteurs pairs pour le chauffage (gaz, chaleur à distance, chaleur PAC) ; essayée aussi sur l'électricité et l'eau puis retirée (2 fausses alertes seulement, mais 5 vraies dérives perdues) ;
- injection solaire : niveau tiré du mensuel 2021-2024 au lieu d'une référence sans historique.
Résultat : de 12 fausses alertes sur 24 à 7 sur 18 ; de 10 dérives de contrôle sur 11 à 9 sur 11 (gaz de S26 perdu).

**Seuils jamais touchés après le premier passage** (référence de contrôle) : CUSUM k = 0,75 et h = 8, persistance 7 jours sur 10, écart relatif 4 %, clôture 14 jours, plancher 30 CHF/mois.
