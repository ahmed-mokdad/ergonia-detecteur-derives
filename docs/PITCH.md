# Pitch 3 minutes — Équipe Ergonia, défi 4

Tous les chiffres viennent de `python -m src.pipeline` (moteur figé en version 1.0.0, Rive-Claire). À relancer avant le pitch : c'est la sortie du code qui fait foi.

## Déroulé

**0:00 – 0:30 · Le problème.** Un exploitant communal reçoit des centaines de courbes. S'il compare chaque mois à la moyenne des années passées, il se noie : en octobre 2025, le gaz de l'école S08 est à +141 % de sa médiane, et à +8 % seulement une fois le froid pris en compte. Notre outil ne lève pas d'alerte, et il a raison.

**0:30 – 2:30 · La solution et la preuve.**
- *(onglet Qualité)* D'abord trier les données : 26 défauts tenus à part. L'immeuble S34 affiche +46 765 % en novembre : c'est un export en Wh, pas une dérive.
- *(onglet Dérives)* Un détecteur qui n'utilise que le passé : historique 2021-2024, météo, calendrier, comparaison entre compteurs de chauffage. Chaque alerte arrive avec sa preuve, ses causes probables et sa check-list.
- *(fiche S01)* La mairie : +12,4 % depuis le 1er mai, à toute heure y compris la nuit. Détectée en 11 jours. 11 016 kWh, 2 974 CHF constatés, « au moins ».
- *(fiche S06)* L'école de Bois-Joli : l'énergie est normale, mais le retour du chauffage à distance est chaud et le ΔT s'est écrasé. Invisible sur la facture, visible en croisant.
- *(couche mensuelle)* Tout le parc, 102 séries : le gaz de S22 à +26 % à météo égale, soit 7,33 t de CO₂ en 2025 ; la pompe à chaleur de S09 dont le COP passe de 4,19 à 3,01 quand celle de S12 reste à 4,49.
- *(onglet Performance)* Nous avons contrôlé notre détecteur avec un relevé qu'il n'a jamais vu : 9 dérives sur 11 retrouvées, avec un délai médian de 8 jours. En comparant les compteurs de chauffage entre eux, nous avons réduit les fausses alertes de 12 à 7, et chaque alerte porte son étiquette « confirmée » ou « non confirmée ».

**2:30 – 3:00 · L'impact, les limites assumées, la suite.** 160 340 kWh de surplus constatés en 2025, 7,33 t de CO₂ direct, 16 966 CHF pour la seule électricité : nous n'avons chiffré en francs que ce dont le jeu donne le prix. Deux limites assumées : une dérive lente de 7 % sur la patinoire S31 reste sous notre seuil, et le gaz de S26 se confond avec la reprise de chauffe. Le moteur est figé, ses seuils sont publiés. Pour la Ville : un connecteur à brancher sur sa télérelève, ses prix à renseigner, ses horaires à déclarer ; code MIT, aucune donnée dans le dépôt.

## Alertes vitrines

| # | Alerte | Pourquoi la montrer |
|---|---|---|
| 1 | S01 électricité, +12,4 % depuis le 01.05, 11 016 kWh, confirmée | le cas d'école : hausse à toute heure, détectée en 11 jours |
| 2 | S32 photovoltaïque, −29,8 % depuis le 23.05, confirmée | sens inverse (production), détectée en 7 jours |
| 3 | S05 électricité et eau pendant les vacances d'été, confirmées | deux fluides, une cause probable ; indices pour et contre |
| 4 | S06 retour chaud depuis le 19.10 | visible seulement en croisant débit et températures |
| 5 | S26 injection nulle en août, confirmée | production et soutirage normaux : dérive ou défaut du registre ? L'outil pose la question |
| 6 | S08 gaz, octobre 2025 : +141 % face à la médiane, +8 % à degrés-jours égaux | la météo change la décision : pas d'alerte |
| 7 | S22 gaz, +26 % à degrés-jours égaux, 7,33 t CO₂ en 2025 | la couche mensuelle, tout le parc |
| 8 | COP de S09 : 4,19 en 2024, 3,01 en 2025 ; S12 stable à 4,49 | croisement chaleur / électricité, comparé à un pair |
| 9 | S34 électricité, défaut ×1000 | ce que l'outil refuse d'appeler une dérive |
| 10 | S31 patinoire (+7 %) et S26 gaz (+17 %) | les deux limites assumées |

## Secours

Lancer `python -m src.outils demo` avant le pitch (le cache est rempli, l'app tourne sans réseau ni LLM). Capture vidéo de secours : à enregistrer par l'équipe.
