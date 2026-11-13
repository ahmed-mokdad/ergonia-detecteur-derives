# Briques tierces

Bibliothèques publiques et préexistantes, installées comme dépendances (aucun code copié dans le dépôt).
Licence relevée dans les métadonnées de la version installée (`importlib.metadata`), le 13.11.2026.

| Brique | Version | Licence | Usage |
|---|---|---|---|
| pandas | 3.1.1 | BSD-3-Clause | tables, séries temporelles |
| numpy | 2.4.6 | BSD-3-Clause (avec composants 0BSD, MIT, Zlib, CC0-1.0) | calcul numérique, régression robuste |
| openpyxl | 3.1.5 | MIT | lecture des classeurs .xlsx |
| PyYAML | 6.0.3 | MIT | fichiers de configuration |
| requests | 2.34.2 | Apache-2.0 | ConnecteurHTTP |
| plotly | 7.1.0 | MIT | graphiques |
| streamlit | 1.67.0 | Apache-2.0 | interface |
| pytest | 9.2.0 | MIT | tests |

Les dépendances transitives sont celles que ces paquets installent ; aucune dépendance GPL, AGPL, LGPL ou non commerciale n'a été ajoutée volontairement.
Les briques envisagées dans le cahier des charges et **non utilisées** à ce stade (statsmodels, scikit-learn, ruptures, eemeter, pvlib) ne sont pas installées :
la régression robuste, le CUSUM et l'estimation du point de rupture sont écrits dans `src/`.
