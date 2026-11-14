# Sources de données, prix et facteurs

## Jeux utilisés (ouverts, CC BY 4.0)

Seuls les fichiers de la liste blanche `config/sources.yaml` sont lus, après contrôle SHA-256. Aucun n'est dans le dépôt.

| Lot | Fichiers | Attribution (mot pour mot) |
|---|---|---|
| Rive-Claire v2, mensuel 2021-2025 | `EIAK-RC-Donnees-Rive-Claire-v2.xlsx` | « Energ-IA Transition, Energ-IACK 2026 » |
| Courbes électriques 15 min, 2025 | `EIAK-RC-Courbes-Elec-15min-v1.csv` et `.xlsx` (feuilles Compteurs, Calendrier_2025) | « Energ-IA Transition, Energ-IACK 2026, Rive-Claire courbes électriques v1 » |
| Fluides, PV, chauffage à distance, 2025 | `EIAK-RC-PV-15min-v2.csv`, `EIAK-RC-Fluides-Jour-v2.csv`, `EIAK-RC-CAD-Heure-v2.csv` | « Energ-IA Transition, Energ-IACK 2026, Rive-Claire fluides, PV et chauffage à distance v2 » |
| École du Centre S04, sources brutes | export SIR, courbe sept. 2022, onduleur, bons de mazout, relevés commune | « Energ-IA Transition, Energ-IACK 2026, Rive-Claire S04 v2 » |
| Climat (dans les lots ci-dessus) | température et rayonnement du calendrier 2025, feuilles Ref_Climat | « Température et rayonnement : MétéoSuisse, station Genève-Cointrin » |

Licence : [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.fr). Rive-Claire est une commune fictive : aucune tentative de réidentification, aucun géocodage, aucune adresse réelle.

**Non utilisés** : le fichier `EIAK-RC-PV-15min-v1.csv` (remplacé par la v2, refusé par motif) ; les jeux Ville de Genève et Quanthome (accès restreint : ni lus, ni copiés, ni envoyés à un service). Aucune donnée publique externe (MétéoSuisse en direct, SITG, RegBL) n'a été téléchargée.

## Prix (`config/tarifs.yaml`, modifiables)

| Vecteur | Valeur | Statut | Source |
|---|---|---|---|
| Électricité | 0,27 CHF/kWh | convention du jeu | tarif fictif SIR, Lisez-moi des courbes électriques |
| Électricité de la PAC (COP) | 0,27 CHF/kWh | convention du jeu | même tarif SIR |
| Gaz | — | **non chiffré** | pas de prix dans le jeu |
| Chaleur à distance | — | **non chiffré** | pas de prix dans le jeu |
| Eau | — | **non chiffré** | pas de prix dans le jeu |
| kWh solaire non produit ou non injecté | — | **non chiffré** | le tarif de reprise de l'injection n'est pas dans le jeu |

Règle : seuls les prix donnés par le jeu sont utilisés. Pour le gaz, la chaleur, l'eau et le solaire, l'app affiche « non chiffré » en CHF ; les kWh, les m³ et le CO₂ restent calculés. Une commune renseigne son prix et sa source dans `config/tarifs.yaml` (valeur `null` = non chiffré) et les CHF apparaissent sans autre changement.

### Prix de référence sourcés (non utilisés par le calcul)

Lus le 13.11.2026 dans les documents primaires ; ils figurent dans `config/tarifs.yaml`, bloc `prix_references`, pour
qu'une commune puisse les reprendre. Rive-Claire étant fictive, ce sont des ordres de grandeur genevois réels.

| Vecteur | Fourchette | Source | Année |
|---|---|---|---|
| Gaz | 9,61 à 10,31 ct/kWh PCS TTC (énergie + taxe CO₂ 2,158 ct + TVA 8,1 %, hors Vitale Vert) | SIG, Tarif gaz standard | **au 1.10.2025** ; janvier à septembre 2025 non lu |
| Chaleur à distance | 8,19 à 11,61 ct/kWh TTC (GeniTerre Transition à Vertua Plus ; Vertua 9,77) | SIG, tarifs réseaux thermiques structurants 2025 | 2025 |
| Eau | 1,50 à 2,80 CHF/m³, hors épuration | ge.ch, coût de l'eau potable | **non daté** |
| Injection PV | 4,40 (énergie seule) à 7,20 ct/kWh HT (avec garantie d'origine), ≥ 100 kW avec consommation propre | SIG, C 2.8 rétributions PV | **2026** ; grille 2025 non trouvée |

## Facteurs

| Facteur | Valeur | Source |
|---|---|---|
| Gaz, m³ → kWh PCS | facteur du mois, 10 à 11,5 kWh/m³ | feuille Ref_Conversion |
| CO₂ direct, gaz | 2,086 kg/m³ | feuille Ref_CO2, convention du jeu |
| CO₂ direct, mazout | 2,65 kg/l | feuille Ref_CO2 (non utilisé : aucune alerte mazout) |
| CO₂ direct, électricité et chaleur à distance | 0 | convention du jeu |
| CO₂ cycle de vie, électricité | 94 g/kWh | valeur citée dans le cahier des charges (mix consommateurs suisse), calculée à part dans `constate.kg_co2_cycle_de_vie`, jamais additionnée au direct |
| Degrés-jours | 20 − T si T < 12 °C, sinon 0 | convention SIA 381/3 du Dictionnaire, recalculée au jour depuis la température du calendrier |
| Chauffage à distance | énergie ≈ 1,163 × débit × (aller − retour) | Lisez-moi fluides |
